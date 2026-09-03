# agentscope/tree.py
"""
Trace tree reconstruction and query utilities for AgentScope.
Extracts hierarchical dependency graphs from Jaeger traces or in-memory spans.
"""

import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Callable

from agentscope.constants import DEFAULT_JAEGER_URL
from agentscope.exporter import (
    SpanNode,
    build_trace_tree,
    export_trace_tree_json,
    export_mermaid_sequence,
    export_mermaid_flowchart,
    render_console_tree,
)


def fetch_trace_data(
    trace_id: str,
    jaeger_url: str = DEFAULT_JAEGER_URL,
    timeout_seconds: float = 5.0
) -> Dict[str, Any]:
    """Fetches full trace JSON from Jaeger backend."""
    if not trace_id or not trace_id.strip():
        raise ValueError("trace_id must not be empty.")

    clean_id = trace_id.strip()
    url = f"{jaeger_url.rstrip('/')}/api/traces/{clean_id}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentScope-TreeViewer/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to connect to Jaeger at {url}: {e}")
    except Exception as e:
        raise ValueError(f"Error fetching trace '{clean_id}' from Jaeger: {e}")

    if not data.get("data") or len(data["data"]) == 0:
        raise ValueError(f"Trace ID '{clean_id}' not found in Jaeger.")

    return data["data"][0]


def fetch_and_build_tree(
    trace_id: str,
    jaeger_url: str = DEFAULT_JAEGER_URL,
    timeout_seconds: float = 5.0
) -> List[SpanNode]:
    """Fetches trace from Jaeger and reconstructs the hierarchical SpanNode forest."""
    trace_data = fetch_trace_data(trace_id, jaeger_url=jaeger_url, timeout_seconds=timeout_seconds)
    spans = trace_data.get("spans", [])
    return build_trace_tree(spans)


def render_trace(
    spans: List[Any],
    output_format: str = "mermaid_sequence",
    title: str = "AgentScope Execution Trace"
) -> str:
    """
    Renders trace in the specified format:
    - 'mermaid_sequence' or 'mermaid'
    - 'mermaid_flowchart' or 'flowchart'
    - 'json'
    - 'ascii' or 'console'
    """
    fmt = output_format.lower().strip()
    if fmt in ("mermaid_sequence", "mermaid", "sequence"):
        return export_mermaid_sequence(spans, title=title)
    elif fmt in ("mermaid_flowchart", "flowchart"):
        return export_mermaid_flowchart(spans, title=title)
    elif fmt in ("json", "dict"):
        return export_trace_tree_json(spans)
    elif fmt in ("ascii", "console", "tree"):
        return render_console_tree(spans)
    else:
        raise ValueError(f"Unsupported render format: '{output_format}'. Use 'mermaid_sequence', 'mermaid_flowchart', 'json', or 'ascii'.")


def find_nodes(roots: List[SpanNode], predicate: Callable[[SpanNode], bool]) -> List[SpanNode]:
    """Recursively searches for nodes in the tree matching the given predicate function."""
    matches: List[SpanNode] = []

    def walk(node: SpanNode) -> None:
        if predicate(node):
            matches.append(node)
        for child in node.children:
            walk(child)

    for root in roots:
        walk(root)

    return matches


def get_critical_path(roots: List[SpanNode]) -> List[SpanNode]:
    """Identifies the longest latency execution path in the span tree."""
    longest_path: List[SpanNode] = []
    max_duration: float = -1.0

    def dfs(node: SpanNode, current_path: List[SpanNode]) -> None:
        nonlocal longest_path, max_duration
        new_path = current_path + [node]
        if not node.children:
            total_dur = sum(n.duration_ms for n in new_path)
            if total_dur > max_duration:
                max_duration = total_dur
                longest_path = new_path
            return
        for child in node.children:
            dfs(child, new_path)

    for root in roots:
        dfs(root, [])

    return longest_path
