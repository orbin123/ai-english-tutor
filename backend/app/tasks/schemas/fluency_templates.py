"""
Fluency & Spontaneity — Task Templates.

Sub-Skill #4 of 7. Covers fluency, spontaneity, small talk handling,
and self-correction ability across all 4 core activities.

KEY DIFFERENCE FROM OTHER SUB-SKILLS:
Fluency is measured by SPEED + SMOOTHNESS, not correctness. Templates
prioritize speech-rate metrics, filler counts, pause analysis, and
real-time response — not "right vs wrong" answers.

TEMPLATES IN THIS FILE
──────────────────────
Read    │ 1. Speed reading aloud (timed reading rate)
Write   │ 2. Timed writing (no editing allowed)
Listen  │ 3. Shadowing exercise (live audio mirroring)
Speak   │ 4. Random topic speaking (60s, no prep)
        │ 5. Continuous talking drill (no pauses allowed)
        │ 6. Small talk simulation
        │ 7. Curveball Q&A (unexpected questions)
        │ 8. Self-correction drill

Total: 8 Fluency templates.
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
# SHARED LABELS
# ═════════════════════════════════════════════════════════════════════


# Words-per-minute targets for reading aloud (from research norms)
ReadingSpeedTier = Literal["slow", "natural", "fast"]


# Common filler words tracked by the evaluator
FillerWord = Literal["um", "uh", "like", "you_know", "actually", "basically", "literally"]


# Small talk scenarios — match real workplace situations
SmallTalkScenario = Literal[
    "elevator_meeting",         # 30 sec with a colleague
    "coffee_break",             # 2 min casual chat
    "intro_at_event",           # meeting someone new
    "weekend_chat",             # Monday morning casual catch-up
    "weather_starter",          # classic English ice-breaker
    "compliment_response",      # handling praise gracefully
]


# ═════════════════════════════════════════════════════════════════════
# LAYER 2 — PYDANTIC MODELS
# ═════════════════════════════════════════════════════════════════════


# ─── Template 1: Speed Reading Aloud (Read) ───────────────────────────


class SpeedReadingTask(GeneratedTaskBase):
    instructions: str
    passage: str = Field(..., min_length=100, max_length=600)
    word_count: int
    target_wpm: int = Field(
        ..., ge=80, le=200,
        description="Target words-per-minute for the learner's level",
    )
    time_limit_seconds: int
    expected_difficult_words: list[str] = Field(
        ..., min_length=2,
        description="Words that may slow the learner down",
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 2: Timed Writing (Write) ────────────────────────────────


class TimedWritingTask(GeneratedTaskBase):
    instructions: str
    writing_prompt: str = Field(..., description="The topic or scenario to write about")
    time_limit_seconds: int = Field(default=300, ge=60, le=900)
    minimum_word_count: int
    target_word_count: int
    no_editing_allowed: bool = Field(
        default=True,
        description="If true, frontend disables backspace/delete after 3 seconds",
    )
    grading_criteria: list[str] = Field(..., min_length=3)
    sample_response: str


# ─── Template 3: Shadowing Exercise (Listen) ──────────────────────────


class ShadowingExerciseTask(GeneratedTaskBase):
    instructions: str
    text_to_shadow: str = Field(..., min_length=50, max_length=300)
    reference_audio_url: str | None = Field(
        None, description="ElevenLabs TTS reference, filled later"
    )
    speed: ReadingSpeedTier
    delay_seconds: float = Field(
        default=0.5, ge=0, le=3,
        description="How long after the audio starts the learner begins (0=simultaneous)",
    )
    minimum_match_percentage: float = Field(default=0.7, ge=0, le=1)
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 4: Random Topic Speaking (Speak) ────────────────────────


class RandomTopicTask(GeneratedTaskBase):
    instructions: str
    topic: str = Field(..., description="The randomly assigned topic")
    topic_category: Literal[
        "personal_experience", "opinion", "describe_something",
        "hypothetical", "explain_process", "compare_two_things",
    ]
    preparation_seconds: int = Field(default=0, ge=0, le=30)
    speaking_duration_seconds: int = Field(default=60, ge=30, le=180)
    minimum_words: int
    sample_talking_points: list[str] = Field(
        ..., min_length=3, max_length=5,
        description="Hints to help the user structure thoughts (shown AFTER they finish)",
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 5: Continuous Talking Drill (Speak) ─────────────────────


class ContinuousTalkingTask(GeneratedTaskBase):
    instructions: str
    starter_prompt: str = Field(..., description="A topic to start talking about")
    duration_seconds: int = Field(default=90, ge=60, le=240)
    max_pause_seconds: float = Field(
        default=2.0, ge=1, le=5,
        description="Pauses longer than this break the streak",
    )
    forbidden_fillers: list[FillerWord] = Field(
        ..., min_length=2,
        description="Filler words that count as failures when used",
    )
    rule_explanation: str = Field(
        ...,
        description="Explain the no-pause-no-filler rule in plain language",
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 6: Small Talk Simulation (Speak) ────────────────────────


class SmallTalkExchange(BaseModel):
    turn_id: str
    speaker: Literal["ai", "user"]
    ai_line: str | None = Field(None, description="AI's line if speaker='ai'")
    expected_user_response_type: Literal[
        "agree_and_extend",
        "polite_disagreement",
        "ask_back_question",
        "share_personal",
        "wrap_up_politely",
    ] | None = None


class SmallTalkSimulationTask(GeneratedTaskBase):
    instructions: str
    scenario: SmallTalkScenario
    setting_description: str = Field(
        ..., description="Where this happens (e.g. 'office kitchen, Monday 9am')"
    )
    exchanges: list[SmallTalkExchange] = Field(..., min_length=4, max_length=8)
    cultural_notes: list[str] = Field(
        default_factory=list,
        description="Cultural tips for the learner (e.g. 'In US, weather talk is just polite filler')",
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 7: Curveball Q&A (Speak) ────────────────────────────────


class CurveballQuestion(BaseModel):
    question_id: str
    question: str = Field(..., description="An unexpected/abstract question")
    question_type: Literal[
        "would_you_rather",
        "abstract_what_if",
        "quirky_personal",
        "opinion_no_right_answer",
        "describe_with_constraint",
    ]
    response_time_limit_seconds: int = Field(default=45, ge=20, le=120)
    sample_answer: str
    expected_recovery_strategies: list[str] = Field(
        ..., min_length=2,
        description="e.g. ['use stalling phrases like \"That\\'s an interesting question...\"', 'pick one angle and commit']",
    )


class CurveballQATask(GeneratedTaskBase):
    instructions: str
    questions: list[CurveballQuestion] = Field(..., min_length=3, max_length=5)
    preparation_allowed: bool = Field(default=False)
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 8: Self-Correction Drill (Speak) ────────────────────────


class SelfCorrectionItem(BaseModel):
    item_id: str
    seed_sentence: str = Field(
        ...,
        description="A sentence the learner says first (may have an error or simple structure)",
    )
    expected_correction_type: Literal[
        "fix_grammar_error",
        "upgrade_vocabulary",
        "make_more_specific",
        "rephrase_more_naturally",
    ]
    sample_corrected_version: str
    correction_phrases_to_practice: list[str] = Field(
        ..., min_length=2,
        description="e.g. ['I mean...', 'Or rather...', 'Let me rephrase that...']",
    )


class SelfCorrectionDrillTask(GeneratedTaskBase):
    instructions: str
    items: list[SelfCorrectionItem] = Field(..., min_length=3, max_length=6)
    rule_explanation: str = Field(
        ...,
        description="Teach why self-correction is a STRENGTH, not a weakness",
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ═════════════════════════════════════════════════════════════════════
# LAYER 1 — TEMPLATE DEFINITIONS
# ═════════════════════════════════════════════════════════════════════


FLUENCY_READ_SPEED_READING_V1 = TaskTemplate(
    template_id="fluency_read_speed_reading_v1",
    sub_skill=SubSkill.FLUENCY,
    activity=Activity.READ,
    task_type="speed_reading_aloud",
    difficulty_range=(2, 10),
    estimated_time_minutes=4,
    scoring_method=ScoringMethod.SPEECH_API,
    llm_prompt_template="""
Create a timed reading-aloud exercise. The learner reads a passage aloud
within a strict time limit, building reading fluency.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}
- Current reading speed (WPM): {current_wpm}

TASK
1. Generate a {word_count}-word passage about a {domain} topic
2. Use vocabulary appropriate to sub-level {sub_level}
3. Avoid words requiring careful pronunciation (this is a SPEED test, not accuracy)
4. Set target_wpm to {target_wpm}
5. Calculate time_limit_seconds = (word_count / target_wpm) * 60
6. List 2–4 expected_difficult_words that may slow the reader down
7. List 3 grading criteria (WPM achieved, completeness, intelligibility)

Return ONLY valid JSON matching the SpeedReadingTask schema.
""",
    output_model_name="SpeedReadingTask",
    evaluation_logic={
        "method": "azure_speech + wpm_calculation",
        "metrics_returned": ["actual_wpm", "completeness_score", "intelligibility_score"],
        "weights": {
            "wpm_target_met": 0.5,
            "completeness": 0.3,
            "intelligibility": 0.2,
        },
        "passing_threshold": 0.7,
        "notes": "Don't penalize minor pronunciation errors — this is a fluency test",
    },
    difficulty_modifiers={
        "beginner": {"word_count": 100, "target_wpm": 90, "current_wpm": 70},
        "intermediate": {"word_count": 180, "target_wpm": 120, "current_wpm": 100},
        "advanced": {"word_count": 250, "target_wpm": 150, "current_wpm": 130},
    },
)


FLUENCY_WRITE_TIMED_WRITING_V1 = TaskTemplate(
    template_id="fluency_write_timed_writing_v1",
    sub_skill=SubSkill.FLUENCY,
    activity=Activity.WRITE,
    task_type="timed_writing",
    difficulty_range=(2, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a timed writing exercise. The learner writes about a topic within
a strict time limit — building written fluency by removing the editing crutch.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
1. Provide a writing prompt relevant to {domain}
   (e.g. "Describe your typical workday in 3 paragraphs")
2. Set time_limit_seconds to {time_limit}
3. Set minimum_word_count to {min_words} and target_word_count to {target_words}
4. Set no_editing_allowed to true
5. List 3 grading criteria (word count met, idea flow, basic correctness)
6. Provide a sample_response showing what a good answer looks like

The goal: produce volume + flow, NOT polish.

Return ONLY valid JSON matching the TimedWritingTask schema.
""",
    output_model_name="TimedWritingTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "word_count_met": 0.4,
            "idea_flow": 0.3,
            "basic_grammar": 0.2,
            "topic_relevance": 0.1,
        },
        "passing_threshold": 0.6,
        "notes": "Forgive minor errors aggressively — this measures FLOW, not perfection",
    },
    difficulty_modifiers={
        "beginner": {"time_limit": 180, "min_words": 60, "target_words": 100},
        "intermediate": {"time_limit": 300, "min_words": 120, "target_words": 200},
        "advanced": {"time_limit": 480, "min_words": 200, "target_words": 350},
    },
)


FLUENCY_LISTEN_SHADOWING_V1 = TaskTemplate(
    template_id="fluency_listen_shadowing_v1",
    sub_skill=SubSkill.FLUENCY,
    activity=Activity.LISTEN,
    task_type="shadowing_exercise",
    difficulty_range=(3, 10),
    estimated_time_minutes=5,
    scoring_method=ScoringMethod.SPEECH_API,
    llm_prompt_template="""
Create a shadowing exercise — the learner repeats audio with a tiny delay,
training real-time language processing.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
1. Generate a {word_range}-word passage on a {domain}-relevant topic
2. Use natural conversational rhythm (not formal/academic)
3. Set speed to {speed}
4. Set delay_seconds to {delay} (lower = harder)
5. Set minimum_match_percentage to 0.7
6. List 3 grading criteria (sync accuracy, completeness, rhythm match)
7. Set reference_audio_url to null (ElevenLabs fills it)

Return ONLY valid JSON matching the ShadowingExerciseTask schema.
""",
    output_model_name="ShadowingExerciseTask",
    evaluation_logic={
        "method": "azure_speech + temporal_alignment",
        "weights": {
            "match_percentage": 0.5,
            "rhythm_sync": 0.3,
            "completeness": 0.2,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "beginner": {"word_range": "30-50", "speed": "slow", "delay": 1.5},
        "intermediate": {"word_range": "50-80", "speed": "natural", "delay": 1.0},
        "advanced": {"word_range": "80-120", "speed": "fast", "delay": 0.5},
    },
)


FLUENCY_SPEAK_RANDOM_TOPIC_V1 = TaskTemplate(
    template_id="fluency_speak_random_topic_v1",
    sub_skill=SubSkill.FLUENCY,
    activity=Activity.SPEAK,
    task_type="random_topic_speaking",
    difficulty_range=(2, 10),
    estimated_time_minutes=4,
    scoring_method=ScoringMethod.SPEECH_API,
    llm_prompt_template="""
Create a random-topic speaking task. The learner speaks for {duration} seconds
on a surprise topic with {prep_time} seconds of preparation.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}
- Topics already covered: {previous_topics}

TASK
1. Pick a topic relevant to general life or {domain} domain
   (avoid previous_topics to keep it fresh)
2. Tag it with topic_category
3. Set preparation_seconds to {prep_time}
4. Set speaking_duration_seconds to {duration}
5. Set minimum_words to {min_words}
6. Provide 3–5 sample_talking_points (only shown AFTER user finishes —
   so they don't lean on hints during the actual task)
7. List 3 grading criteria (fluency rate, content coverage, no excessive fillers)

Return ONLY valid JSON matching the RandomTopicTask schema.
""",
    output_model_name="RandomTopicTask",
    evaluation_logic={
        "method": "azure_speech + ai_content_evaluator",
        "weights": {
            "wpm_naturalness": 0.3,
            "filler_rate": 0.2,        # lower = better
            "content_coverage": 0.3,
            "topic_adherence": 0.2,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "beginner": {"prep_time": 30, "duration": 45, "min_words": 60},
        "intermediate": {"prep_time": 15, "duration": 60, "min_words": 100},
        "advanced": {"prep_time": 0, "duration": 90, "min_words": 160},
    },
)


FLUENCY_SPEAK_CONTINUOUS_TALKING_V1 = TaskTemplate(
    template_id="fluency_speak_continuous_talking_v1",
    sub_skill=SubSkill.FLUENCY,
    activity=Activity.SPEAK,
    task_type="continuous_talking_drill",
    difficulty_range=(3, 10),
    estimated_time_minutes=4,
    scoring_method=ScoringMethod.SPEECH_API,
    llm_prompt_template="""
Create a continuous talking drill — the learner MUST keep speaking with no
long pauses and no filler words. Builds raw fluency under pressure.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
1. Provide a starter_prompt (something easy to talk about)
   e.g. "Describe your morning routine"
2. Set duration_seconds to {duration}
3. Set max_pause_seconds to {max_pause}
4. List forbidden_fillers (at least 2 common ones the learner overuses)
5. Write a clear rule_explanation that motivates WHY this drill helps
6. List 3 grading criteria (pause count, filler count, total speaking time)

Return ONLY valid JSON matching the ContinuousTalkingTask schema.
""",
    output_model_name="ContinuousTalkingTask",
    evaluation_logic={
        "method": "azure_speech + pause_filler_analysis",
        "scoring_rule": "Each long pause = -0.1, each forbidden filler = -0.05",
        "weights": {
            "pause_compliance": 0.4,
            "filler_compliance": 0.3,
            "total_words_produced": 0.3,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "beginner": {"duration": 60, "max_pause": 3.0},
        "intermediate": {"duration": 90, "max_pause": 2.0},
        "advanced": {"duration": 120, "max_pause": 1.5},
    },
)


FLUENCY_SPEAK_SMALL_TALK_V1 = TaskTemplate(
    template_id="fluency_speak_small_talk_v1",
    sub_skill=SubSkill.FLUENCY,
    activity=Activity.SPEAK,
    task_type="small_talk_simulation",
    difficulty_range=(3, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a small talk simulation — the AI plays a colleague/stranger, the
learner navigates a casual conversation. Builds REAL workplace fluency.

LEARNER PROFILE
- Sub-level: {sub_level}
- Career domain: {domain}
- Cultural context: {cultural_context}

TASK
1. Pick a small talk scenario from: {scenario_options}
2. Write a setting_description (where/when this happens)
3. Generate {turn_count} exchanges alternating ai/user turns
   - Start with an AI line
   - For each user turn, set expected_user_response_type
4. Add 2–3 cultural_notes that help non-native speakers handle this scenario
   (e.g. "In US workplaces, 'How are you?' isn't a real question — answer with 'Good, you?'")
5. List 3 grading criteria (natural flow, appropriate register, conversation maintenance)

Return ONLY valid JSON matching the SmallTalkSimulationTask schema.
""",
    output_model_name="SmallTalkSimulationTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "naturalness": 0.3,
            "register_appropriateness": 0.25,
            "conversation_maintenance": 0.25,
            "fluency_smoothness": 0.2,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "beginner": {
            "scenario_options": "weather_starter, weekend_chat",
            "turn_count": 4,
        },
        "intermediate": {
            "scenario_options": "elevator_meeting, coffee_break, weekend_chat",
            "turn_count": 6,
        },
        "advanced": {
            "scenario_options": "intro_at_event, compliment_response, coffee_break",
            "turn_count": 8,
        },
    },
)


FLUENCY_SPEAK_CURVEBALL_QA_V1 = TaskTemplate(
    template_id="fluency_speak_curveball_qa_v1",
    sub_skill=SubSkill.FLUENCY,
    activity=Activity.SPEAK,
    task_type="curveball_qa",
    difficulty_range=(5, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a curveball Q&A task — unexpected, abstract, or weird questions
the learner must answer ON THE SPOT. Trains real-world spontaneity.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
1. Generate {question_count} surprise questions across question_types
   Examples by type:
   - would_you_rather: "Would you rather lose your phone or your wallet?"
   - abstract_what_if: "If colors had sounds, what would blue sound like?"
   - quirky_personal: "What's the weirdest food combination you secretly enjoy?"
   - opinion_no_right_answer: "Are mornings overrated?"
   - describe_with_constraint: "Describe your job using only food metaphors"
2. Set response_time_limit_seconds to {time_limit}
3. Provide a sample_answer for each (4–6 sentences)
4. List 2–3 expected_recovery_strategies — phrases like
   "That's a fun question!" to buy thinking time
5. Set preparation_allowed to false
6. List 3 grading criteria (response time, content quality, smooth recovery)

Return ONLY valid JSON matching the CurveballQATask schema.
""",
    output_model_name="CurveballQATask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "response_speed": 0.25,
            "content_creativity": 0.25,
            "fluency_under_pressure": 0.3,
            "stalling_phrase_usage": 0.2,
        },
        "passing_threshold": 0.55,
    },
    difficulty_modifiers={
        "intermediate": {"question_count": 3, "time_limit": 60},
        "advanced": {"question_count": 5, "time_limit": 45},
    },
)


FLUENCY_SPEAK_SELF_CORRECTION_V1 = TaskTemplate(
    template_id="fluency_speak_self_correction_v1",
    sub_skill=SubSkill.FLUENCY,
    activity=Activity.SPEAK,
    task_type="self_correction_drill",
    difficulty_range=(4, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a self-correction drill — the learner says a sentence, then
mid-stream catches and fixes their own choice. This is a HALLMARK
of advanced fluency that most courses ignore.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
1. Generate {item_count} items. For each:
   - Provide a seed_sentence the learner says first (often imperfect)
   - Mark expected_correction_type
   - Provide a sample_corrected_version
   - List 2–4 correction_phrases_to_practice
     (e.g. "I mean...", "Or rather...", "Sorry, what I meant was...",
      "Let me rephrase that...")
2. Write a rule_explanation that reframes self-correction as a STRENGTH
   (native speakers self-correct constantly — it shows fluency, not weakness)
3. List 3 grading criteria (correction phrase used, smooth transition, improved version quality)

Return ONLY valid JSON matching the SelfCorrectionDrillTask schema.
""",
    output_model_name="SelfCorrectionDrillTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "correction_phrase_used": 0.3,
            "transition_smoothness": 0.3,
            "improved_version_quality": 0.4,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "intermediate": {"item_count": 3},
        "advanced": {"item_count": 5},
    },
)


# ═════════════════════════════════════════════════════════════════════
# REGISTRY
# ═════════════════════════════════════════════════════════════════════


FLUENCY_TEMPLATES: list[TaskTemplate] = [
    FLUENCY_READ_SPEED_READING_V1,
    FLUENCY_WRITE_TIMED_WRITING_V1,
    FLUENCY_LISTEN_SHADOWING_V1,
    FLUENCY_SPEAK_RANDOM_TOPIC_V1,
    FLUENCY_SPEAK_CONTINUOUS_TALKING_V1,
    FLUENCY_SPEAK_SMALL_TALK_V1,
    FLUENCY_SPEAK_CURVEBALL_QA_V1,
    FLUENCY_SPEAK_SELF_CORRECTION_V1,
]


FLUENCY_OUTPUT_MODELS = {
    "SpeedReadingTask": SpeedReadingTask,
    "TimedWritingTask": TimedWritingTask,
    "ShadowingExerciseTask": ShadowingExerciseTask,
    "RandomTopicTask": RandomTopicTask,
    "ContinuousTalkingTask": ContinuousTalkingTask,
    "SmallTalkSimulationTask": SmallTalkSimulationTask,
    "CurveballQATask": CurveballQATask,
    "SelfCorrectionDrillTask": SelfCorrectionDrillTask,
}
