"""
Grammar & Sentence Construction — Task Templates.

Sub-Skill #1 of 7. Covers grammar accuracy, sentence formation,
and coherence/cohesion across all 4 core activities.

TEMPLATES IN THIS FILE
──────────────────────
Read    │ 1. Fill-in-blanks (tense/preposition/article focused)
        │ 2. Error spotting (find grammatical mistakes)
Write   │ 3. Sentence transformation (simple → complex)
        │ 4. Active ↔ Passive voice conversion
        │ 5. Error correction (rewrite incorrect sentences)
Listen  │ 6. Detect grammar errors in audio
Speak   │ 7. Speak using a specific tense
        │ 8. Construct sentences from prompts (combiners)

Total: 8 Grammar templates.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.tasks.schemas.base import (
    Activity,
    GeneratedTaskBase,
    ScoringMethod,
    SubSkill,
    TaskTemplate,
)


# ═════════════════════════════════════════════════════════════════════
# LAYER 2 — PYDANTIC MODELS (validate LLM output for each template)
# ═════════════════════════════════════════════════════════════════════


# Shared label used across multiple templates ─ the grammar rule under test
GrammarRule = Literal[
    "past_simple",
    "past_continuous",
    "present_simple",
    "present_perfect",
    "past_perfect",
    "future_simple",
    "subject_verb_agreement",
    "preposition",
    "article",
    "conditional",
    "passive_voice",
    "active_voice",
    "modal_verb",
    "relative_clause",
    "conjunction",
]


# ─── Template 1: Fill-in-Blanks ───────────────────────────────────────


class BlankItem(BaseModel):
    blank_id: str = Field(..., description="e.g. 'b1', 'b2'")
    sentence_with_blank: str = Field(..., description="Sentence containing ___")
    correct_answer: str
    options: list[str] = Field(..., min_length=4, max_length=4)
    grammar_rule: GrammarRule
    explanation: str = Field(..., min_length=10, max_length=200)


class FillInBlanksTask(GeneratedTaskBase):
    passage_title: str
    passage: str = Field(..., min_length=80, max_length=500)
    blanks: list[BlankItem] = Field(..., min_length=5, max_length=10)
    total_blanks: int


# ─── Template 2: Error Spotting ───────────────────────────────────────


class ErrorItem(BaseModel):
    sentence_id: str
    sentence: str = Field(..., description="The sentence (may contain an error)")
    has_error: bool
    error_type: GrammarRule | None = None
    incorrect_phrase: str | None = None
    correction: str | None = None
    explanation: str | None = None


class ErrorSpottingTask(GeneratedTaskBase):
    instructions: str
    sentences: list[ErrorItem] = Field(..., min_length=5, max_length=10)
    total_with_errors: int


# ─── Template 3: Sentence Transformation ──────────────────────────────


class TransformItem(BaseModel):
    item_id: str
    original_sentence: str
    transformation_target: Literal[
        "make_complex", "make_compound", "add_relative_clause",
        "use_conditional", "combine_sentences",
    ]
    expected_pattern: str = Field(..., description="Grammar pattern user must apply")
    sample_correct_answer: str
    grading_criteria: list[str] = Field(..., min_length=2)


class SentenceTransformationTask(GeneratedTaskBase):
    instructions: str
    items: list[TransformItem] = Field(..., min_length=3, max_length=6)


# ─── Template 4: Active ↔ Passive ─────────────────────────────────────


class VoiceConversionItem(BaseModel):
    item_id: str
    original_sentence: str
    direction: Literal["active_to_passive", "passive_to_active"]
    correct_answer: str
    common_mistake: str | None = Field(
        None, description="Typical wrong answer learners give"
    )


class VoiceConversionTask(GeneratedTaskBase):
    instructions: str
    items: list[VoiceConversionItem] = Field(..., min_length=4, max_length=8)


# ─── Template 5: Error Correction ─────────────────────────────────────


class CorrectionItem(BaseModel):
    item_id: str
    incorrect_sentence: str
    correct_sentence: str
    error_type: GrammarRule
    explanation: str


class ErrorCorrectionTask(GeneratedTaskBase):
    instructions: str
    items: list[CorrectionItem] = Field(..., min_length=4, max_length=8)


# ─── Template 6: Listen — Detect Grammar Errors in Audio ──────────────


class AudioErrorItem(BaseModel):
    item_id: str
    audio_transcript: str = Field(..., description="What was actually spoken")
    has_error: bool
    error_type: GrammarRule | None = None
    correction: str | None = None


class ListenGrammarErrorTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled later by TTS pipeline; null until audio is generated"
    )
    items: list[AudioErrorItem] = Field(..., min_length=3, max_length=6)


# ─── Template 7: Speak — Use a Specific Tense ─────────────────────────


class SpeakWithTenseTask(GeneratedTaskBase):
    instructions: str
    target_tense: GrammarRule
    speaking_prompt: str = Field(
        ..., description="The topic/scenario the user must speak about"
    )
    minimum_duration_seconds: int = Field(default=60, ge=30, le=180)
    minimum_sentences: int = Field(default=4, ge=2, le=10)
    grading_criteria: list[str] = Field(..., min_length=3)
    sample_response: str = Field(..., description="A model answer for reference")


# ─── Template 8: Speak — Sentence Combiners ───────────────────────────


class CombinerItem(BaseModel):
    item_id: str
    fragment_1: str
    fragment_2: str
    expected_combination_type: Literal[
        "compound", "complex", "conditional", "relative_clause",
    ]
    sample_combined_sentence: str


class SpeakSentenceCombinersTask(GeneratedTaskBase):
    instructions: str
    items: list[CombinerItem] = Field(..., min_length=3, max_length=6)


# ═════════════════════════════════════════════════════════════════════
# LAYER 1 — TEMPLATE DEFINITIONS (what the system loads at startup)
# ═════════════════════════════════════════════════════════════════════


GRAMMAR_READ_FILL_BLANKS_V1 = TaskTemplate(
    template_id="grammar_read_fill_blanks_v1",
    sub_skill=SubSkill.GRAMMAR,
    activity=Activity.READ,
    task_type="fill_in_blanks",
    difficulty_range=(1, 10),
    estimated_time_minutes=5,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
You are an English teacher creating a grammar exercise for a learner.

LEARNER PROFILE
- Sub-level: {sub_level} (1=A1 beginner, 10=C2 expert)
- Weak grammar areas: {weak_areas}
- Topic of interest: {topic}

TASK
Create a fill-in-the-blanks passage following these rules:
1. Passage length: {min_words}–{max_words} words
2. Number of blanks: {blank_count}
3. Each blank tests a SPECIFIC grammar rule
4. Prioritize the learner's weak areas: {weak_areas}
5. Provide exactly 4 multiple-choice options per blank (1 correct + 3 plausible distractors)
6. Include a 1-sentence explanation for each correct answer
7. Use vocabulary appropriate to {vocab_level}

Return ONLY valid JSON matching the FillInBlanksTask schema. No prose, no markdown fences.
""",
    output_model_name="FillInBlanksTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct blank, normalized to 0-1",
        "passing_threshold": 0.7,
        "feedback_triggers": {
            "below_0.5": "explain every wrong answer in detail",
            "0.5_to_0.7": "explain only the wrong ones",
            "above_0.7": "brief reinforcement + 1 advanced tip",
        },
    },
    difficulty_modifiers={
        "beginner": {"min_words": 60, "max_words": 100, "blank_count": 5, "vocab_level": "basic"},
        "intermediate": {"min_words": 120, "max_words": 200, "blank_count": 7, "vocab_level": "intermediate"},
        "advanced": {"min_words": 200, "max_words": 350, "blank_count": 10, "vocab_level": "advanced"},
    },
)


GRAMMAR_READ_ERROR_SPOTTING_V1 = TaskTemplate(
    template_id="grammar_read_error_spotting_v1",
    sub_skill=SubSkill.GRAMMAR,
    activity=Activity.READ,
    task_type="error_spotting",
    difficulty_range=(3, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
You are an English teacher. Generate a set of sentences. Some contain a
grammatical error; others are correct. The learner must spot which ones
are wrong and identify the error.

LEARNER PROFILE
- Sub-level: {sub_level}
- Weak grammar areas: {weak_areas}
- Topic context: {topic}

TASK
Generate {sentence_count} sentences:
- About {error_count} should contain a grammar error
- The rest should be grammatically correct
- Errors should be subtle, not obvious
- Each error must be tagged with its type ({grammar_rules_in_play})
- For correct sentences, set has_error=false and leave error fields null

Return ONLY valid JSON matching the ErrorSpottingTask schema.
""",
    output_model_name="ErrorSpottingTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "0.5 for correctly flagging error + 0.5 for naming error_type",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "beginner": {"sentence_count": 5, "error_count": 3, "grammar_rules_in_play": "basic tenses + articles"},
        "intermediate": {"sentence_count": 7, "error_count": 4, "grammar_rules_in_play": "tenses + prepositions + agreement"},
        "advanced": {"sentence_count": 10, "error_count": 6, "grammar_rules_in_play": "all rules including conditionals + passive"},
    },
)


GRAMMAR_WRITE_SENTENCE_TRANSFORMATION_V1 = TaskTemplate(
    template_id="grammar_write_sentence_transformation_v1",
    sub_skill=SubSkill.GRAMMAR,
    activity=Activity.WRITE,
    task_type="sentence_transformation",
    difficulty_range=(4, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
You are an English teacher. Generate sentence-transformation exercises
that push the learner from simple sentences to richer structures.

LEARNER PROFILE
- Sub-level: {sub_level}
- Weak grammar areas: {weak_areas}

TASK
Generate {item_count} items. For each:
- Provide a SIMPLE original sentence
- Set a transformation target (e.g. make_complex, add_relative_clause)
- Give the expected grammar pattern
- Provide a sample correct answer
- List 2–3 grading criteria the AI evaluator will use

Return ONLY valid JSON matching the SentenceTransformationTask schema.
""",
    output_model_name="SentenceTransformationTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {"grammar": 0.5, "structure_match": 0.3, "naturalness": 0.2},
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "intermediate": {"item_count": 3},
        "advanced": {"item_count": 5},
    },
)


GRAMMAR_WRITE_VOICE_CONVERSION_V1 = TaskTemplate(
    template_id="grammar_write_voice_conversion_v1",
    sub_skill=SubSkill.GRAMMAR,
    activity=Activity.WRITE,
    task_type="voice_conversion",
    difficulty_range=(5, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Generate active ↔ passive voice conversion exercises.

LEARNER PROFILE
- Sub-level: {sub_level}
- Topic: {topic}

TASK
Create {item_count} items mixing both directions:
- Some active → passive
- Some passive → active
- Provide the correct answer
- Note one common mistake learners make for each item

Return ONLY valid JSON matching the VoiceConversionTask schema.
""",
    output_model_name="VoiceConversionTask",
    evaluation_logic={
        "method": "fuzzy_match",
        "tolerance": "ignore_case_and_trailing_punctuation",
        "passing_threshold": 0.75,
    },
    difficulty_modifiers={
        "intermediate": {"item_count": 4},
        "advanced": {"item_count": 6},
    },
)


GRAMMAR_WRITE_ERROR_CORRECTION_V1 = TaskTemplate(
    template_id="grammar_write_error_correction_v1",
    sub_skill=SubSkill.GRAMMAR,
    activity=Activity.WRITE,
    task_type="error_correction",
    difficulty_range=(2, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.HYBRID,
    llm_prompt_template="""
Create error-correction exercises. The learner reads an INCORRECT sentence
and must rewrite it correctly.

LEARNER PROFILE
- Sub-level: {sub_level}
- Weak grammar areas: {weak_areas}

TASK
Generate {item_count} sentences:
- Each contains exactly ONE grammar error
- Errors should match the learner's weak areas: {weak_areas}
- Provide the correct version + error type + 1-line explanation

Return ONLY valid JSON matching the ErrorCorrectionTask schema.
""",
    output_model_name="ErrorCorrectionTask",
    evaluation_logic={
        "method": "rule_first_then_ai",
        "rule": "exact_match against correct_sentence (case-insensitive, punctuation-tolerant)",
        "ai_fallback": "if rule fails, AI judges if user's version is grammatically correct",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "beginner": {"item_count": 4},
        "intermediate": {"item_count": 6},
        "advanced": {"item_count": 8},
    },
)


GRAMMAR_LISTEN_DETECT_ERRORS_V1 = TaskTemplate(
    template_id="grammar_listen_detect_errors_v1",
    sub_skill=SubSkill.GRAMMAR,
    activity=Activity.LISTEN,
    task_type="detect_grammar_errors_audio",
    difficulty_range=(4, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Generate spoken sentences (as transcripts) for a listening grammar test.
The TTS pipeline will later convert each transcript to audio.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
Generate {item_count} sentences:
- About half should contain a grammar error
- The other half are correct
- Errors should be HEARABLE (subject-verb agreement, wrong tense, missing article)
- Avoid silent typos that don't affect speech

Return ONLY valid JSON matching the ListenGrammarErrorTask schema.
Set audio_url to null — it will be populated after TTS generation.
""",
    output_model_name="ListenGrammarErrorTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "0.5 for has_error correctness + 0.5 for error_type when applicable",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "intermediate": {"item_count": 4},
        "advanced": {"item_count": 6},
    },
)


GRAMMAR_SPEAK_USE_TENSE_V1 = TaskTemplate(
    template_id="grammar_speak_use_tense_v1",
    sub_skill=SubSkill.GRAMMAR,
    activity=Activity.SPEAK,
    task_type="speak_with_tense",
    difficulty_range=(3, 10),
    estimated_time_minutes=5,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a speaking task where the learner speaks for {duration} seconds
using a SPECIFIC tense.

LEARNER PROFILE
- Sub-level: {sub_level}
- Weak grammar areas: {weak_areas}

TASK
- Pick ONE target tense from the learner's weak areas: {weak_areas}
- Provide a speaking prompt (a topic or scenario)
- Specify a minimum number of sentences ({min_sentences})
- List 3 grading criteria (tense usage, fluency, accuracy)
- Provide a 4–6 sentence sample response that uses the target tense correctly

Return ONLY valid JSON matching the SpeakWithTenseTask schema.
""",
    output_model_name="SpeakWithTenseTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {"target_tense_usage": 0.5, "grammar_accuracy": 0.3, "fluency": 0.2},
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "beginner": {"duration": 30, "min_sentences": 3},
        "intermediate": {"duration": 60, "min_sentences": 4},
        "advanced": {"duration": 90, "min_sentences": 6},
    },
)


GRAMMAR_SPEAK_SENTENCE_COMBINERS_V1 = TaskTemplate(
    template_id="grammar_speak_sentence_combiners_v1",
    sub_skill=SubSkill.GRAMMAR,
    activity=Activity.SPEAK,
    task_type="speak_sentence_combiners",
    difficulty_range=(4, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Generate sentence-combining exercises the learner will complete BY SPEAKING.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
Generate {item_count} pairs of short sentences. For each:
- Two simple fragments (e.g. "He was tired." / "He finished the work.")
- Specify the target combination type (compound, complex, conditional, relative_clause)
- Provide a sample combined sentence

Return ONLY valid JSON matching the SpeakSentenceCombinersTask schema.
""",
    output_model_name="SpeakSentenceCombinersTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {"correct_combiner_used": 0.5, "grammar": 0.3, "delivery": 0.2},
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "intermediate": {"item_count": 3},
        "advanced": {"item_count": 5},
    },
)


# ═════════════════════════════════════════════════════════════════════
# REGISTRY — every template grouped by (activity) for the Task Selector
# ═════════════════════════════════════════════════════════════════════


GRAMMAR_TEMPLATES: list[TaskTemplate] = [
    GRAMMAR_READ_FILL_BLANKS_V1,
    GRAMMAR_READ_ERROR_SPOTTING_V1,
    GRAMMAR_WRITE_SENTENCE_TRANSFORMATION_V1,
    GRAMMAR_WRITE_VOICE_CONVERSION_V1,
    GRAMMAR_WRITE_ERROR_CORRECTION_V1,
    GRAMMAR_LISTEN_DETECT_ERRORS_V1,
    GRAMMAR_SPEAK_USE_TENSE_V1,
    GRAMMAR_SPEAK_SENTENCE_COMBINERS_V1,
]


# Map of LLM-output Pydantic models — used by the validator to pick the
# right schema based on `template.output_model_name`.
GRAMMAR_OUTPUT_MODELS = {
    "FillInBlanksTask": FillInBlanksTask,
    "ErrorSpottingTask": ErrorSpottingTask,
    "SentenceTransformationTask": SentenceTransformationTask,
    "VoiceConversionTask": VoiceConversionTask,
    "ErrorCorrectionTask": ErrorCorrectionTask,
    "ListenGrammarErrorTask": ListenGrammarErrorTask,
    "SpeakWithTenseTask": SpeakWithTenseTask,
    "SpeakSentenceCombinersTask": SpeakSentenceCombinersTask,
}
