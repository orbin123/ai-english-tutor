"""Lightweight token / cost tracking for LLM calls.

Goal: log every LLM call with model, tokens, and approximate cost so we
can see spend per request in the logs (and later, per user).

Why not a full metrics system yet? Premature. We just need *visibility*
during MVP — "how many tokens did the feedback agent use today?". A
proper Prometheus / DB-backed usage tracker comes in Phase 6 when we
add per-user budget caps.

Pricing (USD per 1M tokens) — keep this list small and current.
Source: https://openai.com/pricing — last checked 2026-06.

If a model is missing here we just log tokens without cost (no crash).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pricing table — USD per 1 million tokens.
# ---------------------------------------------------------------------------
_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    # model_name             (input_$, output_$)
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    # Legacy models kept so historical ai_request_logs / cost roll-ups resolve.
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}


@dataclass
class UsageRecord:
    """One LLM call's accounting summary."""

    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float | None  # None when the model isn't in our pricing table

    def as_log_dict(self) -> dict:
        """Shape suitable for structured logging."""
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
        }


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Return the approximate USD cost for one call, or None if unknown."""
    pricing = _PRICING_PER_1M.get(model)
    if pricing is None:
        return None
    in_price, out_price = pricing
    cost = (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    # 6 decimals = sub-penny precision; good enough for daily roll-ups
    return round(cost, 6)


def log_usage(record: UsageRecord) -> None:
    """Emit a single structured log line. One line per LLM call.

    We deliberately log at INFO so this shows up in normal operation
    without flipping debug. If it gets noisy, we'll downgrade later.
    """
    logger.info("llm_usage %s", record.as_log_dict())
    if record.total_tokens > 0:
        from app.modules.quotas.constants import QuotaMetric
        from app.modules.quotas.service import consume_quota

        consume_quota(QuotaMetric.LLM_TOKENS, amount=record.total_tokens)
