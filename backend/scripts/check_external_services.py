"""Verify every external credential this deployment depends on.

Run it locally, and run it on the production VM against the real environment
file. It answers one question: are the keys in this environment actually
present, valid, and pointing at the right resource?

Each probe is read-only and effectively free. Nothing here generates an image,
synthesizes speech, transcribes audio, or moves money: the paid endpoints are
verified by listing models or issuing a token instead. The single exception is
Razorpay, which creates a one-rupee order in TEST mode and reads it straight
back, because there is no cheaper way to prove the key pair signs correctly.

Probes for features that are switched off report SKIP rather than failing, so
the output reflects the configuration actually in force.

    uv run python scripts/check_external_services.py
    uv run python scripts/check_external_services.py pinecone deepgram

Exits non-zero if any probe fails.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Allow `uv run python scripts/check_external_services.py` from anywhere, the
# same way the seed scripts do.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402

Status = Literal["PASS", "FAIL", "SKIP"]

# Long enough for a cold provider connection from an Indian region, short
# enough that a dead endpoint does not hang the whole run.
_TIMEOUT_S = 30.0


class Skip(Exception):
    """Raised by a probe when its feature is switched off in this environment."""


@dataclass(frozen=True)
class Result:
    name: str
    status: Status
    detail: str
    seconds: float


# --------------------------------------------------------------------- OpenAI


async def check_openai_chat() -> str:
    """One-token completion on the model the interactive agents actually use."""
    import openai

    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=_TIMEOUT_S)
    response = await client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_completion_tokens=5,
    )
    reply = (response.choices[0].message.content or "").strip()
    return f"{settings.OPENAI_CHAT_MODEL} answered {reply!r}"


async def check_openai_embeddings() -> str:
    """Embed one word through the real generator and check the dimension.

    A dimension mismatch against the Pinecone index is the classic silent
    failure here: every upsert is rejected and mentor notes quietly go empty.
    """
    from app.ai.embeddings.embedding_generator import OpenAIEmbeddingGenerator

    vector = await OpenAIEmbeddingGenerator().embed("ping")
    expected = settings.OPENAI_EMBEDDING_DIMENSIONS
    if len(vector) != expected:
        raise RuntimeError(f"expected {expected} dimensions, got {len(vector)}")
    return f"{settings.OPENAI_EMBEDDING_MODEL} returned {len(vector)} dimensions"


async def check_openai_models() -> str:
    """Confirm the TTS, STT and image models are visible to this key.

    Membership only. Actually calling them would cost money on every run.
    """
    import openai

    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=_TIMEOUT_S)
    available = {model.id async for model in client.models.list()}

    wanted = {
        "TTS": settings.OPENAI_TTS_MODEL,
        "STT": settings.OPENAI_STT_MODEL,
        "judge": settings.AI_EVAL_JUDGE_MODEL,
        "task generation": settings.OPENAI_TASKGEN_MODEL,
    }
    if settings.ENABLE_IMAGE_GENERATION:
        wanted["image"] = settings.OPENAI_IMAGE_MODEL

    missing = [
        f"{label} ({name})" for label, name in wanted.items() if name not in available
    ]
    if missing:
        raise RuntimeError("not available to this key: " + ", ".join(missing))
    return f"all {len(wanted)} configured models available"


# ------------------------------------------------------------------- Pinecone


async def check_pinecone() -> str:
    """Assert the index exists with the dimension and metric the app assumes.

    The app never creates the index. If it is missing, or was created at the
    default 1536 dimensions, every upsert fails silently and the feedback
    memory stays permanently empty.
    """
    if not settings.ENABLE_RAG_FEEDBACK:
        raise Skip("ENABLE_RAG_FEEDBACK=false")

    from pinecone import Pinecone

    def _describe() -> tuple[object, object]:
        client = Pinecone(api_key=settings.PINECONE_API_KEY)
        description = client.describe_index(settings.PINECONE_INDEX_NAME)
        stats = client.Index(settings.PINECONE_INDEX_NAME).describe_index_stats()
        return description, stats

    description, stats = await asyncio.to_thread(_describe)

    dimension = int(getattr(description, "dimension", 0))
    metric = str(getattr(description, "metric", ""))
    expected = settings.OPENAI_EMBEDDING_DIMENSIONS
    if dimension != expected:
        raise RuntimeError(
            f"index dimension is {dimension}, but OPENAI_EMBEDDING_DIMENSIONS is "
            f"{expected} — every upsert would be rejected"
        )
    if metric != "cosine":
        raise RuntimeError(f"index metric is {metric!r}, expected 'cosine'")

    namespaces = dict(getattr(stats, "namespaces", {}) or {})
    target = settings.PINECONE_FEEDBACK_NAMESPACE
    if target in namespaces:
        count = getattr(namespaces[target], "vector_count", namespaces[target])
        namespace_note = f"namespace {target!r} holds {count} vectors"
    else:
        # Not an error: the namespace is created on first upsert.
        namespace_note = f"namespace {target!r} not created yet (empty index)"
    return f"{settings.PINECONE_INDEX_NAME}: {dimension}d cosine, {namespace_note}"


# ------------------------------------------------------------------- Deepgram


async def check_deepgram() -> str:
    """List projects — the cheapest call that proves the key is live."""
    if not settings.ENABLE_DEEPGRAM:
        raise Skip("ENABLE_DEEPGRAM=false")
    if not settings.DEEPGRAM_API_KEY:
        raise RuntimeError("ENABLE_DEEPGRAM=true but DEEPGRAM_API_KEY is empty")

    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        response = await client.get(
            "https://api.deepgram.com/v1/projects",
            headers={"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"},
        )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:120]}")
    projects = response.json().get("projects", [])
    return f"{len(projects)} project(s) visible"


# --------------------------------------------------------------- Azure Speech


async def check_azure_speech() -> str:
    """Issue a short-lived auth token from the pronunciation region.

    Token issue is free and proves both the key and the region, which is the
    pair that actually goes wrong.
    """
    region = settings.AZURE_SPEECH_REGION
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        response = await client.post(
            f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
            headers={"Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY},
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"HTTP {response.status_code} from region {region!r}: {response.text[:120]}"
        )
    return f"region {region} issued a token"


# ----------------------------------------------------------------- Azure Blob


async def check_azure_blob() -> str:
    """List containers on both storage accounts via the ambient identity.

    On the VM this exercises the managed identity; locally it uses whatever
    DefaultAzureCredential finds, normally the signed-in az CLI user.
    """
    if settings.STORAGE_BACKEND != "azure":
        raise Skip(f"STORAGE_BACKEND={settings.STORAGE_BACKEND}")

    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    accounts = {
        settings.AZURE_BLOB_PUBLIC_ACCOUNT_URL: {settings.AZURE_BLOB_PUBLIC_CONTAINER},
        settings.AZURE_BLOB_PRIVATE_ACCOUNT_URL: {
            settings.AZURE_BLOB_PRIVATE_CONTAINER,
            settings.AZURE_BLOB_INTERNAL_CONTAINER,
        },
    }

    def _list(account_url: str) -> set[str]:
        service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        return {container.name for container in service.list_containers()}

    checked = 0
    for account_url, expected in accounts.items():
        found = await asyncio.to_thread(_list, account_url)
        missing = expected - found
        if missing:
            host = account_url.split("//", 1)[-1].split(".", 1)[0]
            raise RuntimeError(f"{host} is missing container(s): {sorted(missing)}")
        checked += len(expected)
    return f"{checked} container(s) reachable across 2 accounts"


# ------------------------------------------------------------- Azure Postgres


async def check_azure_postgres() -> str:
    """Connect with a fresh Entra token and run SELECT 1.

    This is the probe that fails when the VM identity is not mapped to the
    PostgreSQL role, which no amount of connection-string checking catches.
    """
    if settings.DATABASE_AUTH_MODE != "azure-managed-identity":
        raise Skip(f"DATABASE_AUTH_MODE={settings.DATABASE_AUTH_MODE}")

    from sqlalchemy import create_engine, text

    from app.core.azure_postgres import install_azure_postgres_auth

    def _connect() -> str:
        engine = create_engine(
            settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1),
            pool_pre_ping=True,
        )
        install_azure_postgres_auth(engine)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                version = connection.execute(text("SHOW server_version")).scalar_one()
            return str(version)
        finally:
            engine.dispose()

    version = await asyncio.to_thread(_connect)
    return f"Entra token accepted, PostgreSQL {version}"


# --------------------------------------------------------------------- Resend


async def check_resend() -> str:
    """List domains. Proves the key without sending an email."""
    if settings.EMAIL_PROVIDER != "resend":
        raise Skip(f"EMAIL_PROVIDER={settings.EMAIL_PROVIDER}")
    if not settings.RESEND_API_KEY:
        raise RuntimeError("EMAIL_PROVIDER=resend but RESEND_API_KEY is empty")

    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        response = await client.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        )

    # Resend distinguishes the two failures clearly, and only one is a problem:
    #   400 validation_error   -> the key is not a real key
    #   401 restricted_api_key -> the key IS real, but is sending-only
    # A sending-only key is the correct, least-privilege choice for this app,
    # so treat it as a pass. The tradeoff is that domain verification cannot be
    # read back from here; check that in the Resend dashboard.
    if response.status_code == 401 and "restricted_api_key" in response.text:
        return "key valid (sending-only, so domain status is not readable here)"
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:120]}")

    payload = response.json()
    domains = payload.get("data", payload) if isinstance(payload, dict) else payload
    verified = [
        domain.get("name")
        for domain in domains or []
        if isinstance(domain, dict) and domain.get("status") == "verified"
    ]
    if verified:
        return f"verified domain(s): {', '.join(str(name) for name in verified)}"
    # Sandbox mode still works, but only to the account owner's address.
    return (
        "key valid, but NO verified domain — sandbox only delivers to the account owner"
    )


# ------------------------------------------------------------------- Razorpay


async def check_razorpay() -> str:
    """Create a one-rupee order and read it back.

    Test mode, so nothing is charged and no checkout is completed. This is the
    only probe that writes, because order creation is what actually exercises
    the key-id/secret pair.
    """
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise Skip("Razorpay keys not configured (mock provider in use)")

    from app.payments.razorpay_client import RAZORPAY_API_BASE

    live_mode = not settings.RAZORPAY_KEY_ID.startswith("rzp_test_")
    if live_mode:
        raise Skip("LIVE Razorpay key — refusing to create an order against it")

    auth = (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    async with httpx.AsyncClient(timeout=_TIMEOUT_S, auth=auth) as client:
        created = await client.post(
            f"{RAZORPAY_API_BASE}/orders",
            json={
                "amount": 100,  # paise
                "currency": "INR",
                "receipt": f"healthcheck-{int(time.time())}",
                "notes": {"purpose": "check_external_services probe"},
            },
        )
        if created.status_code not in (200, 201):
            raise RuntimeError(f"HTTP {created.status_code}: {created.text[:160]}")
        order_id = created.json()["id"]

        fetched = await client.get(f"{RAZORPAY_API_BASE}/orders/{order_id}")
    if fetched.status_code != 200:
        raise RuntimeError(f"order {order_id} created but not readable back")
    return f"test-mode order {order_id} created and read back"


# ------------------------------------------------------------------ LangSmith


async def check_langsmith() -> str:
    """Confirm the tracing endpoint accepts this key."""
    if not settings.LANGCHAIN_TRACING_V2:
        raise Skip("LANGCHAIN_TRACING_V2=false")

    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        response = await client.get(
            f"{settings.LANGCHAIN_ENDPOINT.rstrip('/')}/info",
            headers={"x-api-key": settings.LANGCHAIN_API_KEY},
        )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:120]}")
    return f"endpoint reachable, project {settings.LANGCHAIN_PROJECT!r}"


# ----------------------------------------------------------------- the runner

CHECKS: dict[str, Callable[[], Awaitable[str]]] = {
    "openai-chat": check_openai_chat,
    "openai-embeddings": check_openai_embeddings,
    "openai-models": check_openai_models,
    "pinecone": check_pinecone,
    "deepgram": check_deepgram,
    "azure-speech": check_azure_speech,
    "azure-blob": check_azure_blob,
    "azure-postgres": check_azure_postgres,
    "resend": check_resend,
    "razorpay": check_razorpay,
    "langsmith": check_langsmith,
}

_COLOURS = {"PASS": "\033[32m", "FAIL": "\033[31m", "SKIP": "\033[90m"}
_RESET = "\033[0m"


async def run_one(name: str, probe: Callable[[], Awaitable[str]]) -> Result:
    started = time.monotonic()
    try:
        detail = await probe()
        status: Status = "PASS"
    except Skip as skip:
        detail, status = str(skip), "SKIP"
    except Exception as exc:  # noqa: BLE001 - every failure belongs in the table
        detail, status = f"{type(exc).__name__}: {exc}", "FAIL"
    return Result(name, status, detail, time.monotonic() - started)


def render(results: list[Result], *, colour: bool) -> None:
    width = max(len(result.name) for result in results)
    for result in results:
        start = _COLOURS[result.status] if colour else ""
        end = _RESET if colour else ""
        print(
            f"  {start}{result.status:<4}{end}  {result.name:<{width}}  "
            f"{result.seconds:5.2f}s  {result.detail}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "checks",
        nargs="*",
        metavar="CHECK",
        help="probes to run (default: all). One or more of: "
        + ", ".join(sorted(CHECKS)),
    )
    parser.add_argument("--no-colour", action="store_true", help="plain output")
    args = parser.parse_args()

    unknown = [name for name in args.checks if name not in CHECKS]
    if unknown:
        parser.error(
            f"unknown probe(s): {', '.join(unknown)}. "
            f"Available: {', '.join(sorted(CHECKS))}"
        )

    selected = {name: CHECKS[name] for name in (args.checks or CHECKS)}

    print(f"Environment: {settings.environment}")
    print(f"Checking {len(selected)} external service(s)\n")

    results = asyncio.run(
        _gather(selected),
    )
    render(results, colour=not args.no_colour and sys.stdout.isatty())

    failed = [result for result in results if result.status == "FAIL"]
    skipped = [result for result in results if result.status == "SKIP"]
    passed = len(results) - len(failed) - len(skipped)
    print(f"\n{passed} passed, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("\nFailed: " + ", ".join(result.name for result in failed))
    return 1 if failed else 0


async def _gather(selected: dict[str, Callable[[], Awaitable[str]]]) -> list[Result]:
    # Probes hit unrelated providers, so run them together rather than serially.
    return list(
        await asyncio.gather(
            *(run_one(name, probe) for name, probe in selected.items())
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
