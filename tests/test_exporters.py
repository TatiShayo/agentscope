# tests/test_exporters.py
"""
Unit tests for AgentScope resilient exporters and visualization generators
(OTLP retry backoff, in-memory buffering, Mermaid diagrams, JSON tree, ASCII console).
"""

import json
import os
import sys
import pytest
from unittest.mock import MagicMock
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentscope.exporter import (
    ExponentialBackoff,
    ResilientSpanExporter,
    SpanNode,
    build_trace_tree,
    export_trace_tree_json,
    export_mermaid_sequence,
    export_mermaid_flowchart,
    render_console_tree,
)


class TestExponentialBackoff:
    def test_backoff_delays(self):
        eb = ExponentialBackoff(initial_delay=0.1, max_delay=1.0, multiplier=2.0, jitter=False)
        assert eb.get_delay(0) == 0.1
        assert eb.get_delay(1) == 0.2
        assert eb.get_delay(2) == 0.4
        assert eb.get_delay(3) == 0.8
        assert eb.get_delay(4) == 1.0  # Capped at max_delay

    def test_backoff_with_jitter(self):
        eb = ExponentialBackoff(initial_delay=0.5, max_delay=2.0, multiplier=2.0, jitter=True)
        for _ in range(10):
            d = eb.get_delay(1)
            assert 0.0 <= d <= 1.0


class TestResilientSpanExporter:
    def test_successful_export_delegation(self):
        mock_underlying = MagicMock(spec=SpanExporter)
        mock_underlying.export.return_value = SpanExportResult.SUCCESS

        exporter = ResilientSpanExporter(underlying_exporter=mock_underlying, max_retries=2)
        mock_span = MagicMock()
        mock_span.name = "test_span"

        res = exporter.export([mock_span])
        assert res == SpanExportResult.SUCCESS
        assert mock_underlying.export.call_count == 1
        assert len(exporter.get_buffered_spans()) == 0

    def test_retry_on_failure_and_eventual_success(self):
        mock_underlying = MagicMock(spec=SpanExporter)
        # Fail first attempt, succeed on second attempt
        mock_underlying.export.side_effect = [SpanExportResult.FAILURE, SpanExportResult.SUCCESS]

        exporter = ResilientSpanExporter(
            underlying_exporter=mock_underlying,
            max_retries=3,
            initial_backoff=0.01,
            max_backoff=0.05,
        )
        mock_span = MagicMock()

        res = exporter.export([mock_span])
        assert res == SpanExportResult.SUCCESS
        assert mock_underlying.export.call_count == 2
        assert len(exporter.get_buffered_spans()) == 0

    def test_buffering_when_all_retries_fail(self):
        mock_underlying = MagicMock(spec=SpanExporter)
        mock_underlying.export.side_effect = Exception("Network unreachable")

        exporter = ResilientSpanExporter(
            underlying_exporter=mock_underlying,
            max_retries=2,
            initial_backoff=0.005,
            max_backoff=0.01,
        )
        mock_span = MagicMock()
        mock_span.name = "failed_span"
        mock_span.context.trace_id = 0x1234

        res = exporter.export([mock_span])
        assert res == SpanExportResult.FAILURE
        # Spans should be preserved in internal buffer for next cycle
        buffered = exporter.get_buffered_spans()
        assert len(buffered) == 1
        assert buffered[0] == mock_span

    def test_shutdown_lifecycle(self):
        mock_underlying = MagicMock(spec=SpanExporter)
        exporter = ResilientSpanExporter(underlying_exporter=mock_underlying)
        exporter.shutdown()
        assert exporter._is_shutdown is True
        # Export after shutdown returns FAILURE
        assert exporter.export([MagicMock()]) == SpanExportResult.FAILURE


class TestTraceVisualizations:
    @pytest.fixture
    def sample_trace_spans(self):
        return [
            {
                "spanID": "root-1",
                "operationName": "Lead Orchestration",
                "startTime": 1000000,
                "duration": 50000,
                "tags": [
                    {"key": "agent.role", "value": "Lead"},
                ]
            },
            {
                "spanID": "child-dev",
                "operationName": "agent Developer",
                "startTime": 1010000,
                "duration": 20000,
                "references": [{"refType": "CHILD_OF", "spanID": "root-1"}],
                "tags": [
                    {"key": "agent.role", "value": "Developer"},
                ]
            },
            {
                "spanID": "llm-dev",
                "operationName": "chat gpt-4o",
                "startTime": 1012000,
                "duration": 15000,
                "references": [{"refType": "CHILD_OF", "spanID": "child-dev"}],
                "tags": [
                    {"key": "gen_ai.request.model", "value": "gpt-4o"},
                    {"key": "gen_ai.usage.input_tokens", "value": 500},
                    {"key": "gen_ai.usage.output_tokens", "value": 300},
                ]
            },
            {
                "spanID": "tool-file",
                "operationName": "tool write_file",
                "startTime": 1028000,
                "duration": 2000,
                "references": [{"refType": "CHILD_OF", "spanID": "child-dev"}],
                "tags": [
                    {"key": "tool.name", "value": "write_file"},
                ]
            }
        ]

    def test_build_trace_tree(self, sample_trace_spans):
        roots = build_trace_tree(sample_trace_spans)
        assert len(roots) == 1
        root = roots[0]
        assert root.span_id == "root-1"
        assert len(root.children) == 1

        dev_child = root.children[0]
        assert dev_child.span_id == "child-dev"
        assert len(dev_child.children) == 2

    def test_export_trace_tree_json(self, sample_trace_spans):
        json_str = export_trace_tree_json(sample_trace_spans)
        data = json.loads(json_str)
        assert data["root_count"] == 1
        assert "summary" in data
        assert data["summary"]["total_tokens"] == 800
        assert data["roots"][0]["span_id"] == "root-1"

    def test_export_mermaid_sequence(self, sample_trace_spans):
        mermaid = export_mermaid_sequence(sample_trace_spans, title="Test Pipeline")
        assert "sequenceDiagram" in mermaid
        assert "Lead Orchestrator" in mermaid
        assert "Developer Agent" in mermaid
        assert "Tool: write_file" in mermaid
        assert "LLM (gpt-4o)" in mermaid

    def test_export_mermaid_flowchart(self, sample_trace_spans):
        flowchart = export_mermaid_flowchart(sample_trace_spans, title="Flowchart Test")
        assert "graph TD" in flowchart
        assert "root-1" in flowchart
        assert "child-dev" in flowchart
        assert "root-1 --> child-dev" in flowchart

    def test_render_console_tree(self, sample_trace_spans):
        ascii_tree = render_console_tree(sample_trace_spans)
        assert "Lead Orchestration" in ascii_tree
        assert "agent Developer" in ascii_tree
        assert "chat gpt-4o" in ascii_tree
        assert "tokens=500+300" in ascii_tree
