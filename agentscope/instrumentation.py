# agentscope/instrumentation.py
"""
OpenTelemetry instrumentation layer for AgentScope.
Emits GenAI semantic convention spans for LLM calls, tool executions,
and hierarchical multi-agent delegations with full async & thread-safety support.
"""

import re
import threading
from contextlib import contextmanager, asynccontextmanager
from typing import Any, Dict, List, Optional, Union, Generator, AsyncGenerator

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    ConsoleSpanExporter,
    SpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
except Exception:
    OTLPSpanExporter = None

from agentscope.constants import (
    OTEL_GENAI_SPEC_VERSION,
    CAPTURE_CONTENT,
    DEFAULT_SERVICE_NAME,
    DEFAULT_OTLP_ENDPOINT,
)

# Setup thread lock and global references
_lock = threading.RLock()
_tracer: Optional[trace.Tracer] = None
_tracer_provider: Optional[TracerProvider] = None
_in_memory_exporter: Optional[InMemorySpanExporter] = None

# Secret detection regexes
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),               # OpenAI / Generic API key
    re.compile(r"sk-ant-[a-zA-Z0-9_\-]{30,}", re.IGNORECASE),          # Anthropic API key
    re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE),                 # GitHub Personal Access Token
    re.compile(r"github_pat_[a-zA-Z0-9_]{50,}", re.IGNORECASE),        # GitHub Fine-grained PAT
    re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE),                    # AWS Access Key
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}", re.IGNORECASE),             # Google API Key
    re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,}", re.IGNORECASE),          # Slack Token
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),      # Bearer Tokens
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", re.IGNORECASE), # Private Keys
]

SECRET_KEYWORDS = ("key", "secret", "token", "password", "auth", "credential", "private", "api_key")


def sanitize_value(key: str, value: Any) -> Any:
    """
    Recursively redacts values that look like secrets/keys based on key name or content patterns.
    Handles strings, dicts, lists, tuples, and sets.
    """
    if value is None:
        return None

    if isinstance(value, dict):
        return sanitize_dict(value)

    if isinstance(value, (list, tuple)):
        sanitized_list = [sanitize_value(f"{key}[{i}]", item) for i, item in enumerate(value)]
        return type(value)(sanitized_list)

    if isinstance(value, set):
        return {sanitize_value(f"{key}", item) for item in value}

    key_lower = str(key).lower()
    if any(kw in key_lower for kw in SECRET_KEYWORDS):
        return "[REDACTED]"

    if isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                return "[REDACTED]"
        return value

    return value


def sanitize_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitizes a dictionary of attributes."""
    if not isinstance(d, dict):
        return sanitize_value("data", d)
    sanitized = {}
    for k, v in d.items():
        sanitized[str(k)] = sanitize_value(str(k), v)
    return sanitized


def init_tracer(
    service_name: str = DEFAULT_SERVICE_NAME,
    endpoint: str = DEFAULT_OTLP_ENDPOINT,
    span_processor: Optional[SpanProcessor] = None,
    use_batch_processor: bool = True,
    insecure: bool = True,
) -> trace.Tracer:
    """
    Initializes the global OpenTelemetry tracer in a thread-safe manner.
    Supports custom processors, OTLP gRPC export, and graceful fallback.
    """
    global _tracer, _tracer_provider
    with _lock:
        resource = Resource(attributes={
            "service.name": service_name,
            "gen_ai.spec.version": OTEL_GENAI_SPEC_VERSION,
        })
        provider = TracerProvider(resource=resource)

        if span_processor is not None:
            provider.add_span_processor(span_processor)
        elif OTLPSpanExporter is not None and endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
                if use_batch_processor:
                    processor = BatchSpanProcessor(otlp_exporter)
                else:
                    processor = SimpleSpanProcessor(otlp_exporter)
                provider.add_span_processor(processor)
            except Exception as e:
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        else:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

        trace._TRACER_PROVIDER = provider
        _tracer_provider = provider
        _tracer = provider.get_tracer(service_name)
        return _tracer


def init_in_memory_tracer(service_name: str = "agentscope-in-memory") -> tuple[trace.Tracer, InMemorySpanExporter]:
    """
    Initializes an in-memory tracer provider with an InMemorySpanExporter.
    Ideal for unit tests, offline tracing, and hermetic verification.
    """
    global _tracer, _tracer_provider, _in_memory_exporter
    with _lock:
        resource = Resource(attributes={
            "service.name": service_name,
            "gen_ai.spec.version": OTEL_GENAI_SPEC_VERSION,
        })
        provider = TracerProvider(resource=resource)
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        trace._TRACER_PROVIDER = provider
        _tracer_provider = provider
        _in_memory_exporter = exporter
        _tracer = provider.get_tracer(service_name)
        return _tracer, exporter


def get_tracer() -> trace.Tracer:
    """Returns the active global tracer, creating a default one if uninitialized."""
    global _tracer, _tracer_provider
    with _lock:
        if _tracer is not None:
            return _tracer
        if _tracer_provider is not None:
            _tracer = _tracer_provider.get_tracer(DEFAULT_SERVICE_NAME)
            return _tracer
        _tracer = trace.get_tracer(DEFAULT_SERVICE_NAME)
        return _tracer


def get_in_memory_exporter() -> Optional[InMemorySpanExporter]:
    """Returns the current InMemorySpanExporter if configured."""
    with _lock:
        return _in_memory_exporter


def flush_tracer() -> None:
    """Flushes all registered span processors."""
    with _lock:
        if _tracer_provider is not None:
            try:
                _tracer_provider.force_flush()
            except Exception:
                pass


def shutdown_tracer() -> None:
    """Shuts down the tracer provider cleanly."""
    global _tracer, _tracer_provider, _in_memory_exporter
    with _lock:
        if _tracer_provider is not None:
            try:
                _tracer_provider.shutdown()
            except Exception:
                pass
        _tracer_provider = None
        _tracer = None
        _in_memory_exporter = None


def reset_tracer() -> None:
    """Resets the global tracer state (useful between tests)."""
    shutdown_tracer()


class LLMCallContext:
    """Context object passed to caller to record LLM response metadata."""
    def __init__(self, span: trace.Span):
        self.span = span
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.response_model: Optional[str] = None
        self.completion: Optional[str] = None


@contextmanager
def instrument_llm_call(
    model: str,
    messages: Optional[List[Dict[str, Any]]] = None,
    parent_span: Optional[trace.Span] = None,
    **kwargs: Any
) -> Generator[LLMCallContext, None, None]:
    """
    Synchronous context manager that emits an OTel span with gen_ai.* attributes around an LLM call.
    Automatically captures token usage, response model, timing, and errors.
    """
    tracer = get_tracer()
    span_name = f"chat {model}"
    messages = messages or []

    attributes = {
        "gen_ai.request.model": model,
        "gen_ai.system": kwargs.get("system", "mock"),
        "gen_ai.operation.name": "chat",
        "otel.library.name": "agentscope",
    }

    sanitized_kwargs = sanitize_dict(kwargs)
    for k, v in sanitized_kwargs.items():
        if k not in ["system", "messages"]:
            attributes[f"gen_ai.request.{k}"] = str(v)

    if CAPTURE_CONTENT and messages:
        sanitized_messages = [sanitize_dict(m) for m in messages]
        attributes["gen_ai.request.content"] = str(sanitized_messages)

    context = trace.set_span_in_context(parent_span) if parent_span else None

    with tracer.start_as_current_span(span_name, context=context, attributes=attributes) as span:
        ctx = LLMCallContext(span)
        try:
            yield ctx
            span.set_attribute("gen_ai.response.model", ctx.response_model or model)
            span.set_attribute("gen_ai.usage.input_tokens", int(ctx.input_tokens))
            span.set_attribute("gen_ai.usage.output_tokens", int(ctx.output_tokens))
            if CAPTURE_CONTENT and ctx.completion:
                span.set_attribute("gen_ai.response.content", str(sanitize_value("completion", ctx.completion)))
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            raise


@asynccontextmanager
async def async_instrument_llm_call(
    model: str,
    messages: Optional[List[Dict[str, Any]]] = None,
    parent_span: Optional[trace.Span] = None,
    **kwargs: Any
) -> AsyncGenerator[LLMCallContext, None]:
    """
    Asynchronous context manager variant of instrument_llm_call for asyncio pipelines.
    """
    tracer = get_tracer()
    span_name = f"chat {model}"
    messages = messages or []

    attributes = {
        "gen_ai.request.model": model,
        "gen_ai.system": kwargs.get("system", "mock"),
        "gen_ai.operation.name": "chat",
        "otel.library.name": "agentscope",
    }

    sanitized_kwargs = sanitize_dict(kwargs)
    for k, v in sanitized_kwargs.items():
        if k not in ["system", "messages"]:
            attributes[f"gen_ai.request.{k}"] = str(v)

    if CAPTURE_CONTENT and messages:
        sanitized_messages = [sanitize_dict(m) for m in messages]
        attributes["gen_ai.request.content"] = str(sanitized_messages)

    context = trace.set_span_in_context(parent_span) if parent_span else None

    with tracer.start_as_current_span(span_name, context=context, attributes=attributes) as span:
        ctx = LLMCallContext(span)
        try:
            yield ctx
            span.set_attribute("gen_ai.response.model", ctx.response_model or model)
            span.set_attribute("gen_ai.usage.input_tokens", int(ctx.input_tokens))
            span.set_attribute("gen_ai.usage.output_tokens", int(ctx.output_tokens))
            if CAPTURE_CONTENT and ctx.completion:
                span.set_attribute("gen_ai.response.content", str(sanitize_value("completion", ctx.completion)))
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            raise


def instrument_tool_call(
    tool_name: str,
    args: Dict[str, Any],
    result: Any,
    parent_span: Optional[trace.Span] = None
) -> trace.Span:
    """
    Emits a completed child span for a tool execution under the current or specified span context.
    """
    tracer = get_tracer()
    span_name = f"tool {tool_name}"

    sanitized_args = sanitize_dict(args)
    sanitized_result = sanitize_value("result", result)

    attributes = {
        "tool.name": tool_name,
        "tool.args": str(sanitized_args),
    }
    if CAPTURE_CONTENT:
        attributes["tool.result"] = str(sanitized_result)

    context = trace.set_span_in_context(parent_span) if parent_span else None
    with tracer.start_as_current_span(span_name, context=context, attributes=attributes) as span:
        span.set_status(Status(StatusCode.OK))
        return span


@contextmanager
def instrument_tool_call_timed(
    tool_name: str,
    args: Dict[str, Any],
    parent_span: Optional[trace.Span] = None
) -> Generator[trace.Span, None, None]:
    """
    Synchronous context manager that times tool execution, records arguments, results, and errors.
    """
    tracer = get_tracer()
    attributes = {
        "tool.name": tool_name,
        "tool.args": str(sanitize_dict(args)),
    }
    context = trace.set_span_in_context(parent_span) if parent_span else None
    with tracer.start_as_current_span(f"tool {tool_name}", context=context, attributes=attributes) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            raise


@asynccontextmanager
async def async_instrument_tool_call_timed(
    tool_name: str,
    args: Dict[str, Any],
    parent_span: Optional[trace.Span] = None
) -> AsyncGenerator[trace.Span, None]:
    """
    Asynchronous context manager variant of instrument_tool_call_timed.
    """
    tracer = get_tracer()
    attributes = {
        "tool.name": tool_name,
        "tool.args": str(sanitize_dict(args)),
    }
    context = trace.set_span_in_context(parent_span) if parent_span else None
    with tracer.start_as_current_span(f"tool {tool_name}", context=context, attributes=attributes) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            raise


@contextmanager
def dispatch_subagent(
    parent_span: Optional[trace.Span],
    agent_role: str,
    task: str,
    **kwargs: Any
) -> Generator[trace.Span, None, None]:
    """
    Synchronous context manager creating a subagent span nested under parent_span or active context.
    Records agent role, task description, and tracks exceptions.
    """
    tracer = get_tracer()
    span_name = f"agent {agent_role}"

    context = trace.set_span_in_context(parent_span) if parent_span else None
    attributes = {
        "agent.role": agent_role,
        "agent.task": task,
    }
    for k, v in sanitize_dict(kwargs).items():
        attributes[f"agent.{k}"] = str(v)

    with tracer.start_as_current_span(span_name, context=context, attributes=attributes) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            raise


@asynccontextmanager
async def async_dispatch_subagent(
    parent_span: Optional[trace.Span],
    agent_role: str,
    task: str,
    **kwargs: Any
) -> AsyncGenerator[trace.Span, None]:
    """
    Asynchronous context manager creating a subagent span nested under parent_span or active context.
    Ideal for async multi-agent orchestrations with asyncio.gather / TaskGroup.
    """
    tracer = get_tracer()
    span_name = f"agent {agent_role}"

    context = trace.set_span_in_context(parent_span) if parent_span else None
    attributes = {
        "agent.role": agent_role,
        "agent.task": task,
    }
    for k, v in sanitize_dict(kwargs).items():
        attributes[f"agent.{k}"] = str(v)

    with tracer.start_as_current_span(span_name, context=context, attributes=attributes) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            raise
