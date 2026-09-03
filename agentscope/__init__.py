# agentscope/__init__.py
"""
AgentScope: Autonomous Agent Observability, Cost Aggregation, and Governance Layer.
"""

from agentscope.constants import (
    OTEL_GENAI_SPEC_VERSION,
    CAPTURE_CONTENT,
    MODEL_PRICING,
    DEFAULT_SERVICE_NAME,
    DEFAULT_OTLP_ENDPOINT,
    DEFAULT_JAEGER_URL,
    DEFAULT_QUERY_SERVICE_PORT,
    get_model_pricing,
    normalize_model_name,
    register_model_pricing,
)

from agentscope.instrumentation import (
    init_tracer,
    init_in_memory_tracer,
    get_tracer,
    get_in_memory_exporter,
    flush_tracer,
    shutdown_tracer,
    reset_tracer,
    instrument_llm_call,
    async_instrument_llm_call,
    instrument_tool_call,
    instrument_tool_call_timed,
    async_instrument_tool_call_timed,
    dispatch_subagent,
    async_dispatch_subagent,
    sanitize_value,
    sanitize_dict,
    LLMCallContext,
)

from agentscope.cost import (
    aggregate_cost,
    aggregate_cost_from_spans,
    aggregate_cost_from_trace_data,
)

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

from agentscope.tree import (
    fetch_trace_data,
    fetch_and_build_tree,
    render_trace,
    find_nodes,
    get_critical_path,
)

from agentscope.ledger import (
    load_ledger,
    save_ledger,
    update_task_trace,
    resolve_trace_link,
)

from agentscope.schemas import (
    SchemaValidationError,
    validate_finding,
    validate_findings_report,
    validate_test_results,
    load_validated_report,
    summarize_findings,
    summarize_test_results,
    SEVERITY_ENUM,
    CATEGORY_ENUM,
    TEST_STATUS_ENUM,
)

from agentscope.rationale import (
    log_dispatch_rationale,
    read_rationale_log,
)

from agentscope.cycles import (
    get_cycle_count,
    increment_cycle,
    reset_cycle_count,
    assert_can_dispatch,
    COMPACT_RULES,
    DEFAULT_CYCLE_CAP,
)

from agentscope.delegation import (
    sign_delegation,
    verify_delegation,
    read_audit_log,
)

__version__ = "3.2.0"
__all__ = [
    # Constants
    "OTEL_GENAI_SPEC_VERSION",
    "CAPTURE_CONTENT",
    "MODEL_PRICING",
    "DEFAULT_SERVICE_NAME",
    "DEFAULT_OTLP_ENDPOINT",
    "DEFAULT_JAEGER_URL",
    "DEFAULT_QUERY_SERVICE_PORT",
    "get_model_pricing",
    "normalize_model_name",
    "register_model_pricing",
    # Instrumentation
    "init_tracer",
    "init_in_memory_tracer",
    "get_tracer",
    "get_in_memory_exporter",
    "flush_tracer",
    "shutdown_tracer",
    "reset_tracer",
    "instrument_llm_call",
    "async_instrument_llm_call",
    "instrument_tool_call",
    "instrument_tool_call_timed",
    "async_instrument_tool_call_timed",
    "dispatch_subagent",
    "async_dispatch_subagent",
    "sanitize_value",
    "sanitize_dict",
    "LLMCallContext",
    # Cost
    "aggregate_cost",
    "aggregate_cost_from_spans",
    "aggregate_cost_from_trace_data",
    # Exporters
    "ExponentialBackoff",
    "ResilientSpanExporter",
    "SpanNode",
    "build_trace_tree",
    "export_trace_tree_json",
    "export_mermaid_sequence",
    "export_mermaid_flowchart",
    "render_console_tree",
    # Tree
    "fetch_trace_data",
    "fetch_and_build_tree",
    "render_trace",
    "find_nodes",
    "get_critical_path",
    # Ledger
    "load_ledger",
    "save_ledger",
    "update_task_trace",
    "resolve_trace_link",
    # Schemas
    "SchemaValidationError",
    "validate_finding",
    "validate_findings_report",
    "validate_test_results",
    "load_validated_report",
    "summarize_findings",
    "summarize_test_results",
    "SEVERITY_ENUM",
    "CATEGORY_ENUM",
    "TEST_STATUS_ENUM",
    # Rationale
    "log_dispatch_rationale",
    "read_rationale_log",
    # Cycles
    "get_cycle_count",
    "increment_cycle",
    "reset_cycle_count",
    "assert_can_dispatch",
    "COMPACT_RULES",
    "DEFAULT_CYCLE_CAP",
    # Delegation
    "sign_delegation",
    "verify_delegation",
    "read_audit_log",
]
