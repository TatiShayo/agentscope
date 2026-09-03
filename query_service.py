# query_service.py
"""
HTTP query service for AgentScope.
Exposes REST endpoints for cost aggregation, trace hierarchy tree rendering
(Mermaid, JSON, ASCII), and model pricing metadata.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import json
import logging
from typing import Any, Dict

from agentscope.cost import aggregate_cost, aggregate_cost_from_spans
from agentscope.constants import MODEL_PRICING, DEFAULT_QUERY_SERVICE_PORT
from agentscope.tree import fetch_and_build_tree, render_trace
from agentscope.exporter import build_trace_tree, export_trace_tree_json, export_mermaid_sequence, export_mermaid_flowchart, render_console_tree

logger = logging.getLogger("agentscope.query_service")


class QueryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        if parsed_url.path == "/health":
            self.send_json_response({"status": "ok", "service": "agentscope", "version": "3.2.0"})

        elif parsed_url.path == "/models":
            self.send_json_response({"models": MODEL_PRICING, "count": len(MODEL_PRICING)})

        elif parsed_url.path == "/cost":
            trace_id = query_params.get("trace_id", [None])[0]
            if not trace_id:
                self.send_error_response(400, "Missing required query parameter: 'trace_id'")
                return
            try:
                result = aggregate_cost(trace_id)
                self.send_json_response(result)
            except ValueError as e:
                self.send_error_response(404, str(e))
            except ConnectionError as e:
                self.send_error_response(503, str(e))
            except Exception as e:
                self.send_error_response(500, f"Error calculating cost: {str(e)}")

        elif parsed_url.path == "/tree":
            trace_id = query_params.get("trace_id", [None])[0]
            fmt = query_params.get("format", ["json"])[0]

            if not trace_id:
                self.send_error_response(400, "Missing required query parameter: 'trace_id'")
                return

            try:
                from agentscope.tree import fetch_trace_data
                trace_data = fetch_trace_data(trace_id)
                spans = trace_data.get("spans", [])

                if fmt in ("json", "dict"):
                    self.send_json_response(json.loads(export_trace_tree_json(spans)))
                elif fmt in ("mermaid", "mermaid_sequence", "sequence"):
                    self.send_text_response(export_mermaid_sequence(spans), content_type="text/vnd.mermaid")
                elif fmt in ("flowchart", "mermaid_flowchart"):
                    self.send_text_response(export_mermaid_flowchart(spans), content_type="text/vnd.mermaid")
                elif fmt in ("ascii", "console", "text"):
                    self.send_text_response(render_console_tree(spans), content_type="text/plain")
                else:
                    self.send_error_response(400, f"Unsupported format: {fmt}. Options: json, mermaid, flowchart, ascii")
            except ValueError as e:
                self.send_error_response(404, str(e))
            except ConnectionError as e:
                self.send_error_response(503, str(e))
            except Exception as e:
                self.send_error_response(500, f"Error fetching trace tree: {str(e)}")

        else:
            self.send_error_response(
                404,
                "Endpoint not found. Valid endpoints: GET /health, GET /models, GET /cost?trace_id=<id>, GET /tree?trace_id=<id>&format=<fmt>"
            )

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self.send_error_response(400, "Missing request body in POST request.")
            return

        try:
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
        except Exception as e:
            self.send_error_response(400, f"Invalid JSON in request body: {e}")
            return

        if parsed_url.path == "/cost":
            try:
                spans = data.get("spans") if isinstance(data, dict) else data
                if not isinstance(spans, list):
                    self.send_error_response(400, "Body must contain a list of spans or {'spans': [...]}")
                    return
                trace_id = data.get("trace_id") if isinstance(data, dict) else None
                result = aggregate_cost_from_spans(spans, trace_id=trace_id)
                self.send_json_response(result)
            except Exception as e:
                self.send_error_response(500, f"Error calculating cost: {e}")

        elif parsed_url.path == "/tree":
            fmt = query_params.get("format", ["json"])[0]
            try:
                spans = data.get("spans") if isinstance(data, dict) else data
                if not isinstance(spans, list):
                    self.send_error_response(400, "Body must contain a list of spans or {'spans': [...]}")
                    return

                if fmt in ("json", "dict"):
                    self.send_json_response(json.loads(export_trace_tree_json(spans)))
                elif fmt in ("mermaid", "mermaid_sequence", "sequence"):
                    self.send_text_response(export_mermaid_sequence(spans), content_type="text/vnd.mermaid")
                elif fmt in ("flowchart", "mermaid_flowchart"):
                    self.send_text_response(export_mermaid_flowchart(spans), content_type="text/vnd.mermaid")
                elif fmt in ("ascii", "console", "text"):
                    self.send_text_response(render_console_tree(spans), content_type="text/plain")
                else:
                    self.send_error_response(400, f"Unsupported format: {fmt}. Options: json, mermaid, flowchart, ascii")
            except Exception as e:
                self.send_error_response(500, f"Error rendering tree: {e}")
        else:
            self.send_error_response(404, "Endpoint not found for POST. Valid endpoints: POST /cost, POST /tree")

    def send_json_response(self, data: Any, status_code: int = 200) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def send_text_response(self, text: str, status_code: int = 200, content_type: str = "text/plain") -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def send_error_response(self, code: int, message: str) -> None:
        self.send_json_response({"error": message, "code": code}, status_code=code)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard HTTP logs in test environments unless debugging
        pass


def run_server(port: int = DEFAULT_QUERY_SERVICE_PORT, host: str = "0.0.0.0") -> None:
    server = HTTPServer((host, port), QueryHandler)
    print(f"AgentScope Query Service running on http://{host}:{port}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down query server.")
        server.server_close()


if __name__ == "__main__":
    import sys
    port = DEFAULT_QUERY_SERVICE_PORT
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run_server(port)
