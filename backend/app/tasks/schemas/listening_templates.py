"""
Listening & Comprehension — Task Templates.

Sub-Skill #6 of 7. Covers BOTH listening comprehension AND reading
comprehension — the two "input" sides of language. While every other
sub-skill measures what the learner PRODUCES, this one measures what
the learner UNDERSTANDS.

KEY DIFFERENCE FROM OTHER SUB-SKILLS
This is a RECEPTIVE skill. The learner is given audio or text, and the
task is to demonstrate understanding — not to produce polished English.
Templates therefore lean heavily on rule-based scoring (MCQs, exact
matches) because what we're checking is comprehension accuracy.

TWO DIMENSIONS COVERED
  • Listening comprehension — processing spoken English
  • Reading comprehension   — processing written English

Both share the same underlying challenge: catching meaning beyond the
literal words at natural speed.

TEMPLATES IN THIS FILE
──────────────────────
Read    │ 1. Reading comprehension MCQ (passage + 4–6 questions)
        │ 2. True / False / Not Given (IELTS-style inference test)
Write   │ 3. Write answers from audio (open-ended short answers)
Listen  │ 4. Audio MCQ (the core listening drill)
        │ 5. Cloze listening (fill missing words in transcript)
        │ 6. Dictation (write what you hear, word-for-word)
        │ 7. Inference questions (what does the speaker IMPLY?)
Speak   │ 8. Retell what you heard (verbal reformulation)

Total: 8 Listening templates.
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
# SHARED LABELS — used across multiple templates in this file
# ═════════════════════════════════════════════════════════════════════


# Question types used in reading + listening comprehension templates.
# Tagging each question lets the Evaluator track WHICH kind of
# comprehension is weak (e.g. user always misses inference questions).
ComprehensionQuestionType = Literal[
    "main_idea",              # what is the passage/audio primarily about?
    "specific_detail",        # what does it say about X?
    "inference",              # what can you infer that isn't stated?
    "vocabulary_in_context",  # what does word X mean here?
    "tone_or_purpose",        # why did the speaker/author say this?
    "reference",              # what does pronoun/phrase X refer to?
]


# Audio content genres — affects HOW the learner has to listen.
# A monologue is steady; a dialogue requires speaker-tracking.
AudioGenre = Literal[
    "monologue",     # one person speaking (lecture, podcast snippet)
    "dialogue",      # 2-person conversation
    "interview",     # Q&A style
    "announcement",  # public announcement, advert
    "narration",     # storytelling
]


# Three-way verdict used in IELTS-style comprehension tasks.
# "not_given" is the trickiest — it forces the learner to distinguish
# between "the text contradicts this" and "the text just doesn't say".
TrueFalseNotGiven = Literal["true", "false", "not_given"]


# ═════════════════════════════════════════════════════════════════════
# LAYER 2 — PYDANTIC MODELS (validate LLM output for each template)
# ═════════════════════════════════════════════════════════════════════


# ─── Template 1: Reading Comprehension MCQ (Read) ─────────────────────


class ComprehensionMCQItem(BaseModel):
    question_id: str
    question_type: ComprehensionQuestionType
    question: str
    options: list[str] = Field(..., min_length=4, max_length=4)
    correct_answer: str = Field(
        ..., description="Must match exactly one of the options"
    )
    explanation: str = Field(..., min_length=15, max_length=300)
    evidence_phrase: str | None = Field(
        None,
        description="Direct quote from the passage that justifies the answer "
        "(null for pure inference questions where no single phrase suffices)",
    )


class ReadingComprehensionMCQTask(GeneratedTaskBase):
    passage_title: str
    passage: str = Field(..., min_length=200, max_length=1000)
    questions: list[ComprehensionMCQItem] = Field(..., min_length=4, max_length=8)


# ─── Template 2: True / False / Not Given (Read) ──────────────────────


class TFNGStatement(BaseModel):
    statement_id: str
    statement: str
    verdict: TrueFalseNotGiven
    justification: str = Field(
        ...,
        description=(
            "For 'true'/'false': cite the passage line that proves it. "
            "For 'not_given': explain why the passage neither confirms nor denies."
        ),
    )


class TrueFalseNotGivenTask(GeneratedTaskBase):
    instructions: str
    passage_title: str
    passage: str = Field(..., min_length=200, max_length=900)
    statements: list[TFNGStatement] = Field(..., min_length=5, max_length=8)


# ─── Template 3: Write Answers from Audio (Write) ─────────────────────


class AudioShortAnswerItem(BaseModel):
    question_id: str
    question: str
    question_type: ComprehensionQuestionType
    sample_correct_answer: str = Field(
        ..., description="A model answer the AI evaluator compares against"
    )
    acceptable_keywords: list[str] = Field(
        ..., min_length=1, max_length=6,
        description="Keywords that MUST appear (or be paraphrased) in a correct answer",
    )
    answer_max_words: int = Field(default=20, ge=3, le=50)


class WriteAnswersFromAudioTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None,
        description="Filled later by TTS pipeline; null until audio is generated",
    )
    audio_transcript: str = Field(
        ..., min_length=200, max_length=900,
        description="What the speaker says — TTS will convert this to audio",
    )
    audio_genre: AudioGenre
    questions: list[AudioShortAnswerItem] = Field(..., min_length=3, max_length=6)


# ─── Template 4: Audio MCQ (Listen) ───────────────────────────────────


class AudioMCQItem(BaseModel):
    question_id: str
    question_type: ComprehensionQuestionType
    question: str
    options: list[str] = Field(..., min_length=4, max_length=4)
    correct_answer: str
    explanation: str = Field(..., min_length=15, max_length=300)
    timestamp_hint: str | None = Field(
        None,
        description="Optional hint about where in the audio the answer comes from "
        "(e.g. 'around 0:20', 'near the end'). Null if not used.",
    )


class AudioMCQTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled later by TTS pipeline; null until audio is generated"
    )
    audio_transcript: str = Field(..., min_length=150, max_length=900)
    audio_genre: AudioGenre
    questions: list[AudioMCQItem] = Field(..., min_length=4, max_length=8)


# ─── Template 5: Cloze Listening (Listen) ─────────────────────────────


class ClozeBlank(BaseModel):
    blank_id: str = Field(..., description="e.g. 'b1', 'b2'")
    correct_answer: str = Field(
        ..., min_length=1, max_length=40,
        description="The exact word(s) that fill the blank",
    )
    word_count: int = Field(
        ..., ge=1, le=4,
        description="How many words go in this blank (1–4)",
    )
    hint: str | None = Field(
        None, description="Optional hint about the missing word's role/meaning"
    )


class ClozeListeningTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled later by TTS pipeline; null until audio is generated"
    )
    full_transcript: str = Field(
        ..., min_length=150, max_length=600,
        description="The COMPLETE transcript — TTS uses this to generate audio",
    )
    transcript_with_blanks: str = Field(
        ...,
        description="Same transcript but with ___ where blanks should be (shown to learner)",
    )
    blanks: list[ClozeBlank] = Field(..., min_length=5, max_length=12)


# ─── Template 6: Dictation (Listen) ───────────────────────────────────


class DictationSegment(BaseModel):
    segment_id: str = Field(..., description="e.g. 's1', 's2'")
    correct_text: str = Field(
        ..., min_length=20, max_length=200,
        description="The EXACT text the learner must reproduce (1–2 sentences)",
    )
    common_mistakes: list[str] = Field(
        default_factory=list, max_length=5,
        description="Typical wrong transcriptions learners produce",
    )


class DictationTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled later by TTS pipeline; null until audio is generated"
    )
    audio_genre: AudioGenre
    playback_rate: Literal["slow", "natural", "natural_repeated"] = Field(
        default="natural_repeated",
        description="natural_repeated = play once at natural speed, then repeat slowly",
    )
    segments: list[DictationSegment] = Field(..., min_length=3, max_length=6)


# ─── Template 7: Inference Questions (Listen) ─────────────────────────


class InferenceQuestion(BaseModel):
    question_id: str
    question: str = Field(
        ...,
        description="An inference question — e.g. 'How does the speaker probably feel?'",
    )
    options: list[str] = Field(..., min_length=4, max_length=4)
    correct_answer: str
    inference_basis: str = Field(
        ...,
        description="Which part of the audio (tone, word choice, context) implies the answer",
    )
    distractor_explanations: list[str] = Field(
        ..., min_length=3, max_length=3,
        description="One explanation per distractor — why it's wrong (over/under-interpretation)",
    )


class InferenceListeningTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled later by TTS pipeline; null until audio is generated"
    )
    audio_transcript: str = Field(..., min_length=200, max_length=800)
    audio_genre: AudioGenre
    questions: list[InferenceQuestion] = Field(..., min_length=3, max_length=6)


# ─── Template 8: Retell What You Heard (Speak) ────────────────────────


class RetellWhatYouHeardTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled later by TTS pipeline; null until audio is generated"
    )
    audio_transcript: str = Field(..., min_length=200, max_length=700)
    audio_genre: AudioGenre
    main_idea: str = Field(..., description="The single core point of the audio")
    key_points_to_cover: list[str] = Field(
        ..., min_length=3, max_length=6,
        description="Key facts/points the retell must include for full credit",
    )
    minimum_duration_seconds: int = Field(default=45, ge=20, le=180)
    sample_retell: str = Field(
        ..., description="A model retell (3–6 sentences) for reference"
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ═════════════════════════════════════════════════════════════════════
# LAYER 1 — TEMPLATE DEFINITIONS (loaded by the Task Selector at startup)
# ═════════════════════════════════════════════════════════════════════


LISTENING_READ_COMPREHENSION_MCQ_V1 = TaskTemplate(
    template_id="listening_read_comprehension_mcq_v1",
    sub_skill=SubSkill.LISTENING,
    activity=Activity.READ,
    task_type="reading_comprehension_mcq",
    difficulty_range=(2, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
You are an English teacher creating a reading comprehension exercise.
The learner reads a passage and answers multiple-choice questions about it.

LEARNER PROFILE
- Sub-level: {sub_level}
- Topic of interest: {topic}

TASK
1. Write a passage of {min_words}–{max_words} words on a relatable topic
2. Use vocabulary appropriate to {vocab_level}
3. Generate exactly {question_count} multiple-choice questions covering a MIX of:
   main_idea, specific_detail, inference, vocabulary_in_context,
   tone_or_purpose, reference
4. For each question:
   - Tag it with question_type
   - Provide exactly 4 options (1 correct + 3 plausible distractors)
   - Write a 1–2 sentence explanation
   - For literal questions, include evidence_phrase (a quote from the passage)
   - For pure inference questions, set evidence_phrase to null

Return ONLY valid JSON matching the ReadingComprehensionMCQTask schema.
No prose, no markdown fences.
""",
    output_model_name="ReadingComprehensionMCQTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct answer, normalized to 0–1",
        "passing_threshold": 0.7,
        "track_per_question_type": True,  # to detect "always misses inference" patterns
    },
    difficulty_modifiers={
        "beginner": {
            "min_words": 200, "max_words": 320,
            "vocab_level": "basic",
            "question_count": 4,
        },
        "intermediate": {
            "min_words": 350, "max_words": 550,
            "vocab_level": "intermediate",
            "question_count": 6,
        },
        "advanced": {
            "min_words": 550, "max_words": 900,
            "vocab_level": "advanced",
            "question_count": 8,
        },
    },
)


LISTENING_READ_TFNG_V1 = TaskTemplate(
    template_id="listening_read_true_false_not_given_v1",
    sub_skill=SubSkill.LISTENING,
    activity=Activity.READ,
    task_type="true_false_not_given",
    difficulty_range=(4, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create an IELTS-style True / False / Not Given exercise. The learner reads
a passage and decides whether each statement is supported, contradicted,
or simply not addressed by the passage.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Write a factual passage of {min_words}–{max_words} words
2. Generate exactly {statement_count} statements with a balanced mix:
   - Roughly 1/3 should be true (clearly supported by the passage)
   - Roughly 1/3 should be false (directly contradicted)
   - Roughly 1/3 should be not_given (the passage neither confirms nor denies)
3. The "not_given" statements MUST be plausible-sounding — not absurd
4. For each statement:
   - Set verdict to "true", "false", or "not_given"
   - For "true"/"false": justification cites the relevant passage line
   - For "not_given": justification explains what the passage actually addresses
     and why this statement is outside that scope

Return ONLY valid JSON matching the TrueFalseNotGivenTask schema.
""",
    output_model_name="TrueFalseNotGivenTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct verdict, normalized to 0–1",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "intermediate": {"min_words": 250, "max_words": 400, "statement_count": 5},
        "advanced": {"min_words": 400, "max_words": 700, "statement_count": 8},
    },
)


LISTENING_WRITE_ANSWERS_FROM_AUDIO_V1 = TaskTemplate(
    template_id="listening_write_answers_from_audio_v1",
    sub_skill=SubSkill.LISTENING,
    activity=Activity.WRITE,
    task_type="write_answers_from_audio",
    difficulty_range=(3, 10),
    estimated_time_minutes=10,
    scoring_method=ScoringMethod.HYBRID,
    llm_prompt_template="""
Create a listening exercise where the learner hears audio and writes
short open-ended answers (not multiple choice).

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick an audio_genre from: monologue, dialogue, interview, announcement, narration
2. Write an audio_transcript of {min_words}–{max_words} words in that genre
3. Generate {question_count} short-answer questions covering a mix of
   question_types: specific_detail, main_idea, inference
4. For each question:
   - Provide a sample_correct_answer (the model answer)
   - List 1–4 acceptable_keywords that any correct answer must contain
     (or paraphrase) — this is what the rule-based pre-check uses
   - Set answer_max_words={max_answer_words}
5. Set audio_url to null (TTS pipeline fills it later)

Return ONLY valid JSON matching the WriteAnswersFromAudioTask schema.
""",
    output_model_name="WriteAnswersFromAudioTask",
    evaluation_logic={
        "method": "rule_first_then_ai",
        "rule": "check user answer contains acceptable_keywords (case-insensitive, allow paraphrase)",
        "ai_fallback": "if rule fails, AI judges semantic equivalence to sample_correct_answer",
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "beginner": {
            "min_words": 150, "max_words": 230,
            "question_count": 3, "max_answer_words": 10,
        },
        "intermediate": {
            "min_words": 250, "max_words": 400,
            "question_count": 4, "max_answer_words": 15,
        },
        "advanced": {
            "min_words": 400, "max_words": 700,
            "question_count": 6, "max_answer_words": 25,
        },
    },
)


LISTENING_LISTEN_AUDIO_MCQ_V1 = TaskTemplate(
    template_id="listening_listen_audio_mcq_v1",
    sub_skill=SubSkill.LISTENING,
    activity=Activity.LISTEN,
    task_type="audio_mcq",
    difficulty_range=(2, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create the core listening drill: audio + multiple-choice comprehension.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick an audio_genre from: monologue, dialogue, interview, announcement, narration
2. Write an audio_transcript of {min_words}–{max_words} words
3. Generate exactly {question_count} multiple-choice questions covering a MIX of:
   main_idea, specific_detail, inference, tone_or_purpose, reference
4. For each question:
   - Tag with question_type
   - Provide exactly 4 options
   - Write a 1–2 sentence explanation
   - Optionally include timestamp_hint (e.g. "near the start") or set null
5. Set audio_url to null (TTS pipeline fills it later)

Return ONLY valid JSON matching the AudioMCQTask schema.
""",
    output_model_name="AudioMCQTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct answer, normalized to 0–1",
        "passing_threshold": 0.7,
        "track_per_question_type": True,
    },
    difficulty_modifiers={
        "beginner": {"min_words": 150, "max_words": 230, "question_count": 4},
        "intermediate": {"min_words": 280, "max_words": 450, "question_count": 6},
        "advanced": {"min_words": 450, "max_words": 800, "question_count": 8},
    },
)


LISTENING_LISTEN_CLOZE_V1 = TaskTemplate(
    template_id="listening_listen_cloze_v1",
    sub_skill=SubSkill.LISTENING,
    activity=Activity.LISTEN,
    task_type="cloze_listening",
    difficulty_range=(2, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a cloze listening exercise. The learner sees a transcript with
blanks and listens to the audio to fill them in.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Write a full_transcript of {min_words}–{max_words} words
2. Pick exactly {blank_count} CONTENT WORDS to remove (nouns, verbs, key
   adjectives — NOT articles or filler words)
3. Build transcript_with_blanks by replacing each chosen word/phrase with ___
4. For each blank provide:
   - blank_id ('b1', 'b2', ...)
   - correct_answer (the exact word/phrase removed)
   - word_count (1–4 — how many words fill this blank)
   - Optional hint about the word's grammatical role
5. Spread blanks evenly through the transcript — don't cluster them
6. Set audio_url to null (TTS pipeline fills it later)

Return ONLY valid JSON matching the ClozeListeningTask schema.
""",
    output_model_name="ClozeListeningTask",
    evaluation_logic={
        "method": "fuzzy_match",
        "tolerance": "case_insensitive, ignore_punctuation, accept_minor_spelling_variants",
        "scoring_rule": "1 point per correctly filled blank, normalized to 0–1",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "beginner": {"min_words": 150, "max_words": 220, "blank_count": 5},
        "intermediate": {"min_words": 250, "max_words": 380, "blank_count": 8},
        "advanced": {"min_words": 380, "max_words": 600, "blank_count": 12},
    },
)


LISTENING_LISTEN_DICTATION_V1 = TaskTemplate(
    template_id="listening_listen_dictation_v1",
    sub_skill=SubSkill.LISTENING,
    activity=Activity.LISTEN,
    task_type="dictation",
    difficulty_range=(2, 10),
    estimated_time_minutes=10,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a dictation exercise. The learner hears audio and types EXACTLY
what was said. This tests phonological accuracy, not just comprehension.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick an audio_genre from: monologue, narration, announcement
   (avoid dialogue/interview — too many speakers confuses dictation)
2. Generate exactly {segment_count} segments. Each segment is a
   self-contained passage of 1–2 sentences ({min_seg_words}–{max_seg_words} words each)
3. Use everyday vocabulary the learner would realistically encounter
4. For each segment:
   - segment_id ('s1', 's2', ...)
   - correct_text (the EXACT text — careful with contractions, punctuation)
   - Optionally list 2–4 common_mistakes learners typically produce
     (homophones, dropped articles, wrong tense)
5. Set playback_rate to "natural_repeated" (play once natural, then once slow)
6. Set audio_url to null (TTS pipeline fills it later)

Return ONLY valid JSON matching the DictationTask schema.
""",
    output_model_name="DictationTask",
    evaluation_logic={
        "method": "fuzzy_match",
        "tolerance": "case_insensitive, ignore_extra_whitespace, normalize_punctuation",
        "scoring_rule": "word-level Levenshtein similarity vs correct_text, averaged across segments",
        "passing_threshold": 0.85,  # dictation should be near-perfect
    },
    difficulty_modifiers={
        "beginner": {"segment_count": 3, "min_seg_words": 6, "max_seg_words": 12},
        "intermediate": {"segment_count": 4, "min_seg_words": 10, "max_seg_words": 20},
        "advanced": {"segment_count": 5, "min_seg_words": 15, "max_seg_words": 30},
    },
)


LISTENING_LISTEN_INFERENCE_V1 = TaskTemplate(
    template_id="listening_listen_inference_v1",
    sub_skill=SubSkill.LISTENING,
    activity=Activity.LISTEN,
    task_type="inference_listening",
    difficulty_range=(5, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a high-level listening exercise focused on INFERENCE — catching
meaning the speaker implies but doesn't directly state.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick an audio_genre from: dialogue, interview, monologue
2. Write an audio_transcript of {min_words}–{max_words} words rich with
   subtext: tone, hesitation, word choice, or context that hints at
   feelings, opinions, or intentions NOT stated outright
3. Generate exactly {question_count} inference questions like:
   - "How does the speaker probably feel about X?"
   - "What does the speaker imply about Y?"
   - "Why does the speaker pause / change topic?"
4. For each question:
   - Provide exactly 4 options (1 correct + 3 distractors)
   - inference_basis: cite the verbal cue (tone, word, pause) that implies the answer
   - distractor_explanations: ONE explanation per distractor — usually
     "over-interpretation" (reads too much in) or "under-interpretation"
     (misses the cue) or "literal-but-wrong"
5. Set audio_url to null (TTS pipeline fills it later)

Return ONLY valid JSON matching the InferenceListeningTask schema.
""",
    output_model_name="InferenceListeningTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct answer, normalized to 0–1",
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "intermediate": {"min_words": 220, "max_words": 350, "question_count": 3},
        "advanced": {"min_words": 350, "max_words": 600, "question_count": 5},
    },
)


LISTENING_SPEAK_RETELL_V1 = TaskTemplate(
    template_id="listening_speak_retell_v1",
    sub_skill=SubSkill.LISTENING,
    activity=Activity.SPEAK,
    task_type="retell_what_you_heard",
    difficulty_range=(3, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a retelling task. The learner listens to audio and then verbally
summarizes what they heard. This combines listening comprehension with
spoken reformulation — a powerful real-world skill.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick an audio_genre from: monologue, narration, interview, announcement
2. Write an audio_transcript of {min_words}–{max_words} words with
   ONE clear main idea + 3–5 supporting points
3. Provide:
   - main_idea (1 sentence)
   - key_points_to_cover (3–5 bullets the retell must hit)
4. Set minimum_duration_seconds={duration}
5. Write a sample_retell (3–6 sentences) that shows a good retell —
   in the learner's own words, NOT a copy of the transcript
6. Provide 3+ grading_criteria: main_idea_captured, key_points_covered,
   own_words_not_copied, fluency
7. Set audio_url to null (TTS pipeline fills it later)

Return ONLY valid JSON matching the RetellWhatYouHeardTask schema.
""",
    output_model_name="RetellWhatYouHeardTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "main_idea_captured": 0.35,
            "key_points_covered": 0.30,
            "own_words_not_copied": 0.20,
            "fluency": 0.15,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "beginner": {"min_words": 150, "max_words": 230, "duration": 30},
        "intermediate": {"min_words": 250, "max_words": 400, "duration": 60},
        "advanced": {"min_words": 400, "max_words": 650, "duration": 90},
    },
)


# ═════════════════════════════════════════════════════════════════════
# REGISTRY — every template grouped for the Task Selector
# ═════════════════════════════════════════════════════════════════════


LISTENING_TEMPLATES: list[TaskTemplate] = [
    LISTENING_READ_COMPREHENSION_MCQ_V1,
    LISTENING_READ_TFNG_V1,
    LISTENING_WRITE_ANSWERS_FROM_AUDIO_V1,
    LISTENING_LISTEN_AUDIO_MCQ_V1,
    LISTENING_LISTEN_CLOZE_V1,
    LISTENING_LISTEN_DICTATION_V1,
    LISTENING_LISTEN_INFERENCE_V1,
    LISTENING_SPEAK_RETELL_V1,
]


# Map of LLM-output Pydantic models — used by the validator to pick the
# right schema based on `template.output_model_name`.
LISTENING_OUTPUT_MODELS = {
    "ReadingComprehensionMCQTask": ReadingComprehensionMCQTask,
    "TrueFalseNotGivenTask": TrueFalseNotGivenTask,
    "WriteAnswersFromAudioTask": WriteAnswersFromAudioTask,
    "AudioMCQTask": AudioMCQTask,
    "ClozeListeningTask": ClozeListeningTask,
    "DictationTask": DictationTask,
    "InferenceListeningTask": InferenceListeningTask,
    "RetellWhatYouHeardTask": RetellWhatYouHeardTask,
}
