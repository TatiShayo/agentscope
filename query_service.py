# query_service.py

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import json
from agentscope.cost import aggregate_cost

class QueryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        
        if parsed_url.path == "/cost":
            query_params = urllib.parse.parse_qs(parsed_url.query)
            trace_id = query_params.get("trace_id", [None])[0]
            
            if not trace_id:
                self.send_error_response(400, "Missing required query parameter: 'trace_id'")
                return
                
            try:
                # Call cost aggregator
                result = aggregate_cost(trace_id)
                self.send_json_response(result)
            except Exception as e:
                self.send_error_response(500, f"Error calculating cost: {str(e)}")
        else:
            self.send_error_response(404, "Endpoint not found. Use GET /cost?trace_id=<id>")

    def send_json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        # Enable CORS for ease of access
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_error_response(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))

def run_server(port=8000):
    server = HTTPServer(("0.0.0.0", port), QueryHandler)
    print(f"Cost query service running on port {port}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()

if __name__ == "__main__":
    import sys
    port = 8000
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run_server(port)
