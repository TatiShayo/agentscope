# tests/test_tree.py
"""
Unit tests for agentscope.tree utilities:
Tree reconstruction, critical path analysis, node querying, and multi-format rendering.
"""

import json
import os
import sys
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentscope.tree import (
    fetch_trace_data,
    fetch_and_build_tree,
    render_trace,
    find_nodes,
    get_critical_path,
)
from agentscope.exporter import build_trace_tree, SpanNode


@pytest.fixture
def complex_tree_spans():
    return [
        {
            "spanID": "root",
            "operationName": "Lead Orchestration",
            "startTime": 1000000,
            "duration": 100000,
            "tags": [{"key": "agent.role", "value": "LeadAgent"}],
        },
        {
            "spanID": "branch-dev",
            "operationName": "agent Developer",
            "startTime": 1010000,
            "duration": 40000,
            "references": [{"refType": "CHILD_OF", "spanID": "root"}],
            "tags": [{"key": "agent.role", "value": "Developer"}],
        },
        {
            "spanID": "llm-dev",
            "operationName": "chat gpt-4o",
            "startTime": 1015000,
            "duration": 25000,
            "references": [{"refType": "CHILD_OF", "spanID": "branch-dev"}],
            "tags": [
                {"key": "gen_ai.request.model", "value": "gpt-4o"},
                {"key": "gen_ai.usage.input_tokens", "value": 300},
                {"key": "gen_ai.usage.output_tokens", "value": 150},
            ],
        },
        {
            "spanID": "branch-sec",
            "operationName": "agent Security",
            "startTime": 1055000,
            "duration": 35000,
            "references": [{"refType": "CHILD_OF", "spanID": "root"}],
            "tags": [{"key": "agent.role", "value": "SecurityAgent"}],
        },
        {
            "spanID": "llm-sec",
            "operationName": "chat claude-3-5-sonnet",
            "startTime": 1060000,
            "duration": 20000,
            "references": [{"refType": "CHILD_OF", "spanID": "branch-sec"}],
            "tags": [
                {"key": "gen_ai.request.model", "value": "claude-3-5-sonnet"},
                {"key": "gen_ai.usage.input_tokens", "value": 400},
                {"key": "gen_ai.usage.output_tokens", "value": 200},
            ],
        },
    ]


class TestTreeReconstructionAndQueries:
    def test_find_nodes_by_role(self, complex_tree_spans):
        roots = build_trace_tree(complex_tree_spans)
        dev_nodes = find_nodes(roots, lambda n: n.role == "Developer")
        assert len(dev_nodes) == 1
        assert dev_nodes[0].span_id == "branch-dev"

        sec_nodes = find_nodes(roots, lambda n: n.role == "SecurityAgent")
        assert len(sec_nodes) == 1
        assert sec_nodes[0].span_id == "branch-sec"

    def test_find_nodes_by_model(self, complex_tree_spans):
        roots = build_trace_tree(complex_tree_spans)
        gpt_nodes = find_nodes(roots, lambda n: n.model == "gpt-4o")
        assert len(gpt_nodes) == 1
        assert gpt_nodes[0].span_id == "llm-dev"

    def test_get_critical_path(self, complex_tree_spans):
        roots = build_trace_tree(complex_tree_spans)
        crit_path = get_critical_path(roots)
        assert len(crit_path) >= 2
        assert crit_path[0].span_id == "root"
        # Total latency of root -> dev -> llm is greater than root -> sec -> llm
        assert any(n.span_id == "branch-dev" for n in crit_path)

    def test_render_trace_all_formats(self, complex_tree_spans):
        seq = render_trace(complex_tree_spans, output_format="mermaid")
        assert "sequenceDiagram" in seq

        fc = render_trace(complex_tree_spans, output_format="flowchart")
        assert "graph TD" in fc

        js = render_trace(complex_tree_spans, output_format="json")
        data = json.loads(js)
        assert data["root_count"] == 1

        ascii_out = render_trace(complex_tree_spans, output_format="ascii")
        assert "Lead Orchestration" in ascii_out

    @patch("urllib.request.urlopen")
    def test_fetch_and_build_tree_mocked(self, mock_urlopen, complex_tree_spans):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"data": [{"traceID": "t1", "spans": complex_tree_spans}]}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        roots = fetch_and_build_tree("t1")
        assert len(roots) == 1
        assert roots[0].span_id == "root"
