# tests/test_cost.py
"""
Unit tests for AgentScope cost aggregation, multi-model pricing tables,
and Decimal mathematical precision.
"""

import os
import sys
import pytest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentscope.cost import (
    aggregate_cost_from_spans,
    aggregate_cost_from_trace_data,
    _extract_tags_dict,
)
from agentscope.constants import (
    MODEL_PRICING,
    get_model_pricing,
    normalize_model_name,
    register_model_pricing,
)


class TestModelPricingTable:
    def test_anthropic_models_present(self):
        models = [
            "claude-fable-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
            "claude-sonnet-5", "claude-haiku-4-5", "claude-3-7-sonnet", "claude-3-5-sonnet",
            "claude-3-5-haiku", "claude-3-opus",
        ]
        for m in models:
            pricing = get_model_pricing(m)
            assert pricing is not None, f"Missing pricing for {m}"
            assert pricing["input"] > 0 and pricing["output"] > 0

    def test_openai_models_present(self):
        models = ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini", "o3-mini", "gpt-4.5-preview"]
        for m in models:
            pricing = get_model_pricing(m)
            assert pricing is not None, f"Missing pricing for {m}"
            assert pricing["input"] > 0 and pricing["output"] > 0

    def test_gemini_models_present(self):
        models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"]
        for m in models:
            pricing = get_model_pricing(m)
            assert pricing is not None, f"Missing pricing for {m}"
            assert pricing["input"] > 0 and pricing["output"] > 0

    def test_deepseek_models_present(self):
        models = ["deepseek-v3", "deepseek-r1", "deepseek-chat", "deepseek-reasoner"]
        for m in models:
            pricing = get_model_pricing(m)
            assert pricing is not None, f"Missing pricing for {m}"
            assert pricing["input"] > 0 and pricing["output"] > 0

    def test_model_name_normalization(self):
        assert normalize_model_name("models/gemini-1.5-pro") == "gemini-1.5-pro"
        assert normalize_model_name("  GPT-4O-Mini  ") == "gpt-4o-mini"
        assert normalize_model_name("") == "mock-model"

    def test_register_custom_model_pricing(self):
        register_model_pricing("custom-llm-ultra", 0.004, 0.016)
        p = get_model_pricing("custom-llm-ultra")
        assert p == {"input": 0.004, "output": 0.016}

    def test_register_negative_pricing_fails(self):
        with pytest.raises(ValueError):
            register_model_pricing("bad-llm", -0.01, 0.02)


class TestCostAggregationCalculation:
    def test_single_span_gpt4o_cost(self):
        # GPT-4o: $0.0025 per 1k input ($2.5/M), $0.010 per 1k output ($10/M)
        # 10,000 input tokens = (10000 * 0.0025) / 1000 = $0.025
        # 5,000 output tokens = (5000 * 0.010) / 1000 = $0.050
        # Total = $0.075
        span = {
            "name": "chat gpt-4o",
            "tags": {
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 10000,
                "gen_ai.usage.output_tokens": 5000,
            }
        }
        res = aggregate_cost_from_spans([span], trace_id="trace-1")
        assert res["total_input_tokens"] == 10000
        assert res["total_output_tokens"] == 5000
        assert res["total_tokens"] == 15000
        assert res["total_cost_usd"] == 0.075
        assert res["call_count"] == 1
        assert "unknown_models" not in res

    def test_claude_sonnet_5_pricing(self):
        # claude-sonnet-5: input=0.003, output=0.015
        # 2,000 input = 2 * 0.003 = 0.006
        # 1,000 output = 1 * 0.015 = 0.015
        # Total = $0.021
        span = {
            "name": "chat claude-sonnet-5",
            "tags": {
                "gen_ai.response.model": "claude-sonnet-5",
                "gen_ai.usage.input_tokens": 2000,
                "gen_ai.usage.output_tokens": 1000,
            }
        }
        res = aggregate_cost_from_spans([span])
        assert res["total_cost_usd"] == 0.021

    def test_deepseek_v3_pricing(self):
        # deepseek-v3: input=0.00014, output=0.00028
        # 1,000,000 input = 1000 * 0.00014 = $0.14
        # 1,000,000 output = 1000 * 0.00028 = $0.28
        # Total = $0.42
        span = {
            "name": "chat deepseek-v3",
            "tags": {
                "gen_ai.request.model": "deepseek-v3",
                "gen_ai.usage.input_tokens": 1000000,
                "gen_ai.usage.output_tokens": 1000000,
            }
        }
        res = aggregate_cost_from_spans([span])
        assert res["total_cost_usd"] == 0.42

    def test_multi_agent_delegation_breakdown(self):
        spans = [
            {
                "name": "chat gpt-4o",
                "tags": {
                    "agent.role": "LeadOrchestrator",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.input_tokens": 1000,
                    "gen_ai.usage.output_tokens": 500,
                }
            },
            {
                "name": "chat claude-3-5-sonnet",
                "tags": {
                    "agent.role": "DeveloperAgent",
                    "gen_ai.request.model": "claude-3-5-sonnet",
                    "gen_ai.usage.input_tokens": 2000,
                    "gen_ai.usage.output_tokens": 1000,
                }
            },
            {
                "name": "chat deepseek-r1",
                "tags": {
                    "agent.role": "SecurityAgent",
                    "gen_ai.request.model": "deepseek-r1",
                    "gen_ai.usage.input_tokens": 3000,
                    "gen_ai.usage.output_tokens": 1500,
                }
            }
        ]
        res = aggregate_cost_from_spans(spans, trace_id="multi-agent-trace")
        assert res["call_count"] == 3
        assert res["total_tokens"] == 9000

        # Verify breakdowns
        assert "LeadOrchestrator" in res["by_agent"]
        assert "DeveloperAgent" in res["by_agent"]
        assert "SecurityAgent" in res["by_agent"]

        assert "gpt-4o" in res["by_model"]
        assert "claude-3-5-sonnet" in res["by_model"]
        assert "deepseek-r1" in res["by_model"]

    def test_unknown_model_surfaces_flag(self):
        span = {
            "name": "chat mysterious-model-x",
            "tags": {
                "gen_ai.request.model": "mysterious-model-x",
                "gen_ai.usage.input_tokens": 500,
                "gen_ai.usage.output_tokens": 200,
            }
        }
        res = aggregate_cost_from_spans([span])
        assert res["cost_estimate_incomplete"] is True
        assert "mysterious-model-x" in res["unknown_models"]
        # Falls back to mock pricing
        mock_p = MODEL_PRICING["mock-model"]
        expected_cost = ((500 * mock_p["input"]) + (200 * mock_p["output"])) / 1000.0
        assert res["total_cost_usd"] == round(expected_cost, 6)

    def test_jaeger_json_trace_format(self):
        jaeger_trace = {
            "traceID": "0123456789abcdef0123456789abcdef",
            "spans": [
                {
                    "spanID": "span-1",
                    "operationName": "chat gpt-4o",
                    "tags": [
                        {"key": "gen_ai.request.model", "value": "gpt-4o"},
                        {"key": "gen_ai.usage.input_tokens", "value": 400},
                        {"key": "gen_ai.usage.output_tokens", "value": 100},
                    ]
                }
            ]
        }
        res = aggregate_cost_from_trace_data(jaeger_trace)
        assert res["trace_id"] == "0123456789abcdef0123456789abcdef"
        assert res["total_tokens"] == 500
        assert res["call_count"] == 1

    def test_empty_or_non_genai_spans(self):
        empty_res = aggregate_cost_from_spans([])
        assert empty_res["total_tokens"] == 0
        assert empty_res["total_cost_usd"] == 0.0
        assert empty_res["call_count"] == 0

        tool_span = {
            "name": "tool bash",
            "tags": {"tool.name": "bash", "tool.args": "ls"}
        }
        res = aggregate_cost_from_spans([tool_span])
        assert res["call_count"] == 0
        assert res["total_cost_usd"] == 0.0
