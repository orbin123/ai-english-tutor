"""
Thought Organization & Expression — Task Templates.

Sub-Skill #5 of 7. Covers the "thinking in English" layer:
how learners organize ideas, generate content, and re-express
the same thought in different ways.

THREE DIMENSIONS COVERED
  • Thought structuring   — intro/body/conclusion, problem/solution, etc.
  • Idea generation       — coming up with content from a prompt
  • Paraphrasing ability  — re-saying the same idea differently

KEY DIFFERENCE FROM OTHER SUB-SKILLS
This sub-skill cares about HOW IDEAS FLOW, not whether grammar/vocab is
perfect. Templates prioritize coherence, structure-match, and connector
usage over mechanical correctness.

TEMPLATES IN THIS FILE
──────────────────────
Read    │ 1. Passage summarization (capture main idea + key points)
        │ 2. Structure identification (spot the organizational pattern)
Write   │ 3. Structured essay writing (intro → body → conclusion)
        │ 4. Idea paraphrasing (re-express same idea N ways)
        │ 5. Bullets → coherent paragraph (organize loose points)
Listen  │ 6. Identify spoken structure (catch the speaker's pattern)
Speak   │ 7. Storyboard narration (connect 3–5 scenes into a story)
        │ 8. Step-by-step explanation (explain a process clearly)

Total: 8 Thought Organization templates.
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


# Common organizational patterns the learner needs to recognize and produce.
# Used by reading-comprehension, listening, and structured-writing templates.
StructurePattern = Literal[
    "intro_body_conclusion",
    "problem_solution",
    "compare_contrast",
    "cause_effect",
    "chronological",
    "sequential_steps",
    "claim_evidence",
    "general_to_specific",
    "specific_to_general",
]


# The styles a paraphrase can target. Each style forces the learner to
# re-express the same idea while changing ONE specific dimension.
ParaphraseStyle = Literal[
    "more_formal",
    "more_casual",
    "more_concise",
    "different_structure",
    "different_vocabulary",
]


# Logical "section roles" used by the structured-essay template.
# The Literal keeps frontend rendering predictable (renders one card per role).
EssaySectionName = Literal[
    "introduction",
    "body_1",
    "body_2",
    "body_3",
    "conclusion",
]


# ═════════════════════════════════════════════════════════════════════
# LAYER 2 — PYDANTIC MODELS (validate LLM output for each template)
# ═════════════════════════════════════════════════════════════════════


# ─── Template 1: Passage Summarization (Read) ─────────────────────────


class PassageSummarizationTask(GeneratedTaskBase):
    passage_title: str
    passage: str = Field(..., min_length=150, max_length=900)
    summary_sentence_min: int = Field(default=2, ge=1, le=5)
    summary_sentence_max: int = Field(default=3, ge=2, le=6)
    main_idea: str = Field(
        ..., description="The single core point of the passage (1 sentence)"
    )
    key_supporting_points: list[str] = Field(..., min_length=2, max_length=5)
    sample_summary: str = Field(
        ..., description="A model summary the evaluator compares against"
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 2: Structure Identification (Read) ──────────────────────


class StructureIdentificationTask(GeneratedTaskBase):
    instructions: str
    passage_title: str
    passage: str = Field(..., min_length=150, max_length=700)
    correct_pattern: StructurePattern
    pattern_options: list[StructurePattern] = Field(..., min_length=4, max_length=4)
    signal_phrases: list[str] = Field(
        ..., min_length=2, max_length=6,
        description="Phrases inside the passage that hint at the structure",
    )
    explanation: str = Field(
        ..., min_length=20, max_length=300,
        description="Why this pattern fits — points out the giveaway signals",
    )


# ─── Template 3: Structured Essay Writing (Write) ─────────────────────


class EssaySection(BaseModel):
    section_name: EssaySectionName
    purpose: str = Field(..., description="What this section should accomplish")
    minimum_sentences: int = Field(..., ge=1, le=8)
    suggested_focus: str = Field(..., description="Hint about what to put here")


class StructuredEssayTask(GeneratedTaskBase):
    instructions: str
    essay_topic: str
    target_word_count_min: int = Field(..., ge=80, le=500)
    target_word_count_max: int = Field(..., ge=100, le=600)
    required_structure: StructurePattern
    sections: list[EssaySection] = Field(..., min_length=3, max_length=5)
    required_connectors: list[str] = Field(
        ..., min_length=3, max_length=8,
        description="Transition words the learner must use (e.g. 'however', 'therefore')",
    )
    sample_outline: str = Field(
        ..., description="A skeleton outline for the learner to study (NOT a full essay)"
    )
    grading_criteria: list[str] = Field(..., min_length=4)


# ─── Template 4: Idea Paraphrasing (Write) ────────────────────────────


class ParaphraseTarget(BaseModel):
    target_id: str
    paraphrase_style: ParaphraseStyle
    sample_paraphrase: str
    must_preserve: list[str] = Field(
        ..., min_length=1, max_length=5,
        description="Meaning elements that must NOT be lost in the paraphrase",
    )


class IdeaParaphrasingTask(GeneratedTaskBase):
    instructions: str
    original_sentence: str = Field(..., min_length=20, max_length=300)
    target_count: int = Field(default=3, ge=2, le=5)
    targets: list[ParaphraseTarget] = Field(..., min_length=2, max_length=5)
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 5: Bullets → Coherent Paragraph (Write) ─────────────────


class BulletPoint(BaseModel):
    bullet_id: str
    raw_idea: str = Field(
        ..., min_length=5, max_length=120,
        description="A loose, unordered idea fragment",
    )


class BulletsToParagraphTask(GeneratedTaskBase):
    instructions: str
    topic: str
    bullets: list[BulletPoint] = Field(..., min_length=4, max_length=8)
    target_paragraph_min_words: int = Field(..., ge=60, le=400)
    target_paragraph_max_words: int = Field(..., ge=80, le=500)
    required_connectors: list[str] = Field(..., min_length=3, max_length=8)
    sample_paragraph: str = Field(
        ..., description="A model paragraph weaving the bullets into coherent flow"
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 6: Listen — Identify Spoken Structure ───────────────────


class ListenStructureTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None,
        description="Filled later by TTS pipeline; null until audio is generated",
    )
    spoken_transcript: str = Field(
        ..., min_length=200, max_length=1000,
        description="What the speaker says — TTS will convert this to audio",
    )
    correct_pattern: StructurePattern
    pattern_options: list[StructurePattern] = Field(..., min_length=4, max_length=4)
    structural_cues: list[str] = Field(
        ..., min_length=2, max_length=6,
        description="Verbal cues a listener should catch (e.g. 'first…then…finally')",
    )
    explanation: str = Field(..., min_length=20, max_length=300)


# ─── Template 7: Speak — Storyboard Narration ─────────────────────────


class StoryboardScene(BaseModel):
    scene_number: int = Field(..., ge=1, le=6)
    scene_description: str = Field(
        ..., min_length=15, max_length=200,
        description="Plain-text description of what's in this scene/image",
    )
    suggested_focus: str = Field(
        ..., description="What the learner should mention about this scene"
    )


class StoryboardNarrationTask(GeneratedTaskBase):
    instructions: str
    story_theme: str
    scenes: list[StoryboardScene] = Field(..., min_length=3, max_length=6)
    required_tense: Literal["past_simple", "present_simple", "present_continuous"]
    required_connectors: list[str] = Field(
        ..., min_length=3, max_length=8,
        description="Story connectors the learner must use (then, suddenly, because, etc.)",
    )
    minimum_duration_seconds: int = Field(default=60, ge=30, le=180)
    sample_narration: str = Field(
        ..., description="A model narration (4–8 sentences) connecting the scenes"
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 8: Speak — Step-by-Step Explanation ─────────────────────


class StepByStepExplanationTask(GeneratedTaskBase):
    instructions: str
    process_topic: str = Field(
        ..., description="The thing to explain (e.g. 'how to make tea')"
    )
    expected_step_count: int = Field(..., ge=3, le=8)
    required_sequencing_words: list[str] = Field(
        ..., min_length=3, max_length=8,
        description="Words like 'first', 'next', 'then', 'finally' the learner must use",
    )
    minimum_duration_seconds: int = Field(default=60, ge=30, le=180)
    sample_explanation: str = Field(
        ..., description="A model explanation using the sequencing words"
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ═════════════════════════════════════════════════════════════════════
# LAYER 1 — TEMPLATE DEFINITIONS (loaded by the Task Selector at startup)
# ═════════════════════════════════════════════════════════════════════


THOUGHT_ORG_READ_PASSAGE_SUMMARIZATION_V1 = TaskTemplate(
    template_id="thought_org_read_passage_summarization_v1",
    sub_skill=SubSkill.THOUGHT_ORGANIZATION,
    activity=Activity.READ,
    task_type="passage_summarization",
    difficulty_range=(3, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
You are an English teacher creating a summarization exercise. The learner
will read a passage and write a short summary capturing the main idea
and key supporting points.

LEARNER PROFILE
- Sub-level: {sub_level}
- Topic of interest: {topic}

TASK
Create a passage and the summarization frame:
1. Passage length: {min_words}–{max_words} words
2. The passage MUST have ONE clear main idea + 2–4 supporting points
3. Use vocabulary appropriate to {vocab_level}
4. Provide the main idea (1 sentence)
5. List the key supporting points (2–4 bullets)
6. Provide a sample_summary in {summary_min}–{summary_max} sentences
7. Set summary_sentence_min={summary_min} and summary_sentence_max={summary_max}
8. Provide 3+ grading criteria covering: main_idea_captured, key_points_covered,
   conciseness, language_quality

Return ONLY valid JSON matching the PassageSummarizationTask schema.
No prose, no markdown fences.
""",
    output_model_name="PassageSummarizationTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "main_idea_captured": 0.40,
            "key_points_covered": 0.30,
            "conciseness": 0.20,
            "language_quality": 0.10,
        },
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "beginner": {
            "min_words": 150, "max_words": 220,
            "vocab_level": "basic",
            "summary_min": 2, "summary_max": 3,
        },
        "intermediate": {
            "min_words": 250, "max_words": 400,
            "vocab_level": "intermediate",
            "summary_min": 2, "summary_max": 4,
        },
        "advanced": {
            "min_words": 450, "max_words": 800,
            "vocab_level": "advanced",
            "summary_min": 3, "summary_max": 5,
        },
    },
)


THOUGHT_ORG_READ_STRUCTURE_ID_V1 = TaskTemplate(
    template_id="thought_org_read_structure_identification_v1",
    sub_skill=SubSkill.THOUGHT_ORGANIZATION,
    activity=Activity.READ,
    task_type="structure_identification",
    difficulty_range=(4, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a structure-identification exercise. The learner reads a passage
and identifies which organizational pattern the writer used.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick ONE structure pattern as the answer from this set: {focus_patterns}
2. Write a {min_words}–{max_words} word passage that CLEARLY follows that pattern
3. Embed 2–4 signal phrases inside the passage that hint at the structure
   (e.g. for problem_solution: "the issue is...", "one solution is...")
4. Provide exactly 4 distinct pattern options (the correct one + 3 plausible distractors)
5. Provide a 1–2 sentence explanation pointing out the giveaway signals

Return ONLY valid JSON matching the StructureIdentificationTask schema.
""",
    output_model_name="StructureIdentificationTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1.0 if correct_pattern selected, else 0.0",
        "passing_threshold": 1.0,
    },
    difficulty_modifiers={
        "intermediate": {
            "min_words": 180, "max_words": 280,
            "focus_patterns": (
                "intro_body_conclusion, chronological, "
                "sequential_steps, problem_solution"
            ),
        },
        "advanced": {
            "min_words": 280, "max_words": 550,
            "focus_patterns": (
                "all 9 patterns including compare_contrast, cause_effect, "
                "claim_evidence, general_to_specific, specific_to_general"
            ),
        },
    },
)


THOUGHT_ORG_WRITE_STRUCTURED_ESSAY_V1 = TaskTemplate(
    template_id="thought_org_write_structured_essay_v1",
    sub_skill=SubSkill.THOUGHT_ORGANIZATION,
    activity=Activity.WRITE,
    task_type="structured_essay",
    difficulty_range=(5, 10),
    estimated_time_minutes=15,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a structured-writing prompt. The learner writes a short essay that
must follow a specific organizational pattern.

LEARNER PROFILE
- Sub-level: {sub_level}
- Topic interest: {topic}

TASK
1. Pick a relatable, opinion-friendly essay_topic
   (career, study habits, technology, daily life, workplace, etc.)
2. Set required_structure to one of: {structure_patterns}
3. Set target_word_count_min={min_words} and target_word_count_max={max_words}
4. Define exactly {section_count} sections — for each provide:
   - section_name (one of: introduction, body_1, body_2, body_3, conclusion)
   - purpose (what the section accomplishes)
   - minimum_sentences (1–8)
   - suggested_focus (a 1-sentence content hint)
5. List 3–5 required transition connectors the learner must use
6. Provide a skeleton sample_outline (NOT a full essay — just headings + 1-line each)
7. Provide 4+ grading criteria: structure_match, transitions_used,
   idea_development, language_quality

Return ONLY valid JSON matching the StructuredEssayTask schema.
""",
    output_model_name="StructuredEssayTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "structure_match": 0.35,
            "transitions_used": 0.20,
            "idea_development": 0.25,
            "language_quality": 0.20,
        },
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "intermediate": {
            "min_words": 120, "max_words": 200,
            "section_count": 3,
            "structure_patterns": "intro_body_conclusion",
        },
        "advanced": {
            "min_words": 250, "max_words": 450,
            "section_count": 5,
            "structure_patterns": (
                "intro_body_conclusion, problem_solution, "
                "compare_contrast, cause_effect"
            ),
        },
    },
)


THOUGHT_ORG_WRITE_IDEA_PARAPHRASING_V1 = TaskTemplate(
    template_id="thought_org_write_idea_paraphrasing_v1",
    sub_skill=SubSkill.THOUGHT_ORGANIZATION,
    activity=Activity.WRITE,
    task_type="idea_paraphrasing",
    difficulty_range=(4, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create an idea-paraphrasing exercise. The learner re-expresses the SAME
idea in {target_count} different ways, each with a different style.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Provide ONE original_sentence (20–60 words) carrying a clear, complete idea
2. Set target_count={target_count}
3. Define {target_count} paraphrase targets — each with a DIFFERENT style from:
   more_formal, more_casual, more_concise, different_structure, different_vocabulary
4. For each target provide:
   - target_id (e.g. "t1", "t2")
   - paraphrase_style (one of the 5 styles above)
   - sample_paraphrase (a model answer that demonstrates the style)
   - must_preserve: 1–3 meaning elements the learner cannot drop
5. Provide 3+ grading_criteria: meaning_preserved, style_match,
   originality_vs_source, language_quality

Return ONLY valid JSON matching the IdeaParaphrasingTask schema.
""",
    output_model_name="IdeaParaphrasingTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "meaning_preserved": 0.45,
            "style_match": 0.30,
            "originality_vs_source": 0.25,
        },
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "intermediate": {"target_count": 2},
        "advanced": {"target_count": 4},
    },
)


THOUGHT_ORG_WRITE_BULLETS_TO_PARAGRAPH_V1 = TaskTemplate(
    template_id="thought_org_write_bullets_to_paragraph_v1",
    sub_skill=SubSkill.THOUGHT_ORGANIZATION,
    activity=Activity.WRITE,
    task_type="bullets_to_paragraph",
    difficulty_range=(3, 10),
    estimated_time_minutes=10,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a "bullets to paragraph" exercise. The learner gets a list of loose,
unordered ideas and must organize them into ONE coherent paragraph.

LEARNER PROFILE
- Sub-level: {sub_level}
- Topic interest: {topic}

TASK
1. Pick a topic relevant to the learner
2. Provide exactly {bullet_count} bullets — each a SHORT raw idea fragment
   (deliberately unordered, NOT in logical sequence)
3. Set target_paragraph_min_words={min_words} and target_paragraph_max_words={max_words}
4. List 3–5 required_connectors the learner must use
5. Provide a sample_paragraph that weaves all bullets into coherent flow
6. Provide 3+ grading_criteria: all_bullets_covered, logical_order,
   connectors_used, language_quality

Return ONLY valid JSON matching the BulletsToParagraphTask schema.
""",
    output_model_name="BulletsToParagraphTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "all_bullets_covered": 0.30,
            "logical_order": 0.30,
            "connectors_used": 0.20,
            "language_quality": 0.20,
        },
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "beginner": {"bullet_count": 4, "min_words": 60, "max_words": 100},
        "intermediate": {"bullet_count": 6, "min_words": 100, "max_words": 180},
        "advanced": {"bullet_count": 8, "min_words": 180, "max_words": 320},
    },
)


THOUGHT_ORG_LISTEN_STRUCTURE_V1 = TaskTemplate(
    template_id="thought_org_listen_structure_v1",
    sub_skill=SubSkill.THOUGHT_ORGANIZATION,
    activity=Activity.LISTEN,
    task_type="identify_spoken_structure",
    difficulty_range=(5, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Generate a spoken passage (as a transcript) for the learner to listen to.
After listening, the learner identifies the speaker's organizational pattern.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick ONE structure pattern from: {focus_patterns}
2. Write a spoken_transcript of {min_words}–{max_words} words that follows the pattern
3. Make the structural cues HEARABLE — use clear verbal markers
   (e.g. "first...second...finally", "the problem is...the solution is...")
4. Provide exactly 4 pattern_options (correct + 3 plausible distractors)
5. Provide 2–4 structural_cues — exact phrases from the transcript that signal the pattern
6. Set audio_url to null (TTS pipeline fills it later)
7. Provide a 1–2 sentence explanation pointing out the cues

Return ONLY valid JSON matching the ListenStructureTask schema.
""",
    output_model_name="ListenStructureTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1.0 if correct_pattern selected, else 0.0",
        "passing_threshold": 1.0,
    },
    difficulty_modifiers={
        "intermediate": {
            "min_words": 200, "max_words": 320,
            "focus_patterns": (
                "chronological, sequential_steps, problem_solution"
            ),
        },
        "advanced": {
            "min_words": 320, "max_words": 600,
            "focus_patterns": (
                "compare_contrast, cause_effect, claim_evidence, "
                "general_to_specific"
            ),
        },
    },
)


THOUGHT_ORG_SPEAK_STORYBOARD_V1 = TaskTemplate(
    template_id="thought_org_speak_storyboard_v1",
    sub_skill=SubSkill.THOUGHT_ORGANIZATION,
    activity=Activity.SPEAK,
    task_type="storyboard_narration",
    difficulty_range=(3, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a storyboard narration task. The learner sees {scene_count} scene
descriptions (acting as story-image prompts) and narrates a connected
story that flows naturally between them.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick a relatable story_theme (a day at work, a trip, a small conflict, etc.)
2. Define exactly {scene_count} scenes — each with:
   - scene_number (1, 2, 3, ...)
   - scene_description (1–2 sentences describing what's "in the picture")
   - suggested_focus (a hint about what the learner could mention)
3. Pick required_tense: past_simple, present_simple, or present_continuous
4. List 3–5 required_connectors (then, suddenly, because, after that, finally)
5. Set minimum_duration_seconds={duration}
6. Write a sample_narration (4–8 sentences) showing the scenes connected
7. Provide 3+ grading_criteria: story_coherence, scene_coverage,
   tense_consistency, connectors_used

Return ONLY valid JSON matching the StoryboardNarrationTask schema.
""",
    output_model_name="StoryboardNarrationTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "story_coherence": 0.35,
            "scene_coverage": 0.25,
            "tense_consistency": 0.20,
            "connectors_used": 0.20,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "beginner": {"scene_count": 3, "duration": 45},
        "intermediate": {"scene_count": 4, "duration": 60},
        "advanced": {"scene_count": 5, "duration": 90},
    },
)


THOUGHT_ORG_SPEAK_STEP_BY_STEP_V1 = TaskTemplate(
    template_id="thought_org_speak_step_by_step_v1",
    sub_skill=SubSkill.THOUGHT_ORGANIZATION,
    activity=Activity.SPEAK,
    task_type="step_by_step_explanation",
    difficulty_range=(3, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a step-by-step explanation task. The learner explains a process in
clear sequential steps using sequencing words.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick a process_topic the learner is likely to know
   (making tea, getting ready for work, sending an email,
    booking a ticket, cooking a simple dish, etc.)
2. Set expected_step_count={step_count}
3. List 3–5 required_sequencing_words (first, next, then, after that, finally)
4. Set minimum_duration_seconds={duration}
5. Write a sample_explanation that uses the sequencing words and covers the steps
6. Provide 3+ grading_criteria: step_clarity, sequencing_words_used,
   completeness, fluency

Return ONLY valid JSON matching the StepByStepExplanationTask schema.
""",
    output_model_name="StepByStepExplanationTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "step_clarity": 0.35,
            "sequencing_words_used": 0.25,
            "completeness": 0.25,
            "fluency": 0.15,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "beginner": {"step_count": 3, "duration": 45},
        "intermediate": {"step_count": 5, "duration": 60},
        "advanced": {"step_count": 7, "duration": 90},
    },
)


# ═════════════════════════════════════════════════════════════════════
# REGISTRY — every template grouped for the Task Selector
# ═════════════════════════════════════════════════════════════════════


THOUGHT_ORG_TEMPLATES: list[TaskTemplate] = [
    THOUGHT_ORG_READ_PASSAGE_SUMMARIZATION_V1,
    THOUGHT_ORG_READ_STRUCTURE_ID_V1,
    THOUGHT_ORG_WRITE_STRUCTURED_ESSAY_V1,
    THOUGHT_ORG_WRITE_IDEA_PARAPHRASING_V1,
    THOUGHT_ORG_WRITE_BULLETS_TO_PARAGRAPH_V1,
    THOUGHT_ORG_LISTEN_STRUCTURE_V1,
    THOUGHT_ORG_SPEAK_STORYBOARD_V1,
    THOUGHT_ORG_SPEAK_STEP_BY_STEP_V1,
]


# Map of LLM-output Pydantic models — used by the validator to pick the
# right schema based on `template.output_model_name`.
THOUGHT_ORG_OUTPUT_MODELS = {
    "PassageSummarizationTask": PassageSummarizationTask,
    "StructureIdentificationTask": StructureIdentificationTask,
    "StructuredEssayTask": StructuredEssayTask,
    "IdeaParaphrasingTask": IdeaParaphrasingTask,
    "BulletsToParagraphTask": BulletsToParagraphTask,
    "ListenStructureTask": ListenStructureTask,
    "StoryboardNarrationTask": StoryboardNarrationTask,
    "StepByStepExplanationTask": StepByStepExplanationTask,
}
