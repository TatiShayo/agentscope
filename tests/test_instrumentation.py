# tests/test_instrumentation.py
"""
Unit and integration tests for AgentScope OpenTelemetry instrumentation layer.
Tests span lifecycle, attribute redaction, error recording, timing, and hierarchy.
"""

import sys
import os
import pytest
from opentelemetry.trace import StatusCode

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentscope.instrumentation import (
    init_in_memory_tracer,
    get_tracer,
    reset_tracer,
    instrument_llm_call,
    instrument_tool_call,
    instrument_tool_call_timed,
    dispatch_subagent,
    sanitize_value,
    sanitize_dict,
)
import agentscope.instrumentation as inst_mod


@pytest.fixture(autouse=True)
def setup_test_tracer():
    reset_tracer()
    tracer, exporter = init_in_memory_tracer("test-service")
    yield tracer, exporter
    reset_tracer()


class TestSecretSanitization:
    def test_sanitize_keywords(self):
        assert sanitize_value("api_key", "secret123") == "[REDACTED]"
        assert sanitize_value("authToken", "token_val") == "[REDACTED]"
        assert sanitize_value("password", "pass123") == "[REDACTED]"
        assert sanitize_value("user_secret", "data") == "[REDACTED]"
        assert sanitize_value("private_key", "data") == "[REDACTED]"

    def test_sanitize_openai_key_regex(self):
        val = "Use key sk-1234567890abcdef1234567890abcdef here"
        assert sanitize_value("prompt", val) == "[REDACTED]"

    def test_sanitize_anthropic_key_regex(self):
        val = "sk-ant-1234567890abcdef1234567890abcdef12"
        assert sanitize_value("input", val) == "[REDACTED]"

    def test_sanitize_github_token_regex(self):
        val = "ghp_1234567890abcdef1234567890abcdef1234"
        assert sanitize_value("config", val) == "[REDACTED]"

    def test_sanitize_aws_key_regex(self):
        val = "AKIAIOSFODNN7EXAMPLE"
        assert sanitize_value("creds", val) == "[REDACTED]"

    def test_sanitize_google_key_regex(self):
        val = "AIzaSyD-1234567890abcdef1234567890abc"
        assert sanitize_value("param", val) == "[REDACTED]"

    def test_sanitize_bearer_token(self):
        val = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        assert sanitize_value("auth_header", val) == "[REDACTED]"

    def test_sanitize_private_key_block(self):
        val = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASC..."
        assert sanitize_value("key_file", val) == "[REDACTED]"

    def test_sanitize_nested_dict(self):
        d = {
            "model": "gpt-4o",
            "auth": {"token": "secret_abc", "user": "alice"},
            "headers": ["Authorization", "sk-12345678901234567890123456789012"],
        }
        sanitized = sanitize_dict(d)
        assert sanitized["model"] == "gpt-4o"
        assert sanitized["auth"]["token"] == "[REDACTED]"
        assert sanitized["auth"]["user"] == "alice"
        assert sanitized["headers"][1] == "[REDACTED]"

    def test_sanitize_none_and_primitives(self):
        assert sanitize_value("none_val", None) is None
        assert sanitize_value("int_val", 42) == 42
        assert sanitize_value("float_val", 3.14) == 3.14
        assert sanitize_value("bool_val", True) is True


class TestLLMCallInstrumentation:
    def test_instrument_llm_call_emits_span(self, setup_test_tracer):
        tracer, exporter = setup_test_tracer
        with instrument_llm_call("gpt-4o", system="openai", temperature=0.7) as ctx:
            ctx.input_tokens = 100
            ctx.output_tokens = 200
            ctx.response_model = "gpt-4o-2024-08-06"
            ctx.completion = "Hello World"

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "chat gpt-4o"
        assert span.attributes["gen_ai.request.model"] == "gpt-4o"
        assert span.attributes["gen_ai.response.model"] == "gpt-4o-2024-08-06"
        assert span.attributes["gen_ai.usage.input_tokens"] == 100
        assert span.attributes["gen_ai.usage.output_tokens"] == 200
        assert span.attributes["gen_ai.system"] == "openai"
        assert span.status.status_code == StatusCode.OK

    def test_instrument_llm_call_records_exception(self, setup_test_tracer):
        tracer, exporter = setup_test_tracer
        with pytest.raises(RuntimeError, match="LLM rate limit"):
            with instrument_llm_call("claude-3-5-sonnet", system="anthropic"):
                raise RuntimeError("LLM rate limit")

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.status.status_code == StatusCode.ERROR
        assert "LLM rate limit" in span.status.description
        assert len(span.events) > 0
        assert span.events[0].name == "exception"

    def test_instrument_llm_call_content_capture_flag(self, setup_test_tracer, monkeypatch):
        tracer, exporter = setup_test_tracer
        monkeypatch.setattr(inst_mod, "CAPTURE_CONTENT", True)

        messages = [{"role": "user", "content": "What is 2+2?"}]
        with instrument_llm_call("gpt-4o", messages=messages) as ctx:
            ctx.completion = "4"

        spans = exporter.get_finished_spans()
        span = spans[0]
        assert "gen_ai.request.content" in span.attributes
        assert "gen_ai.response.content" in span.attributes
        assert "What is 2+2?" in span.attributes["gen_ai.request.content"]
        assert span.attributes["gen_ai.response.content"] == "4"


class TestToolCallInstrumentation:
    def test_instant_tool_call_emits_child_span(self, setup_test_tracer):
        tracer, exporter = setup_test_tracer
        instrument_tool_call("bash", {"command": "ls -la"}, "file1.py\nfile2.py")
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "tool bash"
        assert span.attributes["tool.name"] == "bash"
        assert "command" in span.attributes["tool.args"]
        assert span.status.status_code == StatusCode.OK

    def test_timed_tool_call_records_duration_and_status(self, setup_test_tracer):
        tracer, exporter = setup_test_tracer
        with instrument_tool_call_timed("pytest", {"path": "tests/"}) as span:
            span.set_attribute("tests.passed", 10)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "tool pytest"
        assert span.attributes["tests.passed"] == 10
        assert span.status.status_code == StatusCode.OK

    def test_timed_tool_call_records_exception(self, setup_test_tracer):
        tracer, exporter = setup_test_tracer
        with pytest.raises(ValueError, match="Invalid tool syntax"):
            with instrument_tool_call_timed("code_eval", {"code": "invalid(("}):
                raise ValueError("Invalid tool syntax")

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].status.status_code == StatusCode.ERROR
        assert "Invalid tool syntax" in spans[0].status.description


class TestSubagentHierarchy:
    def test_subagent_dispatch_creates_parent_child_hierarchy(self, setup_test_tracer):
        tracer, exporter = setup_test_tracer
        with tracer.start_as_current_span("Lead Orchestrator") as lead_span:
            with dispatch_subagent(lead_span, "Developer", "Implement feature X") as dev_span:
                instrument_tool_call("write_file", {"path": "main.py"}, "ok", parent_span=dev_span)

        spans = exporter.get_finished_spans()
        assert len(spans) == 3

        # Spans finish in reverse order: tool, dev, lead
        tool_span = next(s for s in spans if s.name.startswith("tool"))
        dev_span = next(s for s in spans if s.name == "agent Developer")
        lead_span = next(s for s in spans if s.name == "Lead Orchestrator")

        # Check trace ID matches across all spans
        assert tool_span.context.trace_id == dev_span.context.trace_id == lead_span.context.trace_id
        # Check parent hierarchy
        assert tool_span.parent.span_id == dev_span.context.span_id
        assert dev_span.parent.span_id == lead_span.context.span_id
        assert lead_span.parent is None

    def test_subagent_dispatch_records_error(self, setup_test_tracer):
        tracer, exporter = setup_test_tracer
        with pytest.raises(ZeroDivisionError):
            with dispatch_subagent(None, "Security", "Audit auth"):
                _ = 1 / 0

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "agent Security"
        assert spans[0].status.status_code == StatusCode.ERROR
