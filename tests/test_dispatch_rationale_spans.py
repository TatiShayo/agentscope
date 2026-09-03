import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentscope.rationale import log_dispatch_rationale, read_rationale_log
from agentscope.constants import MODEL_PRICING

def test_frontier_2026_pricing():
    assert "gemini-2.5-pro" in MODEL_PRICING
    assert "gemini-2.5-flash" in MODEL_PRICING
    assert "deepseek-v4" in MODEL_PRICING
    assert MODEL_PRICING["gemini-2.5-pro"]["input"] > 0
    assert MODEL_PRICING["deepseek-v4"]["output"] > 0

def test_dispatch_rationale_span_event_capture():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test-agentscope")
    
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        log_file = tf.name

    try:
        with tracer.start_as_current_span("orchestrator_turn") as span:
            entry = log_dispatch_rationale(
                rationale="Dispatching security agent for reentrancy verification",
                action="dispatch_subagent",
                target_agent="security_agent",
                cycle=1,
                log_path=log_file
            )
            assert entry["action"] == "dispatch_subagent"
            assert entry["target_agent"] == "security_agent"

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        events = spans[0].events
        assert len(events) >= 1
        ev = next((e for e in events if e.name == "dispatch_rationale"), None)
        assert ev is not None
        assert ev.attributes["action"] == "dispatch_subagent"
        assert ev.attributes["target_agent"] == "security_agent"
        assert ev.attributes["cycle"] == 1
        
        # Verify file contents
        entries = read_rationale_log(log_path=log_file)
        assert len(entries) == 1
        assert entries[0]["target_agent"] == "security_agent"
    finally:
        if os.path.exists(log_file):
            os.unlink(log_file)
