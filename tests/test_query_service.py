# tests/test_query_service.py
"""
Integration tests for AgentScope query_service HTTP endpoints.
Tests /health, /models, GET /cost, POST /cost, GET /tree, and POST /tree.
"""

import json
import os
import sys
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from query_service import QueryHandler


@pytest.fixture(scope="module")
def http_server():
    """Starts an ephemeral HTTP server on localhost with an assigned port."""
    server = HTTPServer(("127.0.0.1", 0), QueryHandler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


class TestQueryServiceEndpoints:
    def test_health_endpoint(self, http_server):
        url = f"{http_server}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ok"
            assert data["service"] == "agentscope"
            assert "version" in data

    def test_models_endpoint(self, http_server):
        url = f"{http_server}/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "models" in data
            assert data["count"] > 10
            assert "gpt-4o" in data["models"]
            assert "claude-3-5-sonnet" in data["models"]

    def test_cost_missing_trace_id_returns_400(self, http_server):
        url = f"{http_server}/cost"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req)
            pytest.fail("Expected HTTP 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read().decode("utf-8"))
            assert "error" in body

    def test_post_cost_with_spans_payload(self, http_server):
        url = f"{http_server}/cost"
        payload = {
            "trace_id": "test_trace_http",
            "spans": [
                {
                    "name": "chat gpt-4o",
                    "tags": {
                        "gen_ai.request.model": "gpt-4o",
                        "gen_ai.usage.input_tokens": 1000,
                        "gen_ai.usage.output_tokens": 500,
                    }
                }
            ]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["trace_id"] == "test_trace_http"
            assert data["total_tokens"] == 1500
            assert data["total_cost_usd"] > 0

    def test_post_tree_with_json_format(self, http_server):
        url = f"{http_server}/tree?format=json"
        payload = {
            "spans": [
                {
                    "spanID": "root-1",
                    "operationName": "Lead Agent",
                    "tags": [{"key": "agent.role", "value": "Lead"}]
                }
            ]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["root_count"] == 1
            assert data["roots"][0]["span_id"] == "root-1"

    def test_post_tree_with_mermaid_format(self, http_server):
        url = f"{http_server}/tree?format=mermaid"
        payload = {
            "spans": [
                {
                    "spanID": "root-1",
                    "operationName": "Lead Agent",
                    "tags": [{"key": "agent.role", "value": "Lead"}]
                }
            ]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "sequenceDiagram" in content

    def test_post_tree_with_ascii_format(self, http_server):
        url = f"{http_server}/tree?format=ascii"
        payload = {
            "spans": [
                {
                    "spanID": "root-1",
                    "operationName": "Lead Agent",
                    "tags": [{"key": "agent.role", "value": "Lead"}]
                }
            ]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "Lead Agent" in content

    def test_not_found_endpoint(self, http_server):
        url = f"{http_server}/unknown_route"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req)
            pytest.fail("Expected HTTP 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
