# TICKETS — AgentScope Observability Pipeline

## [TICKET-001] OpenTelemetry Dispatch Rationale Span Event Recorder
- **Blocked by**: None
- **Delivers**: Standardized OTel span event generator recording agent reasoning.
- **Verification**: `tests/test_dispatch_rationale_spans.py`

## [TICKET-002] 2026 Model Token Pricing & Cost Circuit Breaker
- **Blocked by**: TICKET-001
- **Delivers**: Up-to-date model rate table and automated loop terminator for cost overruns.
- **Verification**: Pricing calculation and budget trip unit tests.
