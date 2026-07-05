# agentscope/constants.py

# Exact OTel GenAI Semantic Conventions specification version targeted
OTEL_GENAI_SPEC_VERSION = "v1.27.0"

# Configuration for content-capture mode (default: metadata-only)
CAPTURE_CONTENT = False

# Per-model pricing table (USD per 1,000 tokens).
# Current as of July 2026. Anthropic prices are per-MTok list prices / 1000:
#   Fable 5 $10/$50, Opus 4.8/4.7/4.6 $5/$25, Sonnet 5 $3/$15, Haiku 4.5 $1/$5.
# Note: claude-sonnet-5 has an introductory $2/$10 rate through 2026-08-31;
# the standard rate is used here so estimates stay valid after it lapses.
MODEL_PRICING = {
    # --- Anthropic (current) ---
    "claude-fable-5": {"input": 0.010, "output": 0.050},
    "claude-opus-4-8": {"input": 0.005, "output": 0.025},
    "claude-opus-4-7": {"input": 0.005, "output": 0.025},
    "claude-opus-4-6": {"input": 0.005, "output": 0.025},
    "claude-sonnet-5": {"input": 0.003, "output": 0.015},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
    # --- Anthropic (legacy, kept for historical traces) ---
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    # --- OpenAI (legacy entries, kept for historical traces) ---
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
    # --- Simulation ---
    "mock-model": {"input": 0.0001, "output": 0.0002},
}
