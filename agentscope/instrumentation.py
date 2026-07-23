# agentscope/instrumentation.py

import re
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Callable
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
except Exception:
    OTLPSpanExporter = None
from agentscope.constants import OTEL_GENAI_SPEC_VERSION, CAPTURE_CONTENT

# Setup provider and tracer global references
_tracer = None

def init_tracer(service_name: str = "agentscope", endpoint: str = "localhost:4317") -> trace.Tracer:
    """Initializes the global OpenTelemetry tracer."""
    global _tracer
    
    # Define resource info
    resource = Resource(attributes={
        "service.name": service_name,
        "gen_ai.spec.version": OTEL_GENAI_SPEC_VERSION
    })
    
    provider = TracerProvider(resource=resource)
    
    # Configure OTLP exporter (gRPC default)
    if OTLPSpanExporter is not None:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            span_processor = BatchSpanProcessor(otlp_exporter)
            provider.add_span_processor(span_processor)
        except Exception as e:
            print(f"Warning: Failed to initialize OTLP exporter: {e}. Falling back to console/mock tracing.")
        
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    return _tracer

def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        # Fallback to default tracer if not initialized
        _tracer = trace.get_tracer("agentscope")
    return _tracer

def sanitize_value(key: str, value: Any) -> Any:
    """Redacts values that look like secrets/keys based on key name."""
    secret_keywords = ["key", "secret", "token", "password", "auth", "credential", "private"]
    key_lower = key.lower()
    if any(kw in key_lower for kw in secret_keywords):
        return "[REDACTED]"
    
    # Also redact if string matches common secret patterns (like OpenAI API keys: sk-...)
    if isinstance(value, str):
        if re.search(r"sk-[a-zA-Z0-9]{32,}", value) or re.search(r"ghp_[a-zA-Z0-9]{36}", value):
            return "[REDACTED]"
            
    return value

def sanitize_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitizes a dictionary of attributes."""
    sanitized = {}
    for k, v in d.items():
        if isinstance(v, dict):
            sanitized[k] = sanitize_dict(v)
        else:
            sanitized[k] = sanitize_value(k, v)
    return sanitized

class LLMCallContext:
    def __init__(self, span: trace.Span):
        self.span = span
        self.input_tokens = 0
        self.output_tokens = 0
        self.response_model = None
        self.completion = None

@contextmanager
def instrument_llm_call(model: str, messages: List[Dict[str, str]], **kwargs):
    """
    Context manager that emits an OTel span with gen_ai.* attributes around an LLM API call.
    Usage:
        with instrument_llm_call(model, messages, temp=0.7) as ctx:
            # perform real/mock LLM call
            ctx.input_tokens = 15
            ctx.output_tokens = 25
            ctx.response_model = "gpt-4o"
            ctx.completion = "Response text"
    """
    tracer = get_tracer()
    span_name = f"chat {model}"
    
    # Base gen_ai attributes based on conventions
    attributes = {
        "gen_ai.request.model": model,
        "gen_ai.system": kwargs.get("system", "mock"),
        "gen_ai.operation.name": "chat",
        "otel.library.name": "agentscope"
    }
    
    # Record non-secret kwargs as request metadata
    sanitized_kwargs = sanitize_dict(kwargs)
    for k, v in sanitized_kwargs.items():
        if k not in ["system"]:
            attributes[f"gen_ai.request.{k}"] = str(v)
            
    if CAPTURE_CONTENT:
        # Sanitize and capture prompt messages
        sanitized_messages = [sanitize_dict(m) for m in messages]
        attributes["gen_ai.request.content"] = str(sanitized_messages)
        
    with tracer.start_as_current_span(span_name, attributes=attributes) as span:
        ctx = LLMCallContext(span)
        yield ctx
        
        # Populate post-call attributes
        span.set_attribute("gen_ai.response.model", ctx.response_model or model)
        span.set_attribute("gen_ai.usage.input_tokens", ctx.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", ctx.output_tokens)
        
        if CAPTURE_CONTENT and ctx.completion:
            span.set_attribute("gen_ai.response.content", str(sanitize_value("completion", ctx.completion)))

def instrument_tool_call(tool_name: str, args: Dict[str, Any], result: Any) -> trace.Span:
    """
    Emits a child span for a tool execution under the current active span.
    """
    tracer = get_tracer()
    span_name = f"tool {tool_name}"
    
    sanitized_args = sanitize_dict(args)
    sanitized_result = sanitize_value("result", result)
    
    attributes = {
        "tool.name": tool_name,
        "tool.args": str(sanitized_args)
    }
    if CAPTURE_CONTENT:
        attributes["tool.result"] = str(sanitized_result)
        
    # Start and immediately finish the span since tool calls are usually recorded after completion,
    # or wrapped. Here we emit it as a completed child of the active span context.
    with tracer.start_as_current_span(span_name, attributes=attributes) as span:
        return span

@contextmanager
def instrument_tool_call_timed(tool_name: str, args: Dict[str, Any]):
    """
    Context-manager variant of instrument_tool_call for when you want the span to
    cover the tool's actual execution time (the plain function emits a zero-duration
    span recorded after the fact). Set ctx-style result via span.set_attribute.

    Usage:
        with instrument_tool_call_timed("run_tests", {"path": "tests/"}) as span:
            result = run_tests()
            if CAPTURE_CONTENT:
                span.set_attribute("tool.result", str(sanitize_value("result", result)))
    """
    tracer = get_tracer()
    attributes = {
        "tool.name": tool_name,
        "tool.args": str(sanitize_dict(args)),
    }
    with tracer.start_as_current_span(f"tool {tool_name}", attributes=attributes) as span:
        yield span


@contextmanager
def dispatch_subagent(parent_span: Optional[trace.Span], agent_role: str, task: str):
    """
    Context manager that creates a new subagent span as a child of the calling agent's span.
    Allows constructing nested/parallel agent hierarchies.
    """
    tracer = get_tracer()
    span_name = f"agent {agent_role}"
    
    # We can pass context explicitly, or OTel will automatically pick up the current active context.
    # To be explicit, we set context if parent_span is provided.
    context = None
    if parent_span:
        context = trace.set_span_in_context(parent_span)
        
    attributes = {
        "agent.role": agent_role,
        "agent.task": task
    }
    
    with tracer.start_as_current_span(span_name, context=context, attributes=attributes) as span:
        yield span
