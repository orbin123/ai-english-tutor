"""
Task template library for LingosAI.

Usage:
    from app.tasks.schemas import GRAMMAR_TEMPLATES, ALL_TEMPLATES
    from app.tasks.schemas import SubSkill, Activity, ScoringMethod
    from app.tasks.schemas import FillInBlanksTask  # for validating LLM output

As we add more sub-skills (vocab, pronunciation, etc.), each gets its own
*_templates.py file. We extend ALL_TEMPLATES + ALL_OUTPUT_MODELS here.
"""

from app.tasks.schemas.base import (
    Activity,
    DifficultyTier,
    GeneratedTaskBase,
    ScoringMethod,
    SubSkill,
    TaskTemplate,
    difficulty_tier_for_sublevel,
)

# ─── Sub-Skill #1: Grammar ────────────────────────────────────────────
from app.tasks.schemas.grammar_templates import (
    AudioErrorItem,
    BlankItem,
    CombinerItem,
    CorrectionItem,
    ErrorCorrectionTask,
    ErrorItem,
    ErrorSpottingTask,
    FillInBlanksTask,
    GrammarRule,
    ListenGrammarErrorTask,
    SentenceTransformationTask,
    SpeakSentenceCombinersTask,
    SpeakWithTenseTask,
    TransformItem,
    VoiceConversionItem,
    VoiceConversionTask,
    GRAMMAR_OUTPUT_MODELS,
    GRAMMAR_TEMPLATES,
)

# ─── Sub-Skill #2: Vocabulary ─────────────────────────────────────────
from app.tasks.schemas.vocabulary_templates import (
    PartOfSpeech,
    VocabDomain,
    VocabTier,
    AudioVocabItem,
    ConcisenessItem,
    ConcisenessRewriteTask,
    ContextMCQItem,
    ContextMCQTask,
    ListenIdentifyVocabTask,
    ParaphraseItem,
    SpeakWithWordsTask,
    TopicExplanationTask,
    VocabParaphraseTask,
    WordMeaningMatchTask,
    WordMeaningPair,
    WordUpgradeItem,
    WordUpgradeTask,
    VOCABULARY_OUTPUT_MODELS,
    VOCABULARY_TEMPLATES,
)

# ─── Sub-Skill #3: Pronunciation ──────────────────────────────────────
from app.tasks.schemas.pronunciation_templates import (
    ReferenceAccent,
    StressPosition,
    TargetPhoneme,
    ConnectedSpeechItem,
    ConnectedSpeechTask,
    IdentifyMispronouncedTask,
    MinimalPair,
    MinimalPairsDrillTask,
    MispronouncedItem,
    PhonemeAwarenessItem,
    PhonemeAwarenessTask,
    ReadAloudTask,
    ShadowAudioTask,
    StressPatternItem,
    StressPatternTask,
    PRONUNCIATION_OUTPUT_MODELS,
    PRONUNCIATION_TEMPLATES,
)

# ─── Sub-Skill #4: Fluency ────────────────────────────────────────────
from app.tasks.schemas.fluency_templates import (
    FillerWord,
    ReadingSpeedTier,
    SmallTalkScenario,
    ContinuousTalkingTask,
    CurveballQATask,
    CurveballQuestion,
    RandomTopicTask,
    SelfCorrectionDrillTask,
    SelfCorrectionItem,
    ShadowingExerciseTask,
    SmallTalkExchange,
    SmallTalkSimulationTask,
    SpeedReadingTask,
    TimedWritingTask,
    FLUENCY_OUTPUT_MODELS,
    FLUENCY_TEMPLATES,
)

# ─── Sub-Skill #5: Thought Organization & Expression ──────────────────
from app.tasks.schemas.thought_organization_templates import (
    EssaySectionName,
    ParaphraseStyle,
    StructurePattern,
    BulletPoint,
    BulletsToParagraphTask,
    EssaySection,
    IdeaParaphrasingTask,
    ListenStructureTask,
    ParaphraseTarget,
    PassageSummarizationTask,
    StepByStepExplanationTask,
    StoryboardNarrationTask,
    StoryboardScene,
    StructureIdentificationTask,
    StructuredEssayTask,
    THOUGHT_ORG_OUTPUT_MODELS,
    THOUGHT_ORG_TEMPLATES,
)

# ─── Sub-Skill #6: Listening & Comprehension ──────────────────────────
from app.tasks.schemas.listening_templates import (
    AudioGenre,
    ComprehensionQuestionType,
    TrueFalseNotGiven,
    AudioMCQItem,
    AudioMCQTask,
    AudioShortAnswerItem,
    ClozeBlank,
    ClozeListeningTask,
    ComprehensionMCQItem,
    DictationSegment,
    DictationTask,
    InferenceListeningTask,
    InferenceQuestion,
    ReadingComprehensionMCQTask,
    RetellWhatYouHeardTask,
    TFNGStatement,
    TrueFalseNotGivenTask,
    WriteAnswersFromAudioTask,
    LISTENING_OUTPUT_MODELS,
    LISTENING_TEMPLATES,
)

# ─── Sub-Skill #7: Tone & Social Awareness ──────────────────────────────
from app.tasks.schemas.tone_templates import (
    Register,
    SocialScenario,
    ToneLabel,
    AssertivenessChallenge,
    AssertivenessDrillTask,
    DetectSpeakerToneTask,
    DialogueLine,
    MessageScenarioItem,
    MessageToScenarioTask,
    RegisterConversionItem,
    RegisterConversionTask,
    RegisterMismatchTask,
    RoleplayScenarioTask,
    RoleplayTurn,
    SpeakerToneItem,
    ToneIdentificationItem,
    ToneIdentificationTask,
    ToneResponseTask,
    TONE_OUTPUT_MODELS,
    TONE_TEMPLATES,
)


# ─────────────────────────────────────────────────────────────────────
# Aggregate registries — extend these as more sub-skills are added
# ─────────────────────────────────────────────────────────────────────


ALL_TEMPLATES: list[TaskTemplate] = [
    *GRAMMAR_TEMPLATES,
    *VOCABULARY_TEMPLATES,
    *PRONUNCIATION_TEMPLATES,
    *FLUENCY_TEMPLATES,
    *THOUGHT_ORG_TEMPLATES,
    *LISTENING_TEMPLATES,
    *TONE_TEMPLATES,
]

ALL_OUTPUT_MODELS: dict[str, type[GeneratedTaskBase]] = {
    **GRAMMAR_OUTPUT_MODELS,
    **VOCABULARY_OUTPUT_MODELS,
    **PRONUNCIATION_OUTPUT_MODELS,
    **FLUENCY_OUTPUT_MODELS,
    **THOUGHT_ORG_OUTPUT_MODELS,
    **LISTENING_OUTPUT_MODELS,
    **TONE_OUTPUT_MODELS,
}


# ─────────────────────────────────────────────────────────────────────
# Helpers used by the Task Generator + Selector
# ─────────────────────────────────────────────────────────────────────


def get_templates_for(
    sub_skill: SubSkill, activity: Activity | None = None
) -> list[TaskTemplate]:
    """Return all templates matching a sub-skill, optionally filtered by activity."""
    matches = [t for t in ALL_TEMPLATES if t.sub_skill == sub_skill]
    if activity is not None:
        matches = [t for t in matches if t.activity == activity]
    return matches


def get_template_by_id(template_id: str) -> TaskTemplate | None:
    """Look up a single template by its stable ID."""
    for tpl in ALL_TEMPLATES:
        if tpl.template_id == template_id:
            return tpl
    return None


def get_output_model(model_name: str) -> type[GeneratedTaskBase] | None:
    """Get the Pydantic class used to validate an LLM response."""
    return ALL_OUTPUT_MODELS.get(model_name)


__all__ = [
    # Enums + shared labels
    "SubSkill", "Activity", "ScoringMethod", "DifficultyTier",
    "GrammarRule",
    "VocabTier", "VocabDomain", "PartOfSpeech",
    "TargetPhoneme", "ReferenceAccent", "StressPosition",
    "FillerWord", "ReadingSpeedTier", "SmallTalkScenario",
    "StructurePattern", "ParaphraseStyle", "EssaySectionName",
    "ComprehensionQuestionType", "AudioGenre", "TrueFalseNotGiven",
    "Register", "ToneLabel", "SocialScenario",
    # Base classes
    "TaskTemplate", "GeneratedTaskBase",
    # Helpers
    "difficulty_tier_for_sublevel",
    "get_templates_for", "get_template_by_id", "get_output_model",
    # Registries
    "ALL_TEMPLATES", "ALL_OUTPUT_MODELS",
    "GRAMMAR_TEMPLATES", "GRAMMAR_OUTPUT_MODELS",
    "VOCABULARY_TEMPLATES", "VOCABULARY_OUTPUT_MODELS",
    "PRONUNCIATION_TEMPLATES", "PRONUNCIATION_OUTPUT_MODELS",
    "FLUENCY_TEMPLATES", "FLUENCY_OUTPUT_MODELS",
    "THOUGHT_ORG_TEMPLATES", "THOUGHT_ORG_OUTPUT_MODELS",
    "LISTENING_TEMPLATES", "LISTENING_OUTPUT_MODELS",
    "TONE_TEMPLATES", "TONE_OUTPUT_MODELS",
    # Grammar Pydantic models
    "FillInBlanksTask", "BlankItem",
    "ErrorSpottingTask", "ErrorItem",
    "SentenceTransformationTask", "TransformItem",
    "VoiceConversionTask", "VoiceConversionItem",
    "ErrorCorrectionTask", "CorrectionItem",
    "ListenGrammarErrorTask", "AudioErrorItem",
    "SpeakWithTenseTask",
    "SpeakSentenceCombinersTask", "CombinerItem",
    # Vocabulary Pydantic models
    "WordMeaningMatchTask", "WordMeaningPair",
    "ContextMCQTask", "ContextMCQItem",
    "WordUpgradeTask", "WordUpgradeItem",
    "VocabParaphraseTask", "ParaphraseItem",
    "ConcisenessRewriteTask", "ConcisenessItem",
    "ListenIdentifyVocabTask", "AudioVocabItem",
    "SpeakWithWordsTask",
    "TopicExplanationTask",
    # Pronunciation Pydantic models
    "PhonemeAwarenessTask", "PhonemeAwarenessItem",
    "IdentifyMispronouncedTask", "MispronouncedItem",
    "StressPatternTask", "StressPatternItem",
    "ReadAloudTask",
    "MinimalPairsDrillTask", "MinimalPair",
    "ShadowAudioTask",
    "ConnectedSpeechTask", "ConnectedSpeechItem",
    # Fluency Pydantic models
    "SpeedReadingTask",
    "TimedWritingTask",
    "ShadowingExerciseTask",
    "RandomTopicTask",
    "ContinuousTalkingTask",
    "SmallTalkSimulationTask", "SmallTalkExchange",
    "CurveballQATask", "CurveballQuestion",
    "SelfCorrectionDrillTask", "SelfCorrectionItem",
    # Thought Organization Pydantic models
    "PassageSummarizationTask",
    "StructureIdentificationTask",
    "StructuredEssayTask", "EssaySection",
    "IdeaParaphrasingTask", "ParaphraseTarget",
    "BulletsToParagraphTask", "BulletPoint",
    "ListenStructureTask",
    "StoryboardNarrationTask", "StoryboardScene",
    "StepByStepExplanationTask",
    # Listening Pydantic models
    "ReadingComprehensionMCQTask", "ComprehensionMCQItem",
    "TrueFalseNotGivenTask", "TFNGStatement",
    "WriteAnswersFromAudioTask", "AudioShortAnswerItem",
    "AudioMCQTask", "AudioMCQItem",
    "ClozeListeningTask", "ClozeBlank",
    "DictationTask", "DictationSegment",
    "InferenceListeningTask", "InferenceQuestion",
    "RetellWhatYouHeardTask",
    # Tone Pydantic models
    "ToneIdentificationTask", "ToneIdentificationItem",
    "MessageToScenarioTask", "MessageScenarioItem",
    "RegisterConversionTask", "RegisterConversionItem",
    "ToneResponseTask",
    "DetectSpeakerToneTask", "SpeakerToneItem",
    "RegisterMismatchTask", "DialogueLine",
    "RoleplayScenarioTask", "RoleplayTurn",
    "AssertivenessDrillTask", "AssertivenessChallenge",
]
