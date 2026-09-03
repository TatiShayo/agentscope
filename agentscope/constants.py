# agentscope/constants.py
"""
Constants, model pricing tables, and global configurations for agentscope.
"""

from typing import Dict, Any, Optional

# Exact OTel GenAI Semantic Conventions specification version targeted
OTEL_GENAI_SPEC_VERSION = "v1.27.0"

# Configuration for content-capture mode (default: metadata-only)
CAPTURE_CONTENT = False

# Default service configuration
DEFAULT_SERVICE_NAME = "agentscope"
DEFAULT_OTLP_ENDPOINT = "localhost:4317"
DEFAULT_JAEGER_URL = "http://localhost:16686"
DEFAULT_QUERY_SERVICE_PORT = 8000

# Per-model pricing table (USD per 1,000 tokens).
# Comprehensive pricing covering leading 2024-2026 models from Anthropic, OpenAI,
# Google, DeepSeek, Meta, Mistral, and Cohere.
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # --- Anthropic (Latest & Current) ---
    "claude-fable-5": {"input": 0.010, "output": 0.050},
    "claude-opus-4-8": {"input": 0.005, "output": 0.025},
    "claude-opus-4-7": {"input": 0.005, "output": 0.025},
    "claude-opus-4-6": {"input": 0.005, "output": 0.025},
    "claude-sonnet-5": {"input": 0.003, "output": 0.015},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
    "claude-3-7-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
    "claude-3-5-haiku": {"input": 0.001, "output": 0.005},
    "claude-3-5-haiku-20241022": {"input": 0.001, "output": 0.005},
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},

    # --- OpenAI (Latest & Current) ---
    "gpt-4o": {"input": 0.0025, "output": 0.010},
    "gpt-4o-2024-08-06": {"input": 0.0025, "output": 0.010},
    "gpt-4o-2024-11-20": {"input": 0.0025, "output": 0.010},
    "gpt-4o-2024-05-13": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o-mini-2024-07-18": {"input": 0.00015, "output": 0.0006},
    "chatgpt-4o-latest": {"input": 0.005, "output": 0.015},
    "gpt-4.5-preview": {"input": 0.075, "output": 0.150},
    "o1": {"input": 0.015, "output": 0.060},
    "o1-2024-12-17": {"input": 0.015, "output": 0.060},
    "o1-preview": {"input": 0.015, "output": 0.060},
    "o1-preview-2024-09-12": {"input": 0.015, "output": 0.060},
    "o1-mini": {"input": 0.0011, "output": 0.0044},
    "o1-mini-2024-09-12": {"input": 0.0011, "output": 0.0044},
    "o3-mini": {"input": 0.0011, "output": 0.0044},
    "o3-mini-2025-01-31": {"input": 0.0011, "output": 0.0044},
    "gpt-4-turbo": {"input": 0.010, "output": 0.030},
    "gpt-4-turbo-2024-04-09": {"input": 0.010, "output": 0.030},
    "gpt-4": {"input": 0.030, "output": 0.060},
    "gpt-4-32k": {"input": 0.060, "output": 0.120},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "gpt-3.5-turbo-0125": {"input": 0.0005, "output": 0.0015},

    # --- Google Gemini (1.5, 2.0 & 2.5) ---
    "gemini-2.5-pro": {"input": 0.00125, "output": 0.005},
    "gemini-2.5-flash": {"input": 0.0001, "output": 0.0004},
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
    "gemini-2.0-flash-exp": {"input": 0.0001, "output": 0.0004},
    "gemini-2.0-flash-lite": {"input": 0.000075, "output": 0.0003},
    "gemini-2.0-flash-lite-preview-02-05": {"input": 0.000075, "output": 0.0003},
    "gemini-2.0-pro-exp-02-05": {"input": 0.00125, "output": 0.005},
    "gemini-2.0-flash-thinking-exp-01-21": {"input": 0.0001, "output": 0.0004},
    "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
    "gemini-1.5-pro-latest": {"input": 0.00125, "output": 0.005},
    "gemini-1.5-pro-001": {"input": 0.00125, "output": 0.005},
    "gemini-1.5-pro-002": {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-flash-latest": {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-flash-001": {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-flash-002": {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-flash-8b": {"input": 0.0000375, "output": 0.00015},
    "gemini-1.5-flash-8b-latest": {"input": 0.0000375, "output": 0.00015},

    # --- DeepSeek ---
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
    "deepseek-v4": {"input": 0.00014, "output": 0.00028},
    "deepseek-v3": {"input": 0.00014, "output": 0.00028},
    "deepseek-r1": {"input": 0.00055, "output": 0.00219},
    "deepseek-coder": {"input": 0.00014, "output": 0.00028},

    # --- Meta LLaMA / Open Weights ---
    "llama-3.3-70b-instruct": {"input": 0.00059, "output": 0.00079},
    "llama-3.1-405b-instruct": {"input": 0.0035, "output": 0.0035},
    "llama-3.1-70b-instruct": {"input": 0.00059, "output": 0.00079},
    "llama-3.1-8b-instruct": {"input": 0.00008, "output": 0.00008},

    # --- Mistral AI ---
    "mistral-large-latest": {"input": 0.002, "output": 0.006},
    "mistral-small-latest": {"input": 0.0002, "output": 0.0006},
    "codestral-latest": {"input": 0.0003, "output": 0.0009},

    # --- Cohere ---
    "command-r-plus": {"input": 0.0025, "output": 0.010},
    "command-r": {"input": 0.00015, "output": 0.0006},

    # --- Simulation & Testing ---
    "mock-model": {"input": 0.0001, "output": 0.0002},
    "test-model": {"input": 0.0001, "output": 0.0002},
}


def normalize_model_name(model_name: str) -> str:
    """Normalizes model names (lowercasing, trimming, alias mapping)."""
    if not model_name:
        return "mock-model"
    name = model_name.strip().lower()
    # Normalize common prefix variations (e.g. models/gemini-1.5-pro -> gemini-1.5-pro)
    if "/" in name:
        name = name.split("/")[-1]
    return name


def get_model_pricing(model_name: str) -> Optional[Dict[str, float]]:
    """Retrieves pricing for a model by name or normalized name."""
    norm = normalize_model_name(model_name)
    if norm in MODEL_PRICING:
        return MODEL_PRICING[norm]
    # Check if exact match exists
    if model_name in MODEL_PRICING:
        return MODEL_PRICING[model_name]
    return None


def register_model_pricing(model_name: str, input_price: float, output_price: float) -> None:
    """Registers or updates a custom model's pricing in the global table."""
    if input_price < 0 or output_price < 0:
        raise ValueError("Pricing cannot be negative.")
    norm = normalize_model_name(model_name)
    MODEL_PRICING[norm] = {"input": float(input_price), "output": float(output_price)}
