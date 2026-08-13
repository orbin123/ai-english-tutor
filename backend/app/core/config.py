"""Application configuration loaded from environment variables."""

import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration object.

    Reads values from .env file at project root.
    All fields are type-validated on startup - missing/wrong values
    will crash the app immediately with a clear error.
    """

    # Application
    environment: str = "development"
    debug: bool = True
    log_level: str = "info"

    # CORS — comma-separated allowed origins per environment. The dev default
    # matches the local Next.js server; prod MUST override with the real
    # frontend origin(s). The prod guard below rejects any localhost origin.
    cors_origins: str = "http://localhost:3000"

    # SQL statement logging. Decoupled from `debug` so prod can keep generic
    # debug off without ever echoing queries (which would leak schema/PII to
    # logs). The prod guard forces this False when environment=production.
    sql_echo: bool = False

    # Sentry error tracking. Empty = disabled (local/test default).
    sentry_dsn: str = ""
    # Fraction of requests traced for performance (0.0–1.0). 0.1 = 10%.
    sentry_traces_sample_rate: float = 0.1

    # Schema-boundary strictness. When False (prod default during rollout), a
    # contract-projection or agent-input validation failure is logged and the
    # legacy payload is delivered unchanged. When True (set in tests), the same
    # failure raises so contract violations surface loudly instead of silently
    # falling back. Env: STRICT_CONTRACTS.
    strict_contracts: bool = True

    # Database
    database_url: str
    DB_POOL_SIZE: int = Field(default=3, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=2, ge=0)
    DB_POOL_TIMEOUT: float = Field(default=10.0, gt=0)

    # Gunicorn worker count. The production entrypoint reads the same
    # WEB_CONCURRENCY variable, so configuration validation and runtime cannot
    # silently disagree about whether a process-local limiter is safe.
    WEB_CONCURRENCY: int = Field(default=1, ge=1)

    # Redis is optional in the single-worker zero-cost topology. Select Redis
    # explicitly for a multi-worker deployment; an empty URL is valid when the
    # process-local limiter is selected.
    redis_url: str | None = None

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Billing / access
    # A one-time course purchase grants this many years of access from the
    # purchase date. Surfaced in the admin Subscribers view as access_expires_at.
    ACCESS_WINDOW_YEARS: int = 2
    # Free-trial length. Stored on the subscription row when the user
    # starts their trial (start-trial endpoint).
    TRIAL_DAYS: int = 7

    # Email delivery — "console" logs emails to the app logger (dev/test
    # default, the OTP shows up in the uvicorn console); "resend" sends real
    # email via the Resend API. Missing RESEND_API_KEY falls back to console.
    EMAIL_PROVIDER: str = "console"
    RESEND_API_KEY: str = ""
    # AWS SES region for the "ses" provider. Auth is via the ambient AWS env
    # (ECS task role granted ses:SendEmail) — no API key in env.
    SES_REGION: str = "us-east-1"
    # Resend sandbox (no verified domain) requires the resend.dev sender and
    # only delivers to the Resend account owner's address.
    EMAIL_FROM: str = "LingosAI <onboarding@resend.dev>"
    # Where the marketing-site contact form delivers submissions.
    CONTACT_RECIPIENT_EMAIL: str = "support@lingosai.com"

    # Email OTP verification. The pepper keys the HMAC of stored codes —
    # set a dedicated random value in prod; empty falls back to jwt_secret.
    OTP_HASHING_SECRET: str = ""
    OTP_LENGTH: int = 6
    OTP_TTL_MINUTES: int = 10
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    OTP_MAX_SENDS_PER_HOUR: int = 5
    OTP_MAX_VERIFY_ATTEMPTS: int = 5
    # Local dev only — accepts "123456" without the HMAC check. NEVER true in prod.
    DEV_OTP_BYPASS: bool = False

    # Auth sessions (refresh tokens). Access tokens issued by the session
    # flow are short; the refresh cookie keeps users logged in. The legacy
    # jwt_access_token_expire_minutes stays for non-session tokens (e.g.
    # OAuth relink state).
    ACCESS_TOKEN_TTL_MINUTES: int = 20
    REFRESH_TOKEN_TTL_DAYS: int = 30
    REFRESH_TOKEN_REMEMBER_DAYS: int = 90
    # False for http://localhost dev; MUST be true behind https in prod.
    # The refresh cookie is SameSite=Lax — frontend and backend must share a
    # registrable domain in prod (subdomains are fine).
    AUTH_COOKIE_SECURE: bool = False

    # Razorpay (Test Mode) — wired in Phase 4; placeholders so .env can be
    # filled ahead of time.
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # AI / LLM
    OPENAI_API_KEY: str
    # Default chat model for the INTERACTIVE agents on the learner's critical
    # path (teacher, evaluator, feedback, planner, personalization, RAG mentor
    # notes, IELTS + diagnosis agents). `gpt-4.1-mini` is a NON-reasoning model:
    # it returns first tokens in ~1s (the streamed teaching turn needs that — a
    # reasoning model's think-then-generate latency blew past the teaching
    # stream timeout and silently fell back) and it HONORS `temperature`, so the
    # teacher's 0.4 / evaluator's 0.2 / feedback's 0.4 actually take effect.
    # Task generation and the quality judge deliberately stay on a reasoning
    # model (gpt-5) where think-time improves output — they're wired separately
    # (OPENAI_TASKGEN_MODEL / AI_EVAL_JUDGE_MODEL), not from this default.
    OPENAI_CHAT_MODEL: str = "gpt-4.1-mini"
    # Reasoning effort: minimal | low | medium | high. Only sent when the chosen
    # model is a reasoning model (gpt-5 / o-series); the client drops it for
    # non-reasoning models like the gpt-4.1-mini default above.
    OPENAI_REASONING_EFFORT: str = "medium"
    # Task generation runs on its OWN client, NOT the interactive default above.
    # Kept on the cheap non-reasoning `gpt-4o-mini` for cost — a reasoning model
    # (gpt-5) at high effort burns far too many reasoning tokens for a per-activity
    # call. Wired as a dedicated client in app/ai/sessions/factory.py; only the
    # task generator uses it. `OPENAI_TASKGEN_REASONING_EFFORT` is INERT for a
    # non-reasoning model (the client only sends it to reasoning models) — it's
    # kept so the model can be swapped back to a reasoning one from .env alone.
    OPENAI_TASKGEN_MODEL: str = "gpt-4o-mini"
    OPENAI_TASKGEN_REASONING_EFFORT: str = "high"
    # Off by default (data-residency, audit A5): tracing ships learner content
    # to LangSmith, so it must be enabled consciously. Dev .env can set it True.
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str
    LANGCHAIN_PROJECT: str = "ai-english-coach"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    # AI observability — when True, each instrumented LLM collaborator call
    # writes one operational row to ai_request_logs (latency, tokens, status,
    # trace_id). Best-effort and off the request session; flip to False to kill
    # the seam entirely if it ever misbehaves.
    AI_REQUEST_LOGGING_ENABLED: bool = True

    # Rate limiting (AI endpoints) — per-user sliding-window limits on every
    # route that spends money on an AI provider call. "memory" is deliberately
    # process-local and therefore requires exactly one application worker.
    # Select "redis" for shared buckets in a multi-worker deployment; runtime
    # Redis failures still degrade to memory so active requests can complete.
    AI_RATE_LIMIT_ENABLED: bool = True
    # Default Redis preserves the frozen AWS recovery configuration when the
    # new selector is absent. Local and future Azure examples explicitly choose
    # memory, making the one-worker tradeoff intentional rather than fallback.
    AI_RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "redis"
    AI_RATE_LIMIT_PER_MINUTE: int = 30
    AI_RATE_LIMIT_TRANSCRIBE_PER_MINUTE: int = 20
    # Process-local ceiling across provider calls. The zero-cost deployment
    # runs one worker, so this single semaphore bounds LLM, image, and audio
    # concurrency without another infrastructure dependency.
    AI_MAX_CONCURRENT_JOBS: int = Field(default=3, ge=1)
    MAX_AUDIO_UPLOAD_BYTES: int = Field(default=5 * 1024 * 1024, ge=1)
    MAX_AUDIO_DURATION_SECONDS: float = Field(default=45.0, gt=0)
    # Learning-session WebSocket: max incoming messages per user per minute.
    WS_MESSAGE_RATE_PER_MINUTE: int = 20
    # A2Z game: max Deepgram stream connections per user per minute
    # (connection-level only — audio frames inside a stream are never throttled).
    WS_A2Z_STREAMS_PER_MINUTE: int = 10

    # AI quality (LLM-as-judge, Part B Phase 2) — a stronger model scores live
    # feedback for quality and writes one ai_evaluations row, joined to the
    # operational log by trace_id. Online sampling only (cost control); the
    # judge runs post-commit, fire-and-forget, and never blocks the learner.
    AI_EVAL_ENABLED: bool = True
    AI_EVAL_SAMPLE_RATE: float = 0.1
    AI_EVAL_JUDGE_MODEL: str = "gpt-4.1"
    # `AI_EVAL_JUDGE_REASONING_EFFORT` is INERT on the non-reasoning `gpt-4.1`
    # judge (the client only sends it to reasoning models); kept so the judge can
    # be swapped back to a reasoning model from .env alone.
    AI_EVAL_JUDGE_REASONING_EFFORT: str = "high"
    # Generous post-commit/fire-and-forget timeout — the judge never blocks the
    # learner, so headroom only ever costs a dropped ai_evaluations row.
    AI_EVAL_TIMEOUT_S: float = 60.0
    # Mentor-note (RAG) judging sample rate (Part B Phase 3). Notes are produced
    # once per session completion — far rarer than per-activity feedback — and
    # RAG faithfulness is the highest-value bug-catcher, so judge every one.
    AI_EVAL_MENTOR_SAMPLE_RATE: float = 1.0

    # AI / TTS (text-to-speech)
    # `gpt-4o-mini-tts` is the newest + cheapest TTS model from OpenAI.
    # It uniquely supports the `instructions` parameter (e.g. "speak slowly,
    # sound encouraging") which is gold for a tutor app.
    # Voices for this model: alloy, ash, ballad, coral, echo, fable,
    # onyx, nova, sage, shimmer, verse.
    OPENAI_TTS_MODEL: str = "gpt-4o-mini-tts"
    OPENAI_TTS_VOICE: str = "alloy"
    # Where synthesized audio files are cached on disk. Path is RELATIVE
    # to the backend/ directory so it works regardless of where uvicorn
    # is launched from. Override per-environment via env var.
    TTS_CACHE_DIR: str = "app/ai/tts/_cache"
    # Public URL prefix the audio files are served under by FastAPI's
    # StaticFiles mount. Frontend uses these URLs in <audio src=...>.
    TTS_PUBLIC_URL_PREFIX: str = "/audio"

    # AI / STT (speech-to-text)
    # We use whisper-1 because it's the ONLY OpenAI model that supports
    # word-level timestamps (needed for fluency analysis on speak_*
    # tasks). gpt-4o-mini-transcribe is newer + cheaper but only returns
    # plain text. Sticking with whisper-1 keeps one model for all STT.
    OPENAI_STT_MODEL: str = "whisper-1"
    # Where transcript JSON sidecars are cached on disk. Different
    # directory from TTS so retention/cleanup policies stay independent
    # (transcripts may have privacy implications audio doesn't).
    STT_CACHE_DIR: str = "app/ai/stt/_cache"
    # Where learner-uploaded speaking clips live. These are not mounted as
    # public StaticFiles; they are served through an owner-checked route.
    LEARNER_AUDIO_DIR: str = "app/ai/stt/_learner_audio"

    # Deepgram — real-time streaming STT for A2Z challenge
    # Get a key at console.deepgram.com → API Keys → Create Key
    DEEPGRAM_API_KEY: str = ""

    # AI / Pronunciation (Azure Speech Pronunciation Assessment)
    # Optional at startup so Phase 4 code doesn't break environments that
    # haven't created an Azure Speech resource yet. The pronunciation route
    # fails fast with a clear error if these remain unset at call time.
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = ""
    # Where pronunciation-score JSON sidecars are cached on disk.
    PRONUNCIATION_CACHE_DIR: str = "app/ai/pronunciation/_cache"

    # AI / Image Generation (OpenAI)
    # `gpt-image-2` is the current OpenAI flagship image-generation
    # model. We keep output as PNG because the API returns base64 bytes
    # and PNG is the simplest format to serve/debug locally.
    OPENAI_IMAGE_MODEL: str = "gpt-image-2"
    OPENAI_IMAGE_QUALITY: str = "medium"
    OPENAI_IMAGE_OUTPUT_FORMAT: str = "png"
    IMAGEGEN_CACHE_DIR: str = "app/ai/imagegen/_cache"
    IMAGEGEN_PUBLIC_URL_PREFIX: str = "/images"

    # Blog cover images. Stored on disk like the AI media blobs and served
    # publicly via a StaticFiles mount (set up in app/main.py). Path is
    # RELATIVE to backend/ so it works regardless of where uvicorn launches.
    BLOG_MEDIA_CACHE_DIR: str = "app/modules/blog/_media"
    BLOG_MEDIA_PUBLIC_URL_PREFIX: str = "/blog-media"

    # Blob storage backend — local disk for development, S3/CloudFront for the
    # frozen AWS recovery path, or managed-identity Azure Blob storage for the
    # zero-cost topology. Selected by `build_blob_storage()` in
    # app/ai/storage/__init__.py; callers never change.
    STORAGE_BACKEND: Literal["local", "s3", "azure"] = "local"
    # S3 bucket + region for PUBLIC generated media (required when
    # STORAGE_BACKEND=s3). Credentials come from the ambient AWS env (ECS task
    # role in prod).
    MEDIA_S3_BUCKET: str = ""
    MEDIA_S3_REGION: str = "us-east-1"
    # Separate PRIVATE bucket for learner audio — never fronted by CloudFront,
    # only reachable through the owner-checked /responses/audio route. Falls
    # back to MEDIA_S3_BUCKET when empty (single-bucket setups).
    MEDIA_PRIVATE_S3_BUCKET: str = ""
    # CloudFront base URL for PUBLIC media (TTS audio, images, blog covers),
    # e.g. "https://media.lingosai.com". Private learner audio never uses this.
    MEDIA_CDN_URL: str = ""

    # Azure Blob adapter. Public media is intentionally separated from private
    # learner/internal data at the account boundary. Runtime authentication uses
    # DefaultAzureCredential (managed identity in Azure), never account keys.
    AZURE_BLOB_PUBLIC_ACCOUNT_URL: str = ""
    AZURE_BLOB_PRIVATE_ACCOUNT_URL: str = ""
    AZURE_BLOB_PUBLIC_CONTAINER: str = "public-media"
    AZURE_BLOB_PRIVATE_CONTAINER: str = "learner-media"
    AZURE_BLOB_INTERNAL_CONTAINER: str = "internal-media"
    # These declarations mirror the provisioned Azure container access levels
    # and make an unsafe production deployment fail at application startup.
    # "blob" permits direct anonymous reads but not container listing.
    AZURE_BLOB_PUBLIC_CONTAINER_ACCESS: Literal["private", "blob", "container"] = (
        "private"
    )
    AZURE_BLOB_PRIVATE_CONTAINER_ACCESS: Literal["private", "blob", "container"] = (
        "private"
    )
    AZURE_BLOB_INTERNAL_CONTAINER_ACCESS: Literal["private", "blob", "container"] = (
        "private"
    )

    # Vector DB (Pinecone)
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "lingosai-responses"
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"
    PINECONE_FEEDBACK_NAMESPACE: str = "feedback_memory"

    # RAG / Embeddings
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = 1024
    # A normalized mistake must appear in at least this many of the learner's
    # past activities to count as a "recurring pattern" in the Coach's Note.
    RAG_RECURRENCE_MIN_COUNT: int = 2
    # Phase 2: make per-activity feedback memory-aware (advisory only, never
    # changes scoring). Off by default — keeps current behavior unchanged.
    RAG_PER_ACTIVITY_FEEDBACK: bool = False
    # Kept short so RAG retrieval fails fast and degrades gracefully: when a
    # vector call is slow, retrieve_context_for_feedback drops the Pinecone
    # context and the Coach's Note is still generated from Postgres-only data.
    OPENAI_EMBEDDING_TIMEOUT_S: float = 8.0
    PINECONE_OPERATION_TIMEOUT_S: float = 8.0
    # Whole-operation ceiling for the Coach's Note. The completion path streams
    # the scorecard immediately, shows a "generating…" placeholder, then awaits
    # ensure_mentor_note up to this long before showing a fallback. It must
    # comfortably cover embedding + Pinecone retrieval + the LLM generation.
    RAG_MENTOR_NOTE_TIMEOUT_S: float = 30.0
    # Cap on the (flagged) per-activity memory retrieval so enabling
    # RAG_PER_ACTIVITY_FEEDBACK can never add tens of seconds to a submit.
    RAG_PER_ACTIVITY_TIMEOUT_S: float = 5.0

    # Feedback generation budget. The default LLM client retries 60s × 3 ≈ 180s,
    # which blows past the frontend's ceiling and strands the learner under an
    # empty scorecard. Feedback runs on a DEDICATED client capped at
    # OPENAI_FEEDBACK_TIMEOUT_S × (OPENAI_FEEDBACK_MAX_RETRIES + 1), and the
    # service wraps every feedback call in asyncio.wait_for(FEEDBACK_TIMEOUT_S)
    # so a slow/failed generation falls back to a deterministic card instead of
    # rolling back the graded attempt. Keep FEEDBACK_TIMEOUT_S comfortably below
    # the frontend loading ceiling (90s).
    OPENAI_FEEDBACK_TIMEOUT_S: float = 20.0
    OPENAI_FEEDBACK_MAX_RETRIES: int = 1
    FEEDBACK_TIMEOUT_S: float = 25.0

    # Find and read .env file
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Allowed CORS origins as a clean list (empty entries dropped)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _guard_production(self) -> "Settings":
        """Fail-fast safety net for production.

        The app already crashes on missing required vars; this extends that
        philosophy to "unsafe-in-prod" combinations so a single forgotten env
        override on the server can never silently ship a dev-only setting
        (OTP bypass, SQL query logging, localhost CORS, insecure cookies).
        Only enforced when ENVIRONMENT=production — dev and tests are untouched.
        """
        if self.environment != "production":
            return self

        violations: list[str] = []
        if self.debug:
            violations.append("DEBUG must be false")
        if self.sql_echo:
            violations.append("SQL_ECHO must be false")
        if self.DEV_OTP_BYPASS:
            violations.append("DEV_OTP_BYPASS must be false (magic OTP 123456)")
        if not self.OTP_HASHING_SECRET:
            violations.append(
                "OTP_HASHING_SECRET must be set (no jwt_secret fallback in prod)"
            )
        if not self.AUTH_COOKIE_SECURE:
            violations.append("AUTH_COOKIE_SECURE must be true behind https")
        if not self.cors_origins_list:
            violations.append("CORS_ORIGINS must be set")
        else:
            unsafe_origins = [
                origin
                for origin in self.cors_origins_list
                if not _is_safe_production_origin(origin)
            ]
            if unsafe_origins:
                violations.append(
                    "CORS_ORIGINS must contain only explicit HTTPS origins "
                    f"without credentials, paths, wildcards, or local/private hosts: "
                    f"{unsafe_origins}"
                )
        if not _is_safe_production_origin(self.frontend_url):
            violations.append("FRONTEND_URL must be an explicit public HTTPS origin")
        elif self.frontend_url not in self.cors_origins_list:
            violations.append("FRONTEND_URL must also be listed in CORS_ORIGINS")

        if self.DB_POOL_SIZE + self.DB_MAX_OVERFLOW > 5:
            violations.append(
                "DB_POOL_SIZE + DB_MAX_OVERFLOW must not exceed 5 production "
                "application connections"
            )

        if self.AI_RATE_LIMIT_BACKEND == "memory" and self.WEB_CONCURRENCY != 1:
            violations.append(
                "WEB_CONCURRENCY must be 1 when AI_RATE_LIMIT_BACKEND=memory"
            )
        if self.AI_RATE_LIMIT_BACKEND == "redis" and not _is_valid_redis_url(
            self.redis_url
        ):
            violations.append("REDIS_URL must be set when AI_RATE_LIMIT_BACKEND=redis")

        if self.STORAGE_BACKEND == "local":
            violations.append("STORAGE_BACKEND=local is not supported in production")
        elif self.STORAGE_BACKEND == "s3":
            if not self.MEDIA_S3_BUCKET:
                violations.append("MEDIA_S3_BUCKET must be set when STORAGE_BACKEND=s3")
            if not self.MEDIA_CDN_URL:
                violations.append("MEDIA_CDN_URL must be set when STORAGE_BACKEND=s3")
        elif self.STORAGE_BACKEND == "azure":
            violations.extend(self._azure_blob_production_violations())

        if violations:
            raise ValueError(
                "Unsafe production configuration — refusing to boot:\n  - "
                + "\n  - ".join(violations)
            )
        return self

    def _azure_blob_production_violations(self) -> list[str]:
        """Return fail-closed Azure endpoint, container, and privacy errors."""
        violations: list[str] = []
        account_urls = {
            "AZURE_BLOB_PUBLIC_ACCOUNT_URL": self.AZURE_BLOB_PUBLIC_ACCOUNT_URL,
            "AZURE_BLOB_PRIVATE_ACCOUNT_URL": self.AZURE_BLOB_PRIVATE_ACCOUNT_URL,
        }
        for field_name, account_url in account_urls.items():
            if not _is_safe_azure_blob_account_url(account_url):
                violations.append(
                    f"{field_name} must be a credential-free HTTPS Azure Blob "
                    "account endpoint"
                )
        public_account_host = urlsplit(self.AZURE_BLOB_PUBLIC_ACCOUNT_URL).hostname
        private_account_host = urlsplit(self.AZURE_BLOB_PRIVATE_ACCOUNT_URL).hostname
        if public_account_host and public_account_host == private_account_host:
            violations.append(
                "Azure public and private data must use separate storage accounts"
            )

        containers = {
            "AZURE_BLOB_PUBLIC_CONTAINER": self.AZURE_BLOB_PUBLIC_CONTAINER,
            "AZURE_BLOB_PRIVATE_CONTAINER": self.AZURE_BLOB_PRIVATE_CONTAINER,
            "AZURE_BLOB_INTERNAL_CONTAINER": self.AZURE_BLOB_INTERNAL_CONTAINER,
        }
        for field_name, container in containers.items():
            if not _is_valid_azure_container_name(container):
                violations.append(
                    f"{field_name} must be a valid lowercase Azure container name"
                )
        if len(set(containers.values())) != len(containers):
            violations.append(
                "Azure public/private/internal containers must be distinct"
            )

        if self.AZURE_BLOB_PUBLIC_CONTAINER_ACCESS != "blob":
            violations.append(
                "AZURE_BLOB_PUBLIC_CONTAINER_ACCESS must be blob "
                "(direct reads without container listing)"
            )
        if self.AZURE_BLOB_PRIVATE_CONTAINER_ACCESS != "private":
            violations.append("AZURE_BLOB_PRIVATE_CONTAINER_ACCESS must be private")
        if self.AZURE_BLOB_INTERNAL_CONTAINER_ACCESS != "private":
            violations.append("AZURE_BLOB_INTERNAL_CONTAINER_ACCESS must be private")
        return violations


_AZURE_CONTAINER_NAME = re.compile(
    r"^(?=.{3,63}$)[a-z0-9](?:[a-z0-9]|-(?!-))*[a-z0-9]$"
)
_AZURE_BLOB_ACCOUNT_HOST = re.compile(r"^[a-z0-9]{3,24}\.blob\.core\.windows\.net$")


def _is_safe_production_origin(origin: str) -> bool:
    """Accept an exact public HTTPS origin, never a URL pattern or local host."""
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return False
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or "*" in origin
        or (port is not None and port != 443)
    ):
        return False
    normalized_host = hostname.rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        return "." in normalized_host
    return address.is_global


def _is_safe_azure_blob_account_url(account_url: str) -> bool:
    """Accept only a bare public-cloud Azure Blob account endpoint."""
    try:
        parsed = urlsplit(account_url)
        port = parsed.port
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower()
    return bool(
        parsed.scheme == "https"
        and _AZURE_BLOB_ACCOUNT_HOST.fullmatch(hostname)
        and parsed.username is None
        and parsed.password is None
        and port is None
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment
    )


def _is_valid_redis_url(redis_url: str | None) -> bool:
    """Require an addressable Redis endpoint when shared buckets are selected."""
    if not redis_url or not redis_url.strip():
        return False
    try:
        parsed = urlsplit(redis_url)
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme in {"redis", "rediss"}
        and parsed.hostname
        and port is not None
        and not parsed.fragment
    )


def _is_valid_azure_container_name(container: str) -> bool:
    """Apply Azure's lowercase DNS-style container naming constraints."""
    return bool(_AZURE_CONTAINER_NAME.fullmatch(container))


# Single shared instance. Fields are populated from the environment by
# pydantic-settings, which mypy can't see — hence the call-arg suppression.
settings = Settings()  # type: ignore[call-arg]
