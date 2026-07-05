# agentscope Observability Layer - Completion Report

## 1. Executive Summary
"agentscope" is a lightweight, custom observability layer built using Python and OpenTelemetry (OTel) to trace hierarchical agent actions. It is specifically designed to instrument Generative AI applications and multi-agent systems, providing detailed span context, parent-child trace tree propagation, latency metrics, token consumption, and aggregate trace pricing.

## 2. Architecture & Components
The system is divided into four main architectural modules:
1. **Instrumentation (`agentscope/instrumentation.py`)**: Emits spans mapping to GenAI semantic conventions. It contains wrappers to instrument LLM calls (managing metadata, inputs, and outputs), tool calls (child spans), and multi-agent dispatches (`dispatch_subagent`).
2. **Cost Aggregation (`agentscope/cost.py`)**: Walks a trace's span tree by querying the local Jaeger API (`/api/traces/{trace_id}`) and aggregates token usage and costs against a configurable per-model pricing table.
3. **Task Ledger Integration (`agentscope/ledger.py`)**: Automatically records and resolves trace IDs in `TASK_LEDGER.json`, returning direct UI links to inspect specific traces.
4. **Query Service (`query_service.py`)**: Exposes the cost metric over an HTTP endpoint on port 8000 (e.g. `/cost?trace_id=<id>`).

## 3. OpenTelemetry Semantic Conventions Used
The project targets and documents the **OTel GenAI Semantic Conventions v1.27.0**.
Spans are annotated with the following key attributes:
- `gen_ai.system`: Identifies the underlying LLM provider/system (e.g. `openai`, `anthropic`, `mock`).
- `gen_ai.operation.name`: Set to `chat` for text completion/chat spans.
- `gen_ai.request.model`: The requested model (e.g. `gpt-4o`).
- `gen_ai.response.model`: The model used in the response.
- `gen_ai.usage.input_tokens`: Prompt token count.
- `gen_ai.usage.output_tokens`: Completion token count.
- `gen_ai.request.<param>`: Captures non-secret parameters (like `temperature`).

### Security & Privacy Rules
- **Content Capture Mode**: By default, `CAPTURE_CONTENT` is set to `False` (metadata-only). Prompts, completions, and tool outputs are excluded from span attributes unless configured otherwise.
- **Secrets Redaction**: Span inputs and attributes are scanned dynamically. Any keys or values resembling API keys (e.g. `sk-...`, `ghp_...`), secrets, or passwords are automatically replaced with `[REDACTED]` placeholders before recording.

## 4. Multi-Agent Hierarchy & Parallel Dispatch
To support multi-agent systems, `dispatch_subagent` acts as a context manager that takes a parent span reference and uses OTel context propagation. This allows representing hierarchical flows as a single cohesive span tree. 
During the simulated review cycle, a Lead agent dispatches:
1. A Developer agent (creating a child branch containing LLM and tool spans).
2. A shared "Review Cycle" parent span.
3. Parallel dispatches of Security and QA agents running in concurrent threads under the shared review parent.

The resulting 10-span trace tree successfully visualizes Developer and parallel Security/QA dispatches as distinct branches under a single trace ID in the Jaeger UI.

## 5. Cost Aggregation and Query API
`aggregate_cost(trace_id)` queries the Jaeger JSON API, parses token metrics and models, and computes pricing based on the table in `agentscope/constants.py`.
Exposed on `GET http://localhost:8000/cost?trace_id=<trace_id>`, a verified query of our simulated hierarchy trace returned:
- Input tokens: 380
- Output tokens: 320
- Total tokens: 700
- USD Cost: $0.01462 (matches hand-calculation exactly)
- Call count: 3

## 6. Approval-Gate Integration
`agentscope/ledger.py` binds trace IDs directly into `TASK_LEDGER.json` entries. A direct lookup function resolves entries back to a direct, clickable Jaeger trace URL:
- Link format: `http://localhost:16686/trace/{trace_id}`

This enables human gatekeepers to click a single link in the approval ledger and immediately audit the full span tree, cost, and metadata of a task execution.
