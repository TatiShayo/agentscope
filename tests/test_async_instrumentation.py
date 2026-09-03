# tests/test_async_instrumentation.py
"""
Async unit and concurrency tests for AgentScope instrumentation layer.
Tests async context managers, TaskGroup / asyncio.gather context propagation, and error handling.
"""

import asyncio
import os
import sys
import pytest
from opentelemetry.trace import StatusCode

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentscope.instrumentation import (
    init_in_memory_tracer,
    reset_tracer,
    async_instrument_llm_call,
    async_instrument_tool_call_timed,
    async_dispatch_subagent,
)


@pytest.fixture(autouse=True)
def setup_test_tracer():
    reset_tracer()
    tracer, exporter = init_in_memory_tracer("test-async-service")
    yield tracer, exporter
    reset_tracer()


@pytest.mark.asyncio
async def test_async_instrument_llm_call_success(setup_test_tracer):
    tracer, exporter = setup_test_tracer
    async with async_instrument_llm_call("claude-3-5-sonnet", system="anthropic") as ctx:
        await asyncio.sleep(0.01)
        ctx.input_tokens = 50
        ctx.output_tokens = 120
        ctx.response_model = "claude-3-5-sonnet-20241022"
        ctx.completion = "Async response"

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chat claude-3-5-sonnet"
    assert span.attributes["gen_ai.usage.input_tokens"] == 50
    assert span.attributes["gen_ai.usage.output_tokens"] == 120
    assert span.status.status_code == StatusCode.OK


@pytest.mark.asyncio
async def test_async_instrument_llm_call_records_exception(setup_test_tracer):
    tracer, exporter = setup_test_tracer
    with pytest.raises(TimeoutError, match="API Timeout"):
        async with async_instrument_llm_call("gpt-4o"):
            await asyncio.sleep(0.01)
            raise TimeoutError("API Timeout")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code == StatusCode.ERROR
    assert "API Timeout" in spans[0].status.description


@pytest.mark.asyncio
async def test_async_instrument_tool_call_timed(setup_test_tracer):
    tracer, exporter = setup_test_tracer
    async with async_instrument_tool_call_timed("web_search", {"query": "OTel gen_ai"}) as span:
        await asyncio.sleep(0.01)
        span.set_attribute("results.count", 5)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "tool web_search"
    assert spans[0].attributes["results.count"] == 5
    assert spans[0].status.status_code == StatusCode.OK


@pytest.mark.asyncio
async def test_async_subagent_dispatch(setup_test_tracer):
    tracer, exporter = setup_test_tracer
    async with async_dispatch_subagent(None, "ResearchAgent", "Find documentation") as agent_span:
        async with async_instrument_llm_call("deepseek-v3", parent_span=agent_span) as ctx:
            ctx.input_tokens = 100
            ctx.output_tokens = 50

    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    llm_span = spans[0]
    subagent_span = spans[1]
    assert llm_span.parent.span_id == subagent_span.context.span_id


@pytest.mark.asyncio
async def test_async_parallel_agent_execution(setup_test_tracer):
    """Verifies that concurrent asyncio tasks preserve parent-child context and distinct span boundaries."""
    tracer, exporter = setup_test_tracer

    with tracer.start_as_current_span("Lead Coordinator") as root_span:
        async def run_worker(role: str, tokens: int):
            async with async_dispatch_subagent(root_span, role, f"Task for {role}") as span:
                async with async_instrument_llm_call("gpt-4o-mini", parent_span=span) as ctx:
                    await asyncio.sleep(0.02)
                    ctx.input_tokens = tokens
                    ctx.output_tokens = tokens * 2

        await asyncio.gather(
            run_worker("SecurityAuditor", 150),
            run_worker("QATester", 250),
            run_worker("DocsWriter", 350),
        )

    spans = exporter.get_finished_spans()
    assert len(spans) == 7  # 1 root + 3 subagents + 3 LLM calls

    root_span_recorded = next(s for s in spans if s.name == "Lead Coordinator")
    subagent_spans = [s for s in spans if s.name.startswith("agent ")]
    llm_spans = [s for s in spans if s.name.startswith("chat ")]

    assert len(subagent_spans) == 3
    assert len(llm_spans) == 3

    # All subagents have root as parent
    for sa in subagent_spans:
        assert sa.parent.span_id == root_span_recorded.context.span_id
        assert sa.context.trace_id == root_span_recorded.context.trace_id

    # All spans share the same trace_id
    trace_ids = {s.context.trace_id for s in spans}
    assert len(trace_ids) == 1
