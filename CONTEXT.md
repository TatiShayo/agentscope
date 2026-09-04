# CONTEXT.md — Ubiquitous Domain Language (AgentScope)

## Core Entities
- **AgentSpan**: OpenTelemetry trace unit capturing an autonomous agent execution step.
- **DispatchRationale**: Structured explanation detailing why a specific model or subagent was invoked.
- **ModelPricingTable**: Up-to-date registry of input/output token rates across LLM providers.
- **RunawaySpendBreaker**: Circuit breaker terminating agent loops when cumulative session cost exceeds budget.

## Domain Invariants
- Every agent delegation step must record a `dispatch_rationale` span event.
- Telemetry exporters must sanitize credentials before transmitting spans over the network.

## Forbidden Terminology
- Do not call agent steps "tasks"; use "AgentSpan".
- Do not hardcode token prices in application code; use "ModelPricingTable".
