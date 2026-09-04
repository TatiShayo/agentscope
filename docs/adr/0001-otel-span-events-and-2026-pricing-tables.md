# ADR 0001: OpenTelemetry Span Events and Dynamic Model Pricing Tables

## Context
Engineering teams deploying autonomous agents lack visibility into why agents take specific actions and suffer unpredictable API bills.

## Decision
1. **OTel Rationale Spans**: Embed structured dispatch decisions inside OpenTelemetry span events.
2. **Dynamic Pricing Registry**: Maintain canonical 2026 model rate tables for live cost tracking.
3. **Spend Circuit Breaker**: Abruptly halt loops that exceed session cost thresholds.

## Consequences
- **Positive**: 100% decision auditability and complete protection against runaway loop spending.
- **Negative**: Adds negligible 1-2ms overhead per agent telemetry dispatch.
