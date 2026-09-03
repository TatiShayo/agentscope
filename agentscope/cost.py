# agentscope/cost.py
"""
Cost aggregation and token accounting module for AgentScope.
Traverses span trees (from Jaeger API, OTel SDK ReadableSpan instances, or raw dictionaries),
calculates token usage with exact precision, and aggregates multi-agent costs.
"""

import json
import urllib.request
import urllib.error
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Union, Sequence

from agentscope.constants import (
    MODEL_PRICING,
    DEFAULT_JAEGER_URL,
    get_model_pricing,
    normalize_model_name,
)


def _extract_tags_dict(span: Any) -> Dict[str, Any]:
    """
    Extracts attributes/tags from a span whether it is:
    1. A Jaeger JSON span dict: {"tags": [{"key": "...", "value": "..."}]}
    2. An OTel ReadableSpan instance: span.attributes
    3. A plain dict with attributes directly or under 'attributes' / 'tags'
    """
    if hasattr(span, "attributes") and span.attributes is not None:
        return dict(span.attributes)

    if isinstance(span, dict):
        if "attributes" in span and isinstance(span["attributes"], dict):
            return dict(span["attributes"])
        if "tags" in span and isinstance(span["tags"], list):
            return {t["key"]: t["value"] for t in span["tags"] if isinstance(t, dict) and "key" in t}
        if "tags" in span and isinstance(span["tags"], dict):
            return dict(span["tags"])
        # Span might be a flat dict of attributes
        return dict(span)

    return {}


def _extract_span_name(span: Any) -> str:
    """Extracts operation name from span."""
    if hasattr(span, "name"):
        return str(span.name)
    if isinstance(span, dict):
        return str(span.get("operationName") or span.get("name") or "")
    return ""


def aggregate_cost_from_spans(
    spans: Sequence[Any],
    trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates exact token usage and USD cost from a sequence of spans.
    Works with in-memory OTel ReadableSpan objects, Jaeger span dicts, or custom dicts.
    """
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost_dec = Decimal("0.000000")
    call_count = 0
    unknown_models = set()

    by_model: Dict[str, Dict[str, Any]] = {}
    by_agent: Dict[str, Dict[str, Any]] = {}
    by_operation: Dict[str, Dict[str, Any]] = {}

    resolved_trace_id = trace_id or "in-memory"

    for span in spans:
        tags = _extract_tags_dict(span)
        op_name = _extract_span_name(span)

        # Infer trace ID if not supplied
        if resolved_trace_id == "in-memory":
            if hasattr(span, "context") and hasattr(span.context, "trace_id"):
                resolved_trace_id = f"{span.context.trace_id:032x}"
            elif isinstance(span, dict) and "traceID" in span:
                resolved_trace_id = str(span["traceID"])

        # Check if span represents a GenAI call with token counts
        has_tokens = "gen_ai.usage.input_tokens" in tags or "gen_ai.usage.output_tokens" in tags
        if not has_tokens:
            continue

        call_count += 1
        try:
            input_tokens = max(0, int(tags.get("gen_ai.usage.input_tokens", 0)))
        except (ValueError, TypeError):
            input_tokens = 0

        try:
            output_tokens = max(0, int(tags.get("gen_ai.usage.output_tokens", 0)))
        except (ValueError, TypeError):
            output_tokens = 0

        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

        # Resolve model name
        raw_model = (
            tags.get("gen_ai.response.model")
            or tags.get("gen_ai.request.model")
            or "mock-model"
        )
        model_name = str(raw_model)
        pricing = get_model_pricing(model_name)

        if pricing is None:
            unknown_models.add(model_name)
            pricing = MODEL_PRICING["mock-model"]

        # Exact Decimal calculation (pricing is per 1000 tokens)
        in_price = Decimal(str(pricing["input"]))
        out_price = Decimal(str(pricing["output"]))
        thousand = Decimal("1000")

        span_cost_dec = ((Decimal(input_tokens) * in_price) + (Decimal(output_tokens) * out_price)) / thousand
        total_cost_dec += span_cost_dec

        # Rollup by model
        norm_model = normalize_model_name(model_name)
        if norm_model not in by_model:
            by_model[norm_model] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "call_count": 0,
            }
        by_model[norm_model]["input_tokens"] += input_tokens
        by_model[norm_model]["output_tokens"] += output_tokens
        by_model[norm_model]["total_tokens"] += (input_tokens + output_tokens)
        by_model[norm_model]["call_count"] += 1
        by_model[norm_model]["cost_usd"] = float(
            (Decimal(str(by_model[norm_model]["cost_usd"])) + span_cost_dec).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        )

        # Rollup by agent role (if tagged)
        agent_role = str(tags.get("agent.role", tags.get("agent_role", "unspecified")))
        if agent_role not in by_agent:
            by_agent[agent_role] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "call_count": 0,
            }
        by_agent[agent_role]["input_tokens"] += input_tokens
        by_agent[agent_role]["output_tokens"] += output_tokens
        by_agent[agent_role]["total_tokens"] += (input_tokens + output_tokens)
        by_agent[agent_role]["call_count"] += 1
        by_agent[agent_role]["cost_usd"] = float(
            (Decimal(str(by_agent[agent_role]["cost_usd"])) + span_cost_dec).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        )

        # Rollup by operation
        op_key = op_name or str(tags.get("gen_ai.operation.name", "chat"))
        if op_key not in by_operation:
            by_operation[op_key] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "call_count": 0,
            }
        by_operation[op_key]["input_tokens"] += input_tokens
        by_operation[op_key]["output_tokens"] += output_tokens
        by_operation[op_key]["total_tokens"] += (input_tokens + output_tokens)
        by_operation[op_key]["call_count"] += 1
        by_operation[op_key]["cost_usd"] = float(
            (Decimal(str(by_operation[op_key]["cost_usd"])) + span_cost_dec).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        )

    # Quantize total cost
    rounded_cost = float(total_cost_dec.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))

    result = {
        "trace_id": resolved_trace_id,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "total_cost_usd": rounded_cost,
        "exact_cost_usd": str(total_cost_dec),
        "call_count": call_count,
        "by_model": by_model,
        "by_agent": by_agent,
        "by_operation": by_operation,
    }

    if unknown_models:
        result["unknown_models"] = sorted(unknown_models)
        result["cost_estimate_incomplete"] = True

    return result


def aggregate_cost_from_trace_data(trace_data: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregates cost from a single Jaeger trace data object."""
    if not isinstance(trace_data, dict):
        raise ValueError("trace_data must be a dictionary.")

    trace_id = trace_data.get("traceID")
    spans = trace_data.get("spans", [])
    return aggregate_cost_from_spans(spans, trace_id=trace_id)


def aggregate_cost(
    trace_id: str,
    jaeger_url: str = DEFAULT_JAEGER_URL,
    timeout_seconds: float = 5.0
) -> Dict[str, Any]:
    """
    Fetches raw spans of a trace from Jaeger, walks the span tree,
    and aggregates input/output token usage and total cost.
    """
    if not trace_id or not trace_id.strip():
        raise ValueError("trace_id must be a non-empty string.")

    clean_trace_id = trace_id.strip()
    url = f"{jaeger_url.rstrip('/')}/api/traces/{clean_trace_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentScope-CostAggregator/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            res_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to connect to Jaeger at {url}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to fetch trace {clean_trace_id} from Jaeger: {e}")

    if not res_data.get("data") or len(res_data["data"]) == 0:
        raise ValueError(f"Trace ID {clean_trace_id} not found in Jaeger.")

    trace_data = res_data["data"][0]
    return aggregate_cost_from_trace_data(trace_data)
