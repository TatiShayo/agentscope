# agentscope V3 Upgrade — July 5, 2026

Implements the previously-unimplemented mechanisms from
`portfolio-audit-and-orchestration-redesign-v3.md` as importable library code.

## New modules

| Module | Spec row | What it does |
|---|---|---|
| `agentscope/schemas.py` | 1, 7 | Strict schema validation for `FINDINGS.json` / `TEST_RESULTS.json` (enum severity/category/status, provenance tag, unknown-field rejection) via `load_validated_report()`, plus `summarize_findings()` / `summarize_test_results()` — the counts-and-histogram-only view the Lead is allowed to read (no free text). |
| `agentscope/rationale.py` | 4 | Dispatch rationale log (`DISPATCH_RATIONALE.jsonl`): `log_dispatch_rationale()` written *before* each dispatch, `read_rationale_log()` readable by every agent and the human. |
| `agentscope/cycles.py` | 5, 6 | Harness-incremented fix-review cycle counter stored in `TASK_LEDGER` (`increment_cycle()`, `assert_can_dispatch()` raises at the 3-cycle cap) plus `COMPACT_RULES` — the per-role compact rule text re-injected each cycle. |
| `agentscope/delegation.py` | 11 | HMAC-signed delegation records appended to `AUDIT_LOG.jsonl` (`sign_delegation()` / `verify_delegation()` / `read_audit_log()` which flags tampered or unsigned records). Key auto-generated at `~/.agentscope_hmac_key`. AIP is the named upgrade path if delegation ever crosses an external trust boundary. |

## Other changes

- `constants.py`: pricing table updated to current (July 2026) models — Claude Fable 5
  ($10/$50 per MTok), Opus 4.8/4.7/4.6 ($5/$25), Sonnet 5 ($3/$15), Haiku 4.5 ($1/$5).
  Legacy entries kept so historical traces still price.
- `cost.py`: unknown models are now reported in the result (`unknown_models`,
  `cost_estimate_incomplete: true`) instead of being silently billed at mock rates.
- `instrumentation.py`: removed unused import; added `instrument_tool_call_timed()`
  context manager so tool spans can cover real execution time (the original function
  emits a zero-duration span recorded after the fact).
- `.agents/agents/*/agent.json`: all four role prompts replaced with the complete V3
  §6 prompts (acceptance criteria, dispatch visibility, harness-tracked iteration
  limit, constraint re-assertion, named skip/reduce conditions, delegation records,
  least-code ladder, enum-constrained report schemas, tool-output compression).

## Tests

`tests/test_v3_modules.py` — 20 tests covering schema enforcement (including
prompt-infection-style freeform severity and unknown-field rejection), the
summary-only Lead view containing no free text, rationale logging, cycle cap
enforcement, and delegation signing/tamper detection. All passing.

## Not implemented (deliberately, per spec §8)

- microVM sandboxing (row 10) — E2B/Firecracker is an infrastructure choice, not
  library code; the manifests in §3 carry the `execution_environment` fields.
- A2A transport (row 13) — degraded-fallback mode (direct subagent spawn) is the
  current transport, exactly as the spec's fallback table prescribes.
- Repo structural index (row 18) — optional, per-project decision.
