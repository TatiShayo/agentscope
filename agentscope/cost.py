# agentscope/cost.py

import urllib.request
import json
from typing import Dict, Any, Optional
from agentscope.constants import MODEL_PRICING

def aggregate_cost(trace_id: str, jaeger_url: str = "http://localhost:16686") -> Dict[str, Any]:
    """
    Fetches raw spans of a trace from Jaeger, walks the span tree,
    and aggregates input/output token usage and total cost.
    """
    url = f"{jaeger_url}/api/traces/{trace_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode())
    except Exception as e:
        raise ValueError(f"Failed to fetch trace {trace_id} from Jaeger: {e}")
        
    if not res_data.get("data"):
        raise ValueError(f"Trace ID {trace_id} not found in Jaeger.")
        
    trace_data = res_data["data"][0]
    spans = trace_data.get("spans", [])
    
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    call_count = 0
    unknown_models = set()

    for span in spans:
        tags = {t["key"]: t["value"] for t in span.get("tags", [])}
        
        # Check if this span represents a GenAI chat operation
        # (Usually identified by gen_ai.operation.name = chat, or presence of token attributes)
        has_tokens = "gen_ai.usage.input_tokens" in tags or "gen_ai.usage.output_tokens" in tags
        if not has_tokens:
            continue
            
        call_count += 1
        input_tokens = int(tags.get("gen_ai.usage.input_tokens", 0))
        output_tokens = int(tags.get("gen_ai.usage.output_tokens", 0))
        
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        
        # Resolve model name
        model_name = tags.get("gen_ai.response.model") or tags.get("gen_ai.request.model") or "mock-model"
        
        # Get pricing. An unknown model is surfaced in the result rather than
        # silently billed at mock-model rates — that hid real cost before.
        pricing = MODEL_PRICING.get(model_name)
        if pricing is None:
            unknown_models.add(model_name)
            pricing = MODEL_PRICING["mock-model"]
        
        # Calculate cost (pricing is per 1000 tokens)
        span_cost = ((input_tokens * pricing["input"]) + (output_tokens * pricing["output"])) / 1000.0
        total_cost += span_cost
        
    result = {
        "trace_id": trace_id,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "total_cost_usd": round(total_cost, 6),
        "call_count": call_count
    }
    if unknown_models:
        result["unknown_models"] = sorted(unknown_models)
        result["cost_estimate_incomplete"] = True
    return result
