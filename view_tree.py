# view_tree.py
"""
CLI utility to fetch and display an AgentScope trace tree from Jaeger.
Supports ASCII console tree, Mermaid sequence diagram, and JSON outputs.
"""

import sys
from agentscope.tree import fetch_trace_data, render_trace


def main():
    if len(sys.argv) < 2:
        print("Usage: python view_tree.py <trace_id> [format: ascii|mermaid|flowchart|json] [jaeger_url]")
        sys.exit(1)

    trace_id = sys.argv[1]
    fmt = sys.argv[2] if len(sys.argv) > 2 else "ascii"
    jaeger_url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:16686"

    try:
        trace_data = fetch_trace_data(trace_id, jaeger_url=jaeger_url)
        spans = trace_data.get("spans", [])
        output = render_trace(spans, output_format=fmt, title=f"Trace {trace_id}")
        print(output)
    except Exception as e:
        print(f"Error fetching or rendering trace: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
