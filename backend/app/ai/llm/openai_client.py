"""OpenAI implementation of ILLMClient (LangChain-backed).

Design notes:

1. Built on `langchain_openai.ChatOpenAI` so:
   - LangSmith tracing happens automatically (env vars already set)
   - `.with_structured_output(...)` keeps working for legacy agents
   - Swapping to another LangChain-supported provider is one line

2. Retries are handled HERE, not in callers. We retry up to 3 times
   on transient failures (timeout, rate limit, 5xx). Validation errors
   are NOT retried — the prompt is wrong, retrying won't help.

3. Every successful call logs a UsageRecord at INFO level. Every
   failure logs once at WARNING. Callers don't need to log anything.

4. Provider-specific exceptions are translated into our LLMError
   family at the boundary. Nothing leaks `openai.RateLimitError`
   upward — agents catch `LLMError` only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from functools import lru_cache
from typing import Any, TypeVar

import openai
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr, ValidationError

from app.ai.llm.exceptions import (
    LLMAuthError,
    LLMError,
    LLMProviderError,
    LLMRateLimited,
    LLMTimeout,
    LLMValidationError,
)
from app.ai.llm.usage import UsageRecord, estimate_cost, log_usage
from app.core.ai_concurrency import ai_provider_slot
from app.core.config import settings

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Defaults — single source of truth for "which model + which knobs".
# The chat model + reasoning effort come from settings so the whole app can be
# retuned from env without a code change. Override per-call via constructor
# args if needed (e.g. a different model for the judge).
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = settings.OPENAI_CHAT_MODEL
_DEFAULT_REASONING_EFFORT = settings.OPENAI_REASONING_EFFORT
_DEFAULT_TEMPERATURE = 0.7
# Reasoning models (gpt-5, o-series) spend output tokens "thinking" and are
# slower than gpt-4o — 30s risked task-gen timeouts on the learner's path.
_DEFAULT_TIMEOUT_S = 60.0
_MAX_RETRIES = 3  # ChatOpenAI's built-in retry handles transient errors


def _is_reasoning_model(model: str) -> bool:
    """True for models that reject a custom `temperature`.

    OpenAI reasoning models (the gpt-5 family and the o1/o3/o4 series) only
    accept the default temperature; any explicit value 400s at the API. They
    take a `reasoning_effort` knob instead. We detect them by id prefix so the
    client can drop temperature and (optionally) pass reasoning_effort.
    """
    m = model.lower()
    return m.startswith("gpt-5") or m.startswith(("o1", "o3", "o4"))


class OpenAILLMClient:
    """Concrete `ILLMClient` backed by OpenAI through LangChain.

    Stateless w.r.t. user data — safe to reuse as a process-wide
    singleton (see `get_default_llm_client()` below).
    """

    def __init__(
        self,
        *,
        model: str = _DEFAULT_MODEL,
        temperature: float = _DEFAULT_TEMPERATURE,
        reasoning_effort: str | None = _DEFAULT_REASONING_EFFORT,
        timeout: float = _DEFAULT_TIMEOUT_S,
        max_retries: int = _MAX_RETRIES,
        usage_sink: Callable[[UsageRecord], None] | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._max_retries = max_retries
        self._is_reasoning = _is_reasoning_model(model)
        self._reasoning_effort = reasoning_effort if self._is_reasoning else None
        # Optional hook invoked with the UsageRecord after every call. Used by
        # the AIRequestLog instrumentation seam (LoggingLLMClient) to capture
        # token counts; default None keeps the client's behaviour unchanged.
        self._usage_sink = usage_sink
        # ChatOpenAI handles its own retry/backoff for transient errors.
        # We tell it how many tries; it does exponential backoff internally.
        self._chat = self._build_chat(temperature)

    def _build_chat(self, temperature: float) -> ChatOpenAI:
        """Construct a ChatOpenAI honouring the reasoning/non-reasoning split.

        Reasoning models (gpt-5, o-series) reject a custom `temperature` and
        take `reasoning_effort` instead; sending temperature 400s. So we omit
        temperature for them and pass reasoning_effort when set. Non-reasoning
        models keep the original behaviour (temperature passed through).
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "timeout": self._timeout,
            "max_retries": self._max_retries,
            "api_key": SecretStr(settings.OPENAI_API_KEY),
        }
        if self._is_reasoning:
            if self._reasoning_effort:
                kwargs["reasoning_effort"] = self._reasoning_effort
        else:
            kwargs["temperature"] = temperature
        return ChatOpenAI(**kwargs)

    @property
    def model(self) -> str:
        """The model id this client targets (for logging / pricing)."""
        return self._model

    # ------------------------------------------------------------------
    # Public — generate_text
    # ------------------------------------------------------------------
    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> str:
        """Plain text round-trip. Returns the assistant's reply."""
        chat = self._maybe_rebind_temperature(temperature)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        try:
            async with ai_provider_slot():
                response = await chat.ainvoke(messages)
        except Exception as exc:
            raise self._translate_exception(exc) from exc

        self._log_response_usage(response)
        # ChatOpenAI returns an AIMessage; .content is the string.
        return str(response.content)

    # ------------------------------------------------------------------
    # Public — stream_text
    # ------------------------------------------------------------------
    async def stream_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Stream a plain text assistant reply chunk-by-chunk."""
        chat = self._maybe_rebind_temperature(temperature)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            async with ai_provider_slot():
                async for chunk in chat.astream(messages):
                    text = self._chunk_content_to_text(getattr(chunk, "content", ""))
                    if text:
                        yield text
        except Exception as exc:
            raise self._translate_exception(exc) from exc

    # ------------------------------------------------------------------
    # Public — generate_structured (the workhorse)
    # ------------------------------------------------------------------
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[T],
        temperature: float | None = None,
    ) -> T:
        """Round-trip that returns a validated Pydantic instance.

        Uses LangChain's structured-output binding so the LLM is
        constrained at the API level (function-calling under the hood).
        That gives us very high schema-conformance without manual JSON
        parsing.
        """
        chat = self._maybe_rebind_temperature(temperature)
        # include_raw=True returns {"raw": AIMessage, "parsed": <model>,
        # "parsing_error": <exc|None>}. The raw AIMessage carries
        # usage_metadata, which a plain with_structured_output() drops — this
        # is what lets us price + log token usage on structured calls.
        structured_chat = chat.with_structured_output(output_model, include_raw=True)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            async with ai_provider_slot():
                result = await structured_chat.ainvoke(messages)
        except ValidationError as exc:
            # The LLM answered, but the answer didn't match the schema.
            # Don't retry — the prompt or schema needs work.
            log.warning(
                "llm_structured_validation_failed",
                model=self._model,
                schema=output_model.__name__,
                error=str(exc),
            )
            raise LLMValidationError(
                f"LLM output failed schema validation for "
                f"{output_model.__name__}: {exc}"
            ) from exc
        except Exception as exc:
            raise self._translate_exception(exc) from exc

        # With include_raw=True the result is a dict; emit usage off the raw
        # AIMessage even when parsing later fails, so the call is still logged.
        raw = result.get("raw") if isinstance(result, dict) else None
        if raw is not None:
            self._log_response_usage(raw)

        # A schema mismatch is surfaced here (not raised by ainvoke) when
        # include_raw=True. Treat it the same as the ValidationError path.
        parsing_error = (
            result.get("parsing_error") if isinstance(result, dict) else None
        )
        if parsing_error is not None:
            log.warning(
                "llm_structured_validation_failed",
                model=self._model,
                schema=output_model.__name__,
                error=str(parsing_error),
            )
            raise LLMValidationError(
                f"LLM output failed schema validation for "
                f"{output_model.__name__}: {parsing_error}"
            )

        parsed = result.get("parsed") if isinstance(result, dict) else result
        if parsed is None:
            raise LLMValidationError(
                f"LLM returned no parseable output for {output_model.__name__}"
            )

        log.info(
            "llm_structured_ok",
            model=self._model,
            schema=output_model.__name__,
        )
        # `parsed` is already an instance of `output_model` — LangChain
        # validated it for us. Return as-is.
        return parsed  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Public — escape hatch for legacy agents
    # ------------------------------------------------------------------
    def raw_chat_model(self) -> ChatOpenAI:
        """Return the underlying ChatOpenAI for code that uses LangChain
        APIs directly (e.g. `.with_structured_output(...).ainvoke(...)`).

        Existing agents use this. New code should prefer
        `generate_structured(...)`.
        """
        return self._chat

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _maybe_rebind_temperature(self, temperature: float | None) -> ChatOpenAI:
        """Return a ChatOpenAI with a temperature override, or the
        default instance if no override is given.

        ChatOpenAI is cheap to construct — fine to spin a new one when
        a per-call temperature is requested. Keeps the default instance
        pure (same temperature for the whole app).

        For reasoning models (gpt-5, o-series) this is a deliberate no-op:
        those models reject a custom temperature, so per-call overrides from
        the evaluator/feedback/task-gen agents are silently ignored rather
        than 400ing. Effort is governed by `reasoning_effort`, not temperature.
        """
        if (
            self._is_reasoning
            or temperature is None
            or temperature == self._temperature
        ):
            return self._chat
        return self._build_chat(temperature)

    def _log_response_usage(self, response: Any) -> None:
        """Pull token counts off the AIMessage and emit one log line."""
        # LangChain attaches usage_metadata on the AIMessage when the
        # provider returned it. Defensively handle absence.
        meta = getattr(response, "usage_metadata", None) or {}
        input_tokens = int(meta.get("input_tokens", 0) or 0)
        output_tokens = int(meta.get("output_tokens", 0) or 0)
        total = int(meta.get("total_tokens", input_tokens + output_tokens))
        cost = estimate_cost(self._model, input_tokens, output_tokens)
        record = UsageRecord(
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            cost_usd=cost,
        )
        log_usage(record)
        if self._usage_sink is not None:
            # Best-effort: a sink failure must never break the LLM call.
            try:
                self._usage_sink(record)
            except Exception:  # pragma: no cover - defensive
                log.warning("usage_sink_raised", exc_info=True)

    @classmethod
    def _chunk_content_to_text(cls, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return str(content) if content else ""

    @staticmethod
    def _translate_exception(exc: Exception) -> LLMError:
        """Map provider-specific exceptions into our LLMError family.

        Keeps callers simple — they catch `LLMError` (or one of its
        subclasses) instead of N OpenAI exception types. Order matters:
        check the most-specific subclass first.
        """
        if isinstance(exc, openai.AuthenticationError):
            return LLMAuthError(f"OpenAI auth failed: {exc}")
        if isinstance(exc, openai.RateLimitError):
            return LLMRateLimited(f"OpenAI rate limit: {exc}")
        if isinstance(exc, openai.APITimeoutError):
            return LLMTimeout(f"OpenAI request timed out: {exc}")
        if isinstance(exc, openai.APIError):
            return LLMProviderError(f"OpenAI API error: {exc}")
        # Unknown provider error — wrap it so callers still see LLMError.
        return LLMProviderError(f"Unexpected LLM failure: {exc}")


# ---------------------------------------------------------------------------
# Process-wide singleton.
#
# Why a singleton? Constructing ChatOpenAI does some work (validates the
# API key by calling the API once with some configurations). Building it
# per-request adds latency and is wasteful. The instance is stateless
# w.r.t. user data, so sharing is safe.
#
# `lru_cache` gives us lazy + thread-safe initialization. Tests that
# need a fresh client can call `get_default_llm_client.cache_clear()`.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_default_llm_client() -> OpenAILLMClient:
    """Return the shared default LLM client. Lazy + cached."""
    return OpenAILLMClient()
