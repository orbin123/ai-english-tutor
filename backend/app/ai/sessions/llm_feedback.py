"""LLM-driven `FeedbackGenerator` implementation for the sessions flow.

Produces the spec §14 shape: summary, did_well[], mistakes[], next_tip,
sub_skill_breakdown. On LLM failure, returns a minimal stub-flavour
feedback so the user still sees something — and the activity lifecycle
proceeds.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.ai.llm.exceptions import LLMError
from app.ai.llm.interface import ILLMClient
from app.ai.sessions.prompts import (
    build_feedback_user_prompt,
    compute_error_correction_wrong_items,
    compute_error_spotting_wrong_items,
    compute_listen_cloze_wrong_items,
    compute_mcq_wrong_items,
    compute_wrong_items,
    feedback_system_prompt,
)
from app.modules.sessions.widget_mapping import normalize_widget_key
from app.modules.sessions.evaluator import EvaluationResult
from app.modules.sessions.feedback_generator import (
    FeedbackResult,
    MistakeOut,
)
from app.scoring import ArchetypeSpec


logger = logging.getLogger(__name__)

# Widget types whose correctness can be determined deterministically from
# per-item correct_answer string fields — the LLM must not re-derive which
# items were wrong. MCQ and others use different fields (correct_index) so
# they are not included here.
_DETERMINISTIC_WIDGET_KEYS = {"fill_in_blanks", "error_spotting"}
_DETERMINISTIC_SCORE_ARCHETYPES = frozenset(
    {
        "LISTEN_MCQ",
        "LISTEN_CLOZE",
        "LISTEN_INFER",
        "LISTEN_TONE",
        "READ_CLOZE",
        "READ_ERROR_SPOT",
        "READ_COMP_MCQ",
        "READ_CONTEXT_MCQ",
        "READ_WORD_MATCH",
        "READ_TONE_ID",
    }
)
_MCQ_INNER_WIDGET_KEYS = {"listen_and_respond"}
# error_correction is deliberately NOT here: it carries a per-item answer key
# (sample_answer), so its mistakes are computed deterministically rather than
# re-derived by the LLM (which over-counted them — the "3 vs 2" bug).
_OPEN_ENDED_WIDGET_KEYS = {
    "open_text",
    "timed_text",
    "structured_essay",
    "speak_and_record",
    "storyboard",
}
_FREQUENCY_ADVERBS = {
    "always",
    "usually",
    "often",
    "sometimes",
    "never",
    "rarely",
    "seldom",
}


class MistakeOutSchema(BaseModel):
    issue: str
    user_wrote: str | None = None
    correction: str | None = None
    rule: str | None = None
    sub_skills_affected: list[str] = Field(default_factory=list)


class FeedbackOutput(BaseModel):
    """LLM-side schema enforced via structured output."""

    score: int = Field(ge=0, le=10)
    summary: str
    did_well: list[str] = Field(default_factory=list)
    mistakes: list[MistakeOutSchema] = Field(default_factory=list)
    next_tip: str | None = None


class LLMFeedbackGenerator:
    """Production `FeedbackGenerator` — invokes the LLM, validates output,
    returns `FeedbackResult`."""

    def __init__(self, llm: ILLMClient, *, temperature: float | None = 0.4) -> None:
        self.llm = llm
        self.temperature = temperature

    async def generate(
        self,
        *,
        archetype: ArchetypeSpec,
        evaluation: EvaluationResult,
        user_response: dict | None,
        task_content: dict | None = None,
        feedback_overrides: dict | None = None,
        learner_history: str | None = None,
    ) -> FeedbackResult:
        rounded = int(round(evaluation.raw_score))
        if user_response is None:
            return FeedbackResult(
                score=0,
                summary=f"No response submitted for {archetype.name}.",
                did_well=(),
                mistakes=(),
                next_tip="Try submitting an answer next time, even a short one.",
                sub_skill_breakdown={skill: 0 for skill in archetype.weight_map},
            )

        widget_key = normalize_widget_key(archetype.ui_widget)
        confirmed_mistakes: list[dict] | None = None
        use_mcq_mistake_normalization = False
        if widget_key == "error_spotting" and task_content and user_response:
            confirmed_mistakes = compute_error_spotting_wrong_items(
                task_content,
                user_response,
            )
        elif (
            widget_key in _DETERMINISTIC_WIDGET_KEYS and task_content and user_response
        ):
            confirmed_mistakes = compute_wrong_items(task_content, user_response)
        elif widget_key == "error_correction" and task_content and user_response:
            confirmed_mistakes = compute_error_correction_wrong_items(
                task_content,
                user_response,
            )
        elif widget_key == "mcq" and task_content and user_response:
            confirmed_mistakes = compute_mcq_wrong_items(task_content, user_response)
            use_mcq_mistake_normalization = True
        elif widget_key in _MCQ_INNER_WIDGET_KEYS and task_content and user_response:
            if task_content.get("inner_widget") == "fill_in_blanks":
                confirmed_mistakes = compute_listen_cloze_wrong_items(
                    task_content,
                    user_response,
                )
            else:
                confirmed_mistakes = compute_mcq_wrong_items(
                    task_content, user_response
                )
                use_mcq_mistake_normalization = True

        try:
            output = await self.llm.generate_structured(
                system_prompt=feedback_system_prompt(),
                user_prompt=build_feedback_user_prompt(
                    archetype=archetype,
                    raw_score=evaluation.raw_score,
                    rubric_scores=evaluation.rubric_scores,
                    evaluator_notes=evaluation.evaluator_notes,
                    task_content=task_content or {},
                    user_response=user_response,
                    feedback_overrides=feedback_overrides,
                    confirmed_mistakes=confirmed_mistakes,
                    learner_history=learner_history,
                ),
                output_model=FeedbackOutput,
                temperature=self.temperature,
            )
        except LLMError as exc:
            logger.warning(
                "LLM feedback failed for archetype=%s: %s",
                archetype.archetype_id,
                exc,
            )
            return FeedbackResult(
                score=rounded,
                summary=(
                    f"Feedback temporarily unavailable. Score: {rounded}/10. "
                    "We'll generate detailed feedback once the service is back."
                ),
                did_well=(),
                mistakes=(),
                next_tip=None,
                sub_skill_breakdown={skill: rounded for skill in archetype.weight_map},
                fallback=True,
            )

        mistakes = output.mistakes
        if use_mcq_mistake_normalization:
            mistakes = _normalize_mcq_mistakes(
                confirmed_mistakes or [],
                task_content or {},
            )
        elif widget_key == "error_spotting" and confirmed_mistakes is not None:
            mistakes = _normalize_error_spotting_mistakes(confirmed_mistakes)
        elif widget_key == "error_correction" and confirmed_mistakes is not None:
            mistakes = _normalize_error_correction_mistakes(confirmed_mistakes)
        elif widget_key in _OPEN_ENDED_WIDGET_KEYS:
            mistakes = _filter_open_ended_mistakes(mistakes)

        # Cap mistakes per spec rule ("max 3 per activity"). Defensive in
        # case the LLM ignores the instruction.
        mistakes_capped = tuple(
            MistakeOut(
                issue=m.issue,
                user_wrote=m.user_wrote,
                correction=m.correction,
                rule=m.rule,
                sub_skills_affected=tuple(m.sub_skills_affected),
            )
            for m in mistakes[:3]
        )
        if archetype.archetype_id in _DETERMINISTIC_SCORE_ARCHETYPES:
            score = int(round(evaluation.raw_score))
            breakdown = {skill: score for skill in archetype.weight_map}
        else:
            score = int(output.score)
            breakdown = {skill: int(output.score) for skill in archetype.weight_map}
        return FeedbackResult(
            score=score,
            summary=output.summary,
            did_well=tuple(output.did_well),
            mistakes=mistakes_capped,
            next_tip=output.next_tip,
            sub_skill_breakdown=breakdown,
        )


def _normalize_mcq_mistakes(
    confirmed_mistakes: list[dict],
    task_content: dict,
) -> list[MistakeOutSchema]:
    """Map deterministic MCQ wrong-answer rows to learner-facing mistake labels."""
    prompt_by_id = {
        str(item.get("item_id") or ""): str(item.get("prompt") or "").strip()
        for item in (task_content.get("items") or [])
        if isinstance(item, dict)
    }
    mistakes: list[MistakeOutSchema] = []
    for item in confirmed_mistakes:
        item_id = str(item.get("item_id") or "")
        prompt = str(item.get("prompt") or prompt_by_id.get(item_id) or item_id).strip()
        user_wrote = str(
            item.get("user_wrote") or item.get("user_selected") or ""
        ).strip()
        correction = str(
            item.get("correction") or item.get("correct_answer") or ""
        ).strip()
        rule = str(item.get("explanation") or item.get("rule") or "").strip()
        if not user_wrote or not correction:
            continue
        issue = f"'{prompt}'" if prompt else "Incorrect answer"
        mistakes.append(
            MistakeOutSchema(
                issue=issue,
                user_wrote=user_wrote,
                correction=correction,
                rule=rule or None,
            )
        )
    return mistakes


def _normalize_error_spotting_mistakes(
    confirmed_mistakes: list[dict],
) -> list[MistakeOutSchema]:
    """Turn token-level error spotting misses into learner-facing feedback."""
    mistakes: list[MistakeOutSchema] = []
    for item in confirmed_mistakes:
        error_type = str(item.get("error_type") or "")
        user_wrote = str(
            item.get("user_wrote") or item.get("incorrect_phrase") or ""
        ).strip()
        correction = str(item.get("correct_answer") or "").strip()
        rule = str(item.get("rule") or item.get("explanation") or "").strip()

        if error_type == "false_positive":
            token = user_wrote or str(item.get("item_id") or "This word")
            mistakes.append(
                MistakeOutSchema(
                    issue=f'"{token}" was not an error.',
                    user_wrote=token,
                    correction="Do not flag this word",
                    rule=rule
                    or "Only flag words that contain an actual grammar mistake.",
                )
            )
            continue

        if not user_wrote or not correction:
            continue
        mistakes.append(
            MistakeOutSchema(
                issue=f'"{user_wrote}" should be "{correction}".',
                user_wrote=user_wrote,
                correction=correction,
                rule=rule,
            )
        )
    return mistakes


def _normalize_error_correction_mistakes(
    confirmed_mistakes: list[dict],
) -> list[MistakeOutSchema]:
    """Turn deterministic error-correction misses into learner-facing feedback.

    The confirmed set is the ground truth (learner answer != sample_answer), so
    the rendered mistakes are EXACTLY these — the LLM can no longer invent a
    third one. An empty list (all items correct) yields no mistakes.
    """
    mistakes: list[MistakeOutSchema] = []
    for item in confirmed_mistakes:
        user_wrote = str(item.get("user_wrote") or "").strip()
        correction = str(item.get("correct_answer") or "").strip()
        rule = str(item.get("explanation") or item.get("rule") or "").strip()
        if not user_wrote or not correction:
            continue
        mistakes.append(
            MistakeOutSchema(
                issue=f'"{user_wrote}" should be "{correction}".',
                user_wrote=user_wrote,
                correction=correction,
                rule=rule or None,
            )
        )
    return mistakes


def _filter_open_ended_mistakes(
    mistakes: list[MistakeOutSchema],
) -> list[MistakeOutSchema]:
    """Remove false-positive open-ended feedback items.

    Open writing/speaking has no answer key, so the LLM can occasionally
    produce a mistake entry for already-correct wording. We only keep items
    that include an actual changed improvement, and reject common subject-verb
    agreement hallucinations where the proposed correction makes the sentence
    worse.
    """
    filtered: list[MistakeOutSchema] = []
    for mistake in mistakes:
        user_wrote = mistake.user_wrote or ""
        correction = mistake.correction or ""
        if not user_wrote.strip() or not correction.strip():
            continue
        if _normalize_feedback_text(user_wrote) == _normalize_feedback_text(correction):
            continue
        if _is_false_positive_simple_present_feedback(mistake):
            continue
        filtered.append(mistake)
    return filtered


def _normalize_feedback_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).rstrip(".!?")


def _is_false_positive_simple_present_feedback(mistake: MistakeOutSchema) -> bool:
    user_wrote = _normalize_feedback_text(mistake.user_wrote or "")
    correction = _normalize_feedback_text(mistake.correction or "")
    reason = f"{mistake.issue} {mistake.rule or ''}".lower()
    if not user_wrote or not correction:
        return False

    if "missing -s" in reason or "he or she" in reason or "subject-verb" in reason:
        user_subject, user_verb = _simple_present_subject_and_verb(user_wrote)
        correction_subject, correction_verb = _simple_present_subject_and_verb(
            correction
        )
        if (
            user_subject in {"he", "she"}
            and user_verb
            and _looks_third_person_singular(user_verb)
        ):
            if (
                correction_subject == user_subject
                and correction_verb
                and not _looks_third_person_singular(correction_verb)
            ):
                return True

    if "base verb" in reason or "with i" in reason:
        user_subject, user_verb = _simple_present_subject_and_verb(user_wrote)
        correction_subject, correction_verb = _simple_present_subject_and_verb(
            correction
        )
        if (
            user_subject == "i"
            and user_verb
            and not _looks_third_person_singular(user_verb)
        ):
            if correction_subject == "i" and correction_verb == user_verb:
                return True

    return False


def _simple_present_subject_and_verb(sentence: str) -> tuple[str | None, str | None]:
    words = re.findall(r"[a-z']+", sentence.lower())
    if not words:
        return None, None
    subject = words[0]
    if subject not in {"i", "he", "she"}:
        return None, None
    verb_index = 1
    if verb_index < len(words) and words[verb_index] in _FREQUENCY_ADVERBS:
        verb_index += 1
    if verb_index >= len(words):
        return subject, None
    return subject, words[verb_index]


def _looks_third_person_singular(verb: str) -> bool:
    if verb in {"is", "has", "does", "goes"}:
        return True
    return len(verb) > 2 and verb.endswith("s") and not verb.endswith("ss")
