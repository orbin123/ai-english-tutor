"""
Vocabulary & Word Choice — Task Templates.

Sub-Skill #2 of 7. Covers vocabulary range, contextual vocabulary,
and conciseness across all 4 core activities.

TEMPLATES IN THIS FILE
──────────────────────
Read    │ 1. Word-meaning match
        │ 2. Context MCQ (pick the word that fits the sentence)
Write   │ 3. Word upgrade (replace simple → advanced)
        │ 4. Paraphrase using target words
        │ 5. Conciseness rewrite (cut wordiness)
Listen  │ 6. Identify vocabulary from audio
Speak   │ 7. Use given words in speech
        │ 8. Topic explanation with target vocabulary

Total: 8 Vocabulary templates.
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
# SHARED LABELS — used across multiple vocabulary templates
# ═════════════════════════════════════════════════════════════════════


# CEFR-aligned vocabulary tiers — useful for tagging words by difficulty
VocabTier = Literal["A1", "A2", "B1", "B2", "C1", "C2"]


# Domain tags — helps the LLM stay on-topic for a learner's career interest
VocabDomain = Literal[
    "general", "business", "technology", "academic",
    "interview", "daily_conversation", "travel", "healthcare",
]


# Part-of-speech tag (used in word-meaning match)
PartOfSpeech = Literal["noun", "verb", "adjective", "adverb", "phrase", "idiom"]


# ═════════════════════════════════════════════════════════════════════
# LAYER 2 — PYDANTIC MODELS (validate LLM output for each template)
# ═════════════════════════════════════════════════════════════════════


# ─── Template 1: Word-Meaning Match ───────────────────────────────────


class WordMeaningPair(BaseModel):
    pair_id: str = Field(..., description="e.g. 'p1', 'p2'")
    word: str
    correct_meaning: str
    distractor_meanings: list[str] = Field(..., min_length=3, max_length=3)
    part_of_speech: PartOfSpeech
    vocab_tier: VocabTier
    example_sentence: str = Field(..., description="Word used in a natural sentence")


class WordMeaningMatchTask(GeneratedTaskBase):
    instructions: str
    pairs: list[WordMeaningPair] = Field(..., min_length=5, max_length=10)
    domain: VocabDomain


# ─── Template 2: Context MCQ ──────────────────────────────────────────


class ContextMCQItem(BaseModel):
    item_id: str
    sentence_with_blank: str = Field(..., description="Sentence with ___ to fill")
    correct_word: str
    options: list[str] = Field(..., min_length=4, max_length=4)
    explanation: str = Field(
        ..., description="Why the correct word fits and others don't"
    )
    confusion_type: Literal[
        "synonym_nuance",      # words mean similar but feel different
        "collocation",          # only this word pairs naturally
        "register",             # formal vs informal context
        "domain_specific",      # technical/business word
    ]


class ContextMCQTask(GeneratedTaskBase):
    instructions: str
    items: list[ContextMCQItem] = Field(..., min_length=5, max_length=8)


# ─── Template 3: Word Upgrade (Replace Simple → Advanced) ─────────────


class WordUpgradeItem(BaseModel):
    item_id: str
    original_sentence: str = Field(..., description="Sentence using a basic word")
    target_word_to_replace: str
    sample_upgraded_sentence: str
    acceptable_replacements: list[str] = Field(..., min_length=2, max_length=5)
    register_must_match: bool = Field(
        True, description="True if the upgrade should keep the same formality level"
    )


class WordUpgradeTask(GeneratedTaskBase):
    instructions: str
    items: list[WordUpgradeItem] = Field(..., min_length=4, max_length=8)
    target_tier: VocabTier = Field(..., description="The vocabulary tier to upgrade to")


# ─── Template 4: Paraphrase Using Target Words ────────────────────────


class ParaphraseItem(BaseModel):
    item_id: str
    original_sentence: str
    must_use_words: list[str] = Field(..., min_length=2, max_length=4)
    sample_paraphrase: str
    grading_criteria: list[str] = Field(..., min_length=2)


class VocabParaphraseTask(GeneratedTaskBase):
    instructions: str
    items: list[ParaphraseItem] = Field(..., min_length=3, max_length=5)


# ─── Template 5: Conciseness Rewrite ──────────────────────────────────


class ConcisenessItem(BaseModel):
    item_id: str
    wordy_sentence: str
    original_word_count: int
    target_max_words: int
    sample_concise_version: str
    redundant_phrases_to_cut: list[str] = Field(..., min_length=1)


class ConcisenessRewriteTask(GeneratedTaskBase):
    instructions: str
    items: list[ConcisenessItem] = Field(..., min_length=3, max_length=6)


# ─── Template 6: Listen — Identify Vocabulary from Audio ──────────────


class AudioVocabItem(BaseModel):
    item_id: str
    audio_transcript: str = Field(..., description="What is spoken in the audio")
    target_word: str = Field(..., description="The vocabulary word to identify")
    correct_meaning: str
    distractor_meanings: list[str] = Field(..., min_length=3, max_length=3)


class ListenIdentifyVocabTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled later by TTS pipeline"
    )
    items: list[AudioVocabItem] = Field(..., min_length=3, max_length=6)


# ─── Template 7: Speak — Use Given Words in Speech ────────────────────


class SpeakWithWordsTask(GeneratedTaskBase):
    instructions: str
    target_words: list[str] = Field(..., min_length=4, max_length=8)
    speaking_prompt: str = Field(..., description="Topic the user must speak about")
    minimum_duration_seconds: int = Field(default=60, ge=30, le=180)
    minimum_words_to_use: int = Field(
        ..., description="How many target words MUST appear in the response"
    )
    grading_criteria: list[str] = Field(..., min_length=3)
    sample_response: str


# ─── Template 8: Speak — Topic Explanation with Target Vocabulary ─────


class TopicExplanationTask(GeneratedTaskBase):
    instructions: str
    topic: str = Field(..., description="The topic to explain")
    domain: VocabDomain
    suggested_vocabulary: list[str] = Field(..., min_length=5, max_length=10)
    minimum_duration_seconds: int = Field(default=90, ge=60, le=240)
    structure_guidance: list[str] = Field(
        ...,
        description="e.g. ['Define the term', 'Give an example', 'State the impact']",
        min_length=2,
    )
    grading_criteria: list[str] = Field(..., min_length=3)


# ═════════════════════════════════════════════════════════════════════
# LAYER 1 — TEMPLATE DEFINITIONS
# ═════════════════════════════════════════════════════════════════════


VOCAB_READ_WORD_MEANING_MATCH_V1 = TaskTemplate(
    template_id="vocab_read_word_meaning_match_v1",
    sub_skill=SubSkill.VOCABULARY,
    activity=Activity.READ,
    task_type="word_meaning_match",
    difficulty_range=(1, 10),
    estimated_time_minutes=4,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
You are an English vocabulary teacher. Generate a word-meaning matching exercise.

LEARNER PROFILE
- Sub-level: {sub_level} (1=A1, 10=C2)
- Career interest / domain: {domain}
- Already-known words to avoid: {known_words}

TASK
Generate {pair_count} word-meaning pairs:
1. Each word must be at vocabulary tier {target_tier}
2. Each word must be relevant to the {domain} domain
3. Provide 1 correct meaning + 3 plausible distractor meanings
4. Distractors should be wrong but believable (not random nonsense)
5. Tag each word with its part of speech
6. Include a natural example sentence using the word

Avoid words from the known_words list to keep the exercise fresh.

Return ONLY valid JSON matching the WordMeaningMatchTask schema.
""",
    output_model_name="WordMeaningMatchTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct match, normalized to 0-1",
        "passing_threshold": 0.7,
        "feedback_triggers": {
            "below_0.5": "explain meaning of every wrong word + add to learning list",
            "0.5_to_0.7": "explain only wrong ones",
            "above_0.7": "brief reinforcement + introduce 1 advanced synonym",
        },
    },
    difficulty_modifiers={
        "beginner": {"pair_count": 5, "target_tier": "A2"},
        "intermediate": {"pair_count": 7, "target_tier": "B1"},
        "advanced": {"pair_count": 10, "target_tier": "C1"},
    },
)


VOCAB_READ_CONTEXT_MCQ_V1 = TaskTemplate(
    template_id="vocab_read_context_mcq_v1",
    sub_skill=SubSkill.VOCABULARY,
    activity=Activity.READ,
    task_type="context_mcq",
    difficulty_range=(2, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a context-based vocabulary MCQ. The learner picks which word
fits naturally in a sentence — testing CONTEXTUAL usage, not just meaning.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
Generate {item_count} sentences with one word missing:
1. Provide 4 options that ALL mean similar things on the surface
2. Only ONE should fit perfectly in context (collocation, register, or nuance)
3. The other 3 should be PLAUSIBLE wrong answers (this is critical)
4. Tag each item with its confusion_type:
   - synonym_nuance, collocation, register, or domain_specific
5. Include a clear explanation of why the right word fits

Return ONLY valid JSON matching the ContextMCQTask schema.
""",
    output_model_name="ContextMCQTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct choice",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "beginner": {"item_count": 5},
        "intermediate": {"item_count": 7},
        "advanced": {"item_count": 8},
    },
)


VOCAB_WRITE_WORD_UPGRADE_V1 = TaskTemplate(
    template_id="vocab_write_word_upgrade_v1",
    sub_skill=SubSkill.VOCABULARY,
    activity=Activity.WRITE,
    task_type="word_upgrade",
    difficulty_range=(3, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a word-upgrade exercise. The learner replaces a basic word in a
sentence with a more sophisticated synonym while keeping the meaning intact.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}
- Target vocabulary tier to push toward: {target_tier}

TASK
Generate {item_count} sentences:
1. Each sentence uses a BASIC word (e.g. "good", "bad", "very", "happy")
2. Mark the target_word_to_replace clearly
3. Provide a sample upgraded sentence using a {target_tier}-tier word
4. List 2–5 acceptable upgraded alternatives
5. Set register_must_match=true so the upgrade keeps the same formality

Return ONLY valid JSON matching the WordUpgradeTask schema.
""",
    output_model_name="WordUpgradeTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "synonym_validity": 0.4,
            "tier_uplift": 0.3,
            "register_match": 0.2,
            "natural_flow": 0.1,
        },
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "beginner": {"item_count": 4, "target_tier": "B1"},
        "intermediate": {"item_count": 6, "target_tier": "B2"},
        "advanced": {"item_count": 8, "target_tier": "C1"},
    },
)


VOCAB_WRITE_PARAPHRASE_V1 = TaskTemplate(
    template_id="vocab_write_paraphrase_v1",
    sub_skill=SubSkill.VOCABULARY,
    activity=Activity.WRITE,
    task_type="paraphrase_with_target_words",
    difficulty_range=(4, 10),
    estimated_time_minutes=10,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create paraphrasing exercises that FORCE the learner to use specific
target words — building active recall, not just passive recognition.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
Generate {item_count} items. For each:
1. Provide an original sentence (using BASIC words)
2. List 2–4 target words the paraphrase MUST include
3. Target words should be at sub-level {sub_level}'s next-tier
4. Provide a sample paraphrase that uses every target word naturally
5. List 2–3 grading criteria for the AI evaluator

Return ONLY valid JSON matching the VocabParaphraseTask schema.
""",
    output_model_name="VocabParaphraseTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "all_target_words_used": 0.4,
            "meaning_preserved": 0.3,
            "natural_phrasing": 0.2,
            "grammar": 0.1,
        },
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "intermediate": {"item_count": 3},
        "advanced": {"item_count": 5},
    },
)


VOCAB_WRITE_CONCISENESS_V1 = TaskTemplate(
    template_id="vocab_write_conciseness_v1",
    sub_skill=SubSkill.VOCABULARY,
    activity=Activity.WRITE,
    task_type="conciseness_rewrite",
    difficulty_range=(4, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create conciseness exercises. The learner rewrites wordy sentences using
fewer words — directly tackling the conciseness dimension of vocabulary.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
Generate {item_count} wordy sentences typical of non-native writers:
1. Each sentence contains REDUNDANT phrases (e.g. "due to the fact that" → "because")
2. Mark the original_word_count
3. Set target_max_words (~50-60% of original)
4. Provide a sample concise version
5. List the redundant phrases the learner should cut

Common patterns to use as inspiration:
- "in order to" → "to"
- "at this point in time" → "now"
- "make a decision" → "decide"
- "the reason is because" → "because"

Return ONLY valid JSON matching the ConcisenessRewriteTask schema.
""",
    output_model_name="ConcisenessRewriteTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "word_count_target_met": 0.3,
            "meaning_preserved": 0.4,
            "redundancies_removed": 0.3,
        },
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "intermediate": {"item_count": 3},
        "advanced": {"item_count": 5},
    },
)


VOCAB_LISTEN_IDENTIFY_VOCAB_V1 = TaskTemplate(
    template_id="vocab_listen_identify_vocab_v1",
    sub_skill=SubSkill.VOCABULARY,
    activity=Activity.LISTEN,
    task_type="identify_vocab_from_audio",
    difficulty_range=(3, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a listening vocabulary task. The learner hears a sentence containing
a target word and must pick the correct meaning.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
Generate {item_count} short audio transcripts:
1. Each is a 1–2 sentence dialogue or statement
2. Each contains ONE target vocabulary word at tier {target_tier}
3. The word must be CLEARLY embedded in context (not isolated)
4. Provide the correct meaning + 3 plausible distractor meanings
5. Set audio_url to null (TTS pipeline fills it later)

Return ONLY valid JSON matching the ListenIdentifyVocabTask schema.
""",
    output_model_name="ListenIdentifyVocabTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct meaning chosen",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "beginner": {"item_count": 4, "target_tier": "A2"},
        "intermediate": {"item_count": 5, "target_tier": "B1"},
        "advanced": {"item_count": 6, "target_tier": "C1"},
    },
)


VOCAB_SPEAK_USE_WORDS_V1 = TaskTemplate(
    template_id="vocab_speak_use_words_v1",
    sub_skill=SubSkill.VOCABULARY,
    activity=Activity.SPEAK,
    task_type="speak_with_target_words",
    difficulty_range=(3, 10),
    estimated_time_minutes=5,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a speaking task that forces active vocabulary use. The learner
speaks for a duration and must use specific target words naturally.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}
- Weak vocabulary areas: {weak_areas}

TASK
1. Pick {word_count} target words at tier {target_tier}, relevant to {domain}
2. Provide a natural speaking prompt where these words could fit
3. Set minimum duration ({duration} seconds)
4. Specify minimum_words_to_use ({min_words_to_use} of the target words)
5. Provide a sample 4–6 sentence response that uses every target word
6. List 3 grading criteria

Return ONLY valid JSON matching the SpeakWithWordsTask schema.
""",
    output_model_name="SpeakWithWordsTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "target_words_used": 0.4,
            "natural_usage": 0.3,
            "fluency": 0.2,
            "grammar": 0.1,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "beginner": {"duration": 30, "word_count": 4, "min_words_to_use": 3, "target_tier": "A2"},
        "intermediate": {"duration": 60, "word_count": 5, "min_words_to_use": 4, "target_tier": "B1"},
        "advanced": {"duration": 90, "word_count": 6, "min_words_to_use": 5, "target_tier": "C1"},
    },
)


VOCAB_SPEAK_TOPIC_EXPLANATION_V1 = TaskTemplate(
    template_id="vocab_speak_topic_explanation_v1",
    sub_skill=SubSkill.VOCABULARY,
    activity=Activity.SPEAK,
    task_type="topic_explanation",
    difficulty_range=(5, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a domain-vocabulary speaking task. The learner explains a topic
using domain-appropriate vocabulary — building career-focused fluency.

LEARNER PROFILE
- Sub-level: {sub_level}
- Career domain: {domain}
- Weak vocabulary areas: {weak_areas}

TASK
1. Pick a topic relevant to the {domain} domain
   (e.g. for business: "team conflict resolution"; for tech: "API rate limiting")
2. Suggest {vocab_count} domain-appropriate vocabulary words
3. Set minimum duration ({duration} seconds)
4. Provide structure guidance — 2–4 bullet points the learner should cover
   (e.g. "Define the concept", "Give an example", "State why it matters")
5. List 3 grading criteria (vocabulary usage, structure adherence, clarity)

Return ONLY valid JSON matching the TopicExplanationTask schema.
""",
    output_model_name="TopicExplanationTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "domain_vocab_used": 0.35,
            "structure_followed": 0.25,
            "clarity": 0.2,
            "fluency": 0.2,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "intermediate": {"duration": 90, "vocab_count": 6},
        "advanced": {"duration": 120, "vocab_count": 8},
    },
)


# ═════════════════════════════════════════════════════════════════════
# REGISTRY
# ═════════════════════════════════════════════════════════════════════


VOCABULARY_TEMPLATES: list[TaskTemplate] = [
    VOCAB_READ_WORD_MEANING_MATCH_V1,
    VOCAB_READ_CONTEXT_MCQ_V1,
    VOCAB_WRITE_WORD_UPGRADE_V1,
    VOCAB_WRITE_PARAPHRASE_V1,
    VOCAB_WRITE_CONCISENESS_V1,
    VOCAB_LISTEN_IDENTIFY_VOCAB_V1,
    VOCAB_SPEAK_USE_WORDS_V1,
    VOCAB_SPEAK_TOPIC_EXPLANATION_V1,
]


VOCABULARY_OUTPUT_MODELS = {
    "WordMeaningMatchTask": WordMeaningMatchTask,
    "ContextMCQTask": ContextMCQTask,
    "WordUpgradeTask": WordUpgradeTask,
    "VocabParaphraseTask": VocabParaphraseTask,
    "ConcisenessRewriteTask": ConcisenessRewriteTask,
    "ListenIdentifyVocabTask": ListenIdentifyVocabTask,
    "SpeakWithWordsTask": SpeakWithWordsTask,
    "TopicExplanationTask": TopicExplanationTask,
}
