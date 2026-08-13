"""AI debug routes.

Lightweight endpoints for verifying the AI layer works end-to-end.
Mounted under /debug/ai.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.ai.imagegen import (
    AspectRatio,
    ImageGenError,
    ImageGenValidationError,
    ImageResult,
    get_default_imagegen_service,
)
from app.ai.llm import get_default_llm_client
from app.ai.pronunciation import (
    PronunciationError,
    PronunciationResult,
    PronunciationValidationError,
    get_default_pronunciation_service,
)
from app.ai.stt import (
    STTError,
    STTPayloadTooLarge,
    STTValidationError,
    TranscriptionResult,
    get_default_stt_service,
)
from app.ai.tts import (
    SynthesisResult,
    TTSError,
    TTSValidationError,
    get_default_tts_service,
)
from app.core.audio_uploads import (
    enforce_audio_duration,
    enforce_wav_duration,
    read_audio_upload,
)
from app.core.config import settings


def require_non_production_debug() -> None:
    """Return 404 in production even if the router is mounted accidentally."""
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not found.")


router = APIRouter(
    prefix="/debug/ai",
    tags=["debug"],
    dependencies=[Depends(require_non_production_debug)],
)


# ---------------------------------------------------------------------------
# LLM ping
# ---------------------------------------------------------------------------
@router.get("/ping")
async def ping_llm() -> dict[str, str]:
    """Smoke test the LLM client.

    Sends one prompt to OpenAI and returns the reply. Useful for:
      - confirming OPENAI_API_KEY is set + valid
      - confirming LangSmith trace shows up under project
        'ai-english-coach'
      - sanity-checking the unified client after a deploy

    Development-only. The router is absent in production and also carries a
    fail-closed production dependency so this call cannot spend provider quota.
    """
    client = get_default_llm_client()
    reply = await client.generate_text(
        system_prompt="You are a terse echo bot.",
        user_prompt="Say 'LangSmith trace working' in 5 words exactly.",
    )
    return {"reply": reply}


# ---------------------------------------------------------------------------
# TTS synthesize (debug)
# ---------------------------------------------------------------------------
class TTSRequest(BaseModel):
    """Body for /debug/ai/tts/synthesize."""

    text: str = Field(min_length=1, max_length=4000)
    voice: str | None = Field(
        default=None,
        description=(
            "Optional voice override. gpt-4o-mini-tts supports: "
            "alloy, ash, ballad, coral, echo, fable, onyx, nova, sage, "
            "shimmer, verse."
        ),
    )
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    style_instructions: str | None = Field(
        default=None,
        description=(
            "Free-form style guidance, e.g. 'speak slowly and warmly'. "
            "Only used by gpt-4o-mini-tts."
        ),
    )


@router.post("/tts/synthesize")
async def tts_synthesize(req: TTSRequest) -> SynthesisResult:
    """Synthesize one short audio clip and return the URL.

    Useful for:
      - verifying OpenAI TTS is wired up
      - watching cache_hit flip from False -> True on the second call
      - copying the returned audio_url into a browser to hear the result

    First call:  OpenAI is hit, audio written to disk, cache_hit=False.
    Repeat call (same text+voice+speed+instructions): cache_hit=True,
    no provider charge.

    Errors:
      400 - invalid text / voice / speed
      502 - provider failure (timeout, rate limit, etc.)
    """
    service = get_default_tts_service()
    try:
        result = await service.synthesize(
            text=req.text,
            voice=req.voice,
            speed=req.speed,
            style_instructions=req.style_instructions,
        )
    except TTSValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TTSError as exc:
        # 502: provider failed. We surface the message — debug-only,
        # safe to leak provider error text here.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result


# ---------------------------------------------------------------------------
# Image generation (debug)
# ---------------------------------------------------------------------------
class ImageGenerationRequest(BaseModel):
    """Body for /debug/ai/image/generate."""

    prompt: str = Field(min_length=1, max_length=4000)
    aspect_ratio: AspectRatio = Field(
        default="square",
        description="square, landscape, or portrait",
    )
    style: str | None = Field(
        default=None,
        description=(
            "Optional free-form style hint, e.g. 'storybook watercolor' "
            "or 'clean flat illustration'."
        ),
    )


@router.post("/image/generate")
async def image_generate(req: ImageGenerationRequest) -> ImageResult:
    """Generate one image from a prompt and return its cached public URL.

    Useful for:
      - verifying OpenAI image generation is wired up
      - checking cache_hit flips from False -> True on the same prompt
      - confirming static image serving works under the configured URL

    Errors:
      400 - invalid prompt / aspect ratio
      502 - provider failure (auth, timeout, rate limit, etc.)
    """
    service = get_default_imagegen_service()
    try:
        result = await service.generate(
            prompt=req.prompt,
            aspect_ratio=req.aspect_ratio,
            style=req.style,
        )
    except ImageGenValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImageGenError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result


# ---------------------------------------------------------------------------
# Pronunciation score (debug)
# ---------------------------------------------------------------------------
@router.post("/pronunciation/score")
async def pronunciation_score(
    audio: UploadFile = File(
        ...,
        description=(
            "Short pronunciation clip. WAV is the most reliable format for "
            "local verification; compressed formats require GStreamer."
        ),
    ),
    reference_text: str = Form(..., min_length=1),
    language: str = Form(default="en-US"),
) -> PronunciationResult:
    """Score one short scripted audio clip against the expected text.

    Useful for:
      - verifying Azure Speech Pronunciation Assessment is wired up
      - checking phoneme-level scoring end-to-end before task integration
      - confirming cache hits on repeated uploads of the same clip

    Important:
      - This route uses Azure Speech `recognize_once`, which Microsoft
        documents as suitable for a single utterance of about 30 seconds.
      - WAV works without extra local dependencies. Compressed formats
        such as mp3/ogg/flac/mp4 need GStreamer installed on the server.

    Sample curl:
      curl -F "audio=@read-aloud.wav" \\
           -F "reference_text=The quick brown fox jumps over the lazy dog." \\
           http://localhost:8000/debug/ai/pronunciation/score

    Errors:
      400 - invalid audio / unsupported format / missing reference text
      502 - provider failure (auth, timeout, rate limit, SDK error)
    """
    audio_bytes = await read_audio_upload(audio)
    filename = audio.filename or "recording.wav"
    enforce_wav_duration(
        audio_bytes,
        filename=filename,
        content_type=audio.content_type,
    )

    service = get_default_pronunciation_service()
    try:
        result = await service.score(
            audio_bytes=audio_bytes,
            filename=filename,
            reference_text=reference_text,
            language=language,
        )
    except PronunciationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PronunciationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result


# ---------------------------------------------------------------------------
# STT transcribe (debug)
# ---------------------------------------------------------------------------
@router.post("/stt/transcribe")
async def stt_transcribe(
    audio: UploadFile = File(
        ..., description="Audio recording (webm, mp3, wav, ogg, m4a, flac)"
    ),
    language: str = Form(default="en"),
    with_timestamps: bool = Form(default=False),
) -> TranscriptionResult:
    """Transcribe one audio upload via Whisper.

    Useful for:
      - verifying OpenAI STT is wired up
      - testing word-level timestamps for fluency analysis later
      - watching the cache hit on identical re-uploads (look for
        `stt_cache_hit` in server logs)

    Sample curl:
      curl -F "audio=@hello.mp3" \\
           -F "with_timestamps=true" \\
           http://localhost:8000/debug/ai/stt/transcribe

    Errors:
      400 - empty / malformed audio
      413 - audio over 5 MiB or 45 seconds
      502 - provider failure (timeout, rate limit, etc.)
    """
    audio_bytes = await read_audio_upload(audio)
    filename = audio.filename or "recording.webm"

    service = get_default_stt_service()
    try:
        result = await service.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
            language=language,
            with_timestamps=with_timestamps,
        )
        enforce_audio_duration(result.get("duration_seconds"))
    except STTPayloadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except STTValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except STTError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result
