# agentscope/__init__.py

from agentscope.instrumentation import (
    init_tracer,
    get_tracer,
    instrument_llm_call,
    instrument_tool_call,
    instrument_tool_call_timed,
    dispatch_subagent
)

from agentscope.cost import aggregate_cost

from agentscope.constants import (
    OTEL_GENAI_SPEC_VERSION,
    CAPTURE_CONTENT,
    MODEL_PRICING
)

from agentscope.ledger import (
    load_ledger,
    save_ledger,
    update_task_trace,
    resolve_trace_link
)

# V3 spec additions
from agentscope.schemas import (
    SchemaValidationError,
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
    assert_can_dispatch,
    COMPACT_RULES,
    DEFAULT_CYCLE_CAP,
)

from agentscope.delegation import (
    sign_delegation,
    verify_delegation,
    read_audit_log,
)
