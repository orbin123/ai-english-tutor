"""Unit tests for the external-credential checker.

The probes themselves talk to third parties and are not exercised here. What
is worth pinning down is the harness around them: a failing probe must not
abort the run or hide the other results, a switched-off feature must report
SKIP rather than FAIL, and the exit code must reflect only real failures.
"""

from __future__ import annotations

import pytest

from scripts.check_external_services import CHECKS, Result, Skip, render, run_one


@pytest.mark.asyncio
async def test_successful_probe_reports_pass() -> None:
    async def probe() -> str:
        return "all good"

    result = await run_one("thing", probe)

    assert result.status == "PASS"
    assert result.detail == "all good"


@pytest.mark.asyncio
async def test_skip_is_not_a_failure() -> None:
    """A disabled feature is a configuration fact, not a broken credential."""

    async def probe() -> str:
        raise Skip("ENABLE_DEEPGRAM=false")

    result = await run_one("deepgram", probe)

    assert result.status == "SKIP"
    assert result.detail == "ENABLE_DEEPGRAM=false"


@pytest.mark.asyncio
async def test_failing_probe_is_captured_rather_than_raised() -> None:
    """One dead provider must not stop the other ten probes from reporting."""

    async def probe() -> str:
        raise RuntimeError("HTTP 401")

    result = await run_one("resend", probe)

    assert result.status == "FAIL"
    assert result.detail == "RuntimeError: HTTP 401"


@pytest.mark.asyncio
async def test_timeout_is_reported_as_a_failure() -> None:
    async def probe() -> str:
        raise TimeoutError

    result = await run_one("openai-chat", probe)

    assert result.status == "FAIL"
    assert "TimeoutError" in result.detail


def test_every_probe_is_registered_under_a_stable_name() -> None:
    """The names double as CLI arguments, so they are part of the interface."""
    assert set(CHECKS) == {
        "openai-chat",
        "openai-embeddings",
        "openai-models",
        "pinecone",
        "deepgram",
        "azure-speech",
        "azure-blob",
        "azure-postgres",
        "resend",
        "razorpay",
        "langsmith",
    }


def test_render_emits_one_line_per_result(capsys: pytest.CaptureFixture[str]) -> None:
    render(
        [
            Result("openai-chat", "PASS", "answered 'ok'", 0.5),
            Result("resend", "FAIL", "RuntimeError: HTTP 401", 1.25),
        ],
        colour=False,
    )

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert "PASS" in lines[0] and "openai-chat" in lines[0]
    assert "FAIL" in lines[1] and "HTTP 401" in lines[1]


def test_render_without_colour_emits_no_escape_codes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The VM runs this through Run Command, where escape codes are noise."""
    render([Result("pinecone", "PASS", "1024d cosine", 0.1)], colour=False)

    assert "\033" not in capsys.readouterr().out
