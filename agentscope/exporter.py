# agentscope/exporter.py
"""
Resilient exporters and visualization engines for AgentScope traces.
Includes OTLP buffering with exponential retry backoff, and exporters for
Mermaid diagrams (sequence & flowchart), JSON hierarchical trees, and ASCII console views.
"""

import json
import logging
import random
import threading
import time
from collections import deque
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import (
    SpanExporter,
    SpanExportResult,
)

from agentscope.cost import _extract_tags_dict, _extract_span_name, aggregate_cost_from_spans

logger = logging.getLogger("agentscope.exporter")


class ExponentialBackoff:
    """Calculates exponential backoff delays with full jitter."""
    def __init__(
        self,
        initial_delay: float = 0.1,
        max_delay: float = 5.0,
        multiplier: float = 2.0,
        jitter: bool = True,
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        delay = min(self.max_delay, self.initial_delay * (self.multiplier ** attempt))
        if self.jitter:
            delay = random.uniform(0, delay)
        return delay


class ResilientSpanExporter(SpanExporter):
    """
    Wraps an underlying SpanExporter with:
    - In-memory ring buffering during network interruptions
    - Exponential retry backoff
    - Configurable retry attempts
    - Thread-safe queue flushing
    """
    def __init__(
        self,
        underlying_exporter: Optional[SpanExporter] = None,
        max_buffer_size: int = 2048,
        max_retries: int = 3,
        initial_backoff: float = 0.1,
        max_backoff: float = 2.0,
        fallback_to_console: bool = False,
    ):
        self.underlying_exporter = underlying_exporter
        self.max_buffer_size = max_buffer_size
        self.max_retries = max_retries
        self.backoff = ExponentialBackoff(
            initial_delay=initial_backoff,
            max_delay=max_backoff,
        )
        self.fallback_to_console = fallback_to_console
        self.buffer: deque = deque(maxlen=max_buffer_size)
        self._lock = threading.RLock()
        self._is_shutdown = False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self._lock:
            if self._is_shutdown:
                return SpanExportResult.FAILURE

            # Combine any previously buffered spans with new spans
            all_spans: List[ReadableSpan] = list(self.buffer) + list(spans)
            self.buffer.clear()

            if not all_spans:
                return SpanExportResult.SUCCESS

            if self.underlying_exporter is None:
                # Retain in buffer for testing or inspection
                for s in all_spans:
                    self.buffer.append(s)
                return SpanExportResult.SUCCESS

            # Attempt export with retries
            for attempt in range(self.max_retries + 1):
                try:
                    result = self.underlying_exporter.export(all_spans)
                    if result == SpanExportResult.SUCCESS:
                        return SpanExportResult.SUCCESS
                except Exception as exc:
                    logger.warning(
                        "Export failed on attempt %d/%d: %s",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                    )

                if attempt < self.max_retries:
                    delay = self.backoff.get_delay(attempt)
                    time.sleep(delay)

            # If all retries fail, buffer failed spans for next flush cycle
            for s in all_spans:
                self.buffer.append(s)

            if self.fallback_to_console:
                for s in all_spans:
                    print(f"[AgentScope Fallback] Span: {s.name} (TraceID={s.context.trace_id:032x})")

            return SpanExportResult.FAILURE

    def get_buffered_spans(self) -> List[ReadableSpan]:
        """Returns currently buffered spans."""
        with self._lock:
            return list(self.buffer)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        with self._lock:
            if self.underlying_exporter and hasattr(self.underlying_exporter, "force_flush"):
                return bool(self.underlying_exporter.force_flush(timeout_millis))
            return True

    def shutdown(self) -> None:
        with self._lock:
            self._is_shutdown = True
            if self.underlying_exporter:
                self.underlying_exporter.shutdown()


# ============================================================================
# Hierarchy Tree Construction & Serialization
# ============================================================================

class SpanNode:
    """Represents a node in the hierarchical agent trace tree."""
    def __init__(self, span_id: str, name: str, data: Dict[str, Any]):
        self.span_id = span_id
        self.name = name
        self.data = data
        self.parent_id: Optional[str] = None
        self.children: List["SpanNode"] = []
        self.start_time_ns: int = 0
        self.end_time_ns: int = 0
        self.duration_ms: float = 0.0
        self.status: str = "OK"
        self.role: Optional[str] = None
        self.model: Optional[str] = None
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Converts node and recursive children into nested dictionary."""
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "role": self.role,
            "model": self.model,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "cost_usd": self.cost_usd,
            "attributes": self.data.get("attributes", {}),
            "children": [c.to_dict() for c in self.children],
        }


def build_trace_tree(spans: Sequence[Any]) -> List[SpanNode]:
    """
    Constructs a forest (roots with children) of SpanNode trees from any sequence of spans.
    Handles OTel ReadableSpans, Jaeger JSON spans, and custom dictionaries.
    """
    span_nodes: Dict[str, SpanNode] = {}
    parent_map: Dict[str, Optional[str]] = {}

    for s in spans:
        tags = _extract_tags_dict(s)
        name = _extract_span_name(s)

        # Extract span ID and parent ID
        span_id = None
        parent_id = None
        start_ns = 0
        end_ns = 0
        status_str = "OK"

        if hasattr(s, "context") and hasattr(s.context, "span_id"):
            span_id = f"{s.context.span_id:016x}"
            if hasattr(s, "parent") and s.parent and hasattr(s.parent, "span_id"):
                parent_id = f"{s.parent.span_id:016x}"
            start_ns = getattr(s, "start_time", 0) or 0
            end_ns = getattr(s, "end_time", 0) or 0
            if hasattr(s, "status") and hasattr(s.status, "status_code"):
                status_str = "ERROR" if s.status.status_code.name == "ERROR" else "OK"
        elif isinstance(s, dict):
            span_id = str(s.get("spanID") or s.get("span_id") or s.get("id") or id(s))
            # Jaeger references
            refs = s.get("references", [])
            for ref in refs:
                if isinstance(ref, dict) and ref.get("refType") == "CHILD_OF":
                    parent_id = str(ref.get("spanID"))
                    break
            if not parent_id:
                parent_id = s.get("parent_id") or s.get("parentId")
            start_ns = int(s.get("startTime", s.get("start_time_ns", 0))) * 1000  # Jaeger is in microseconds
            duration_us = int(s.get("duration", 0))
            end_ns = start_ns + (duration_us * 1000)

        if not span_id:
            span_id = f"span_{len(span_nodes)}"

        node = SpanNode(span_id=span_id, name=name, data={"attributes": tags, "raw": s})
        node.parent_id = str(parent_id) if parent_id else None
        node.start_time_ns = start_ns
        node.end_time_ns = end_ns
        if end_ns > start_ns and start_ns > 0:
            node.duration_ms = (end_ns - start_ns) / 1_000_000.0

        node.status = status_str
        node.role = tags.get("agent.role") or tags.get("agent_role")
        node.model = tags.get("gen_ai.response.model") or tags.get("gen_ai.request.model")
        node.input_tokens = int(tags.get("gen_ai.usage.input_tokens", 0) or 0)
        node.output_tokens = int(tags.get("gen_ai.usage.output_tokens", 0) or 0)

        # Single span cost
        if node.input_tokens > 0 or node.output_tokens > 0:
            cost_info = aggregate_cost_from_spans([s])
            node.cost_usd = cost_info.get("total_cost_usd", 0.0)

        span_nodes[span_id] = node
        parent_map[span_id] = node.parent_id

    # Assemble hierarchy
    roots: List[SpanNode] = []
    for span_id, node in span_nodes.items():
        pid = parent_map.get(span_id)
        if pid and pid in span_nodes:
            span_nodes[pid].children.append(node)
        else:
            roots.append(node)

    # Sort children by start time
    def sort_tree(n: SpanNode) -> None:
        n.children.sort(key=lambda c: c.start_time_ns)
        for c in n.children:
            sort_tree(c)

    for r in roots:
        sort_tree(r)

    return roots


def export_trace_tree_json(spans: Sequence[Any]) -> str:
    """Exports trace hierarchy as a structured JSON string."""
    roots = build_trace_tree(spans)
    summary_cost = aggregate_cost_from_spans(spans)
    data = {
        "summary": summary_cost,
        "root_count": len(roots),
        "roots": [r.to_dict() for r in roots],
    }
    return json.dumps(data, indent=2)


# ============================================================================
# Mermaid Diagram Exporters
# ============================================================================

def export_mermaid_sequence(spans: Sequence[Any], title: str = "AgentScope Orchestration Trace") -> str:
    """
    Generates a Mermaid sequence diagram showing the interactions and flows
    between Lead Agent, Subagents, Tools, and LLM providers.
    """
    lines = [
        "sequenceDiagram",
        f"    %% {title}",
        "    autonumber",
        "    actor User",
        "    participant Lead as Lead Orchestrator",
    ]

    participants_added = {"User", "Lead"}

    def sanitize_mermaid_id(name: str) -> str:
        return "".join(c if c.isalnum() else "_" for c in name)

    roots = build_trace_tree(spans)

    def render_calls(node: SpanNode, caller: str) -> None:
        callee = caller
        is_subagent = False

        if node.role:
            callee = sanitize_mermaid_id(str(node.role))
            if callee not in participants_added:
                lines.append(f"    participant {callee} as {node.role} Agent")
                participants_added.add(callee)
            is_subagent = True
            lines.append(f"    {caller}->>+{callee}: Dispatch ({node.name})")
        elif "tool" in node.name.lower() or "tool.name" in node.data.get("attributes", {}):
            tool_name = node.data["attributes"].get("tool.name", node.name)
            callee = "Tool_" + sanitize_mermaid_id(str(tool_name))
            if callee not in participants_added:
                lines.append(f"    participant {callee} as Tool: {tool_name}")
                participants_added.add(callee)
            lines.append(f"    {caller}->>+{callee}: Call {tool_name}()")
        elif "chat" in node.name.lower() or node.model:
            model_name = node.model or "LLM"
            callee = "LLM_" + sanitize_mermaid_id(str(model_name))
            if callee not in participants_added:
                lines.append(f"    participant {callee} as LLM ({model_name})")
                participants_added.add(callee)
            tok_msg = f" [{node.input_tokens}in/{node.output_tokens}out]" if node.input_tokens > 0 else ""
            lines.append(f"    {caller}->>+{callee}: Chat Prompt{tok_msg}")

        # Render children
        current_actor = callee if is_subagent else caller
        for child in node.children:
            render_calls(child, current_actor)

        # Deactivate / return response
        if is_subagent:
            lines.append(f"    {callee}-->>-{caller}: Return result")
        elif "tool" in node.name.lower() or "tool.name" in node.data.get("attributes", {}):
            lines.append(f"    {callee}-->>-{caller}: Output")
        elif "chat" in node.name.lower() or node.model:
            lines.append(f"    {callee}-->>-{caller}: Completion")

    for root in roots:
        lines.append(f"    User->>+Lead: Start ({root.name})")
        for child in root.children:
            render_calls(child, "Lead")
        lines.append(f"    Lead-->>-User: Completed ({root.name})")

    return "\n".join(lines)


def export_mermaid_flowchart(spans: Sequence[Any], title: str = "AgentScope Execution Flow") -> str:
    """
    Generates a Mermaid flowchart (graph TD) showing hierarchy, token consumption,
    execution timing, and status.
    """
    lines = [
        "graph TD",
        f"    %% {title}",
        "    classDef okNode fill:#d4edda,stroke:#28a745,stroke-width:2px;",
        "    classDef errNode fill:#f8d7da,stroke:#dc3545,stroke-width:2px;",
        "    classDef leadNode fill:#cce5ff,stroke:#004085,stroke-width:3px;",
    ]

    roots = build_trace_tree(spans)

    def node_label(n: SpanNode) -> str:
        tokens_info = f"<br/>Tokens: {n.input_tokens + n.output_tokens}" if (n.input_tokens + n.output_tokens) > 0 else ""
        cost_info = f"<br/>Cost: ${n.cost_usd:.5f}" if n.cost_usd > 0 else ""
        dur_info = f"<br/>{n.duration_ms:.1f}ms" if n.duration_ms > 0 else ""
        title_text = n.role or n.name
        return f'"{title_text}{dur_info}{tokens_info}{cost_info}"'

    def render_nodes(node: SpanNode) -> None:
        cls_name = "errNode" if node.status == "ERROR" else ("leadNode" if node.parent_id is None else "okNode")
        lines.append(f"    {node.span_id}[{node_label(node)}]:::{cls_name}")
        for child in node.children:
            lines.append(f"    {node.span_id} --> {child.span_id}")
            render_nodes(child)

    for root in roots:
        render_nodes(root)

    return "\n".join(lines)


# ============================================================================
# Console ASCII Tree Exporter
# ============================================================================

def render_console_tree(spans: Sequence[Any]) -> str:
    """Renders a human-readable ASCII tree of the trace hierarchy."""
    roots = build_trace_tree(spans)
    output_lines: List[str] = []

    def format_node_details(node: SpanNode) -> str:
        details = []
        if node.role:
            details.append(f"role={node.role}")
        if node.model:
            details.append(f"model={node.model}")
        if node.input_tokens > 0 or node.output_tokens > 0:
            details.append(f"tokens={node.input_tokens}+{node.output_tokens}")
        if node.cost_usd > 0:
            details.append(f"${node.cost_usd:.5f}")
        if node.duration_ms > 0:
            details.append(f"{node.duration_ms:.1f}ms")
        if node.status == "ERROR":
            details.append("STATUS=ERROR")
        return f" [{', '.join(details)}]" if details else ""

    def print_branch(node: SpanNode, prefix: str = "", is_last: bool = True) -> None:
        connector = "└── " if is_last else "├── "
        output_lines.append(f"{prefix}{connector}{node.name}{format_node_details(node)}")
        child_prefix = prefix + ("    " if is_last else "│   ")
        count = len(node.children)
        for i, child in enumerate(node.children):
            print_branch(child, child_prefix, i == count - 1)

    for i, root in enumerate(roots):
        output_lines.append(f"{root.name}{format_node_details(root)}")
        count = len(root.children)
        for j, child in enumerate(root.children):
            print_branch(child, "", j == count - 1)

    return "\n".join(output_lines)
