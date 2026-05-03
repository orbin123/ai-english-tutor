"""
Pronunciation & Speech Clarity — Task Templates.

Sub-Skill #3 of 7. Covers pronunciation accuracy, intonation/stress patterns,
and cluttering/clarity across Read, Listen, and Speak activities.

NOTE: This sub-skill relies heavily on external speech APIs:
- Whisper (speech-to-text)
- Azure Speech (phoneme-level pronunciation assessment + stress analysis)
- ElevenLabs (TTS for reference audio + shadowing)

Write activity is intentionally excluded — pronunciation cannot be
meaningfully practiced through text-only writing.

TEMPLATES IN THIS FILE
──────────────────────
Read    │ 1. Phoneme awareness (identify words with target sound)
Listen  │ 2. Identify mispronounced word in audio
        │ 3. Detect stress pattern in audio
Speak   │ 4. Read aloud (full sentence)
        │ 5. Minimal pairs drill (ship vs sheep, etc.)
        │ 6. Shadow audio (repeat after model)
        │ 7. Connected speech (linking + reductions)

Total: 7 Pronunciation templates.
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
# SHARED LABELS — phoneme + accent vocabulary
# ═════════════════════════════════════════════════════════════════════


# Common problem phonemes for non-native English speakers (esp. Indian / SE Asian)
TargetPhoneme = Literal[
    "th_voiced",      # /ð/ as in "this", "father"
    "th_voiceless",   # /θ/ as in "think", "bath"
    "v_vs_w",         # /v/ vs /w/ confusion
    "p_vs_f",         # /p/ vs /f/ confusion
    "r_sound",        # /r/ — rolled vs American
    "l_vs_r",         # /l/ vs /r/ distinction
    "schwa",          # /ə/ — unstressed vowel reduction
    "short_i",        # /ɪ/ as in "ship"
    "long_i",         # /iː/ as in "sheep"
    "short_a",        # /æ/ as in "cat"
    "z_vs_s",         # /z/ vs /s/ at end of words
    "ed_endings",     # /t/, /d/, /ɪd/ in past tense
    "consonant_cluster",  # "strengths", "twelfths"
]


# Reference accent for evaluation
ReferenceAccent = Literal[
    "general_american",
    "received_pronunciation",  # British RP
    "neutral_international",   # mixed/clear, no strong regional bias
]


# Stress placement
StressPosition = Literal[
    "first_syllable",
    "second_syllable",
    "third_syllable",
    "last_syllable",
]


# ═════════════════════════════════════════════════════════════════════
# LAYER 2 — PYDANTIC MODELS
# ═════════════════════════════════════════════════════════════════════


# ─── Template 1: Phoneme Awareness (Read) ─────────────────────────────


class PhonemeAwarenessItem(BaseModel):
    item_id: str
    word_set: list[str] = Field(..., min_length=4, max_length=4)
    target_phoneme: TargetPhoneme
    correct_indices: list[int] = Field(
        ..., description="Indices (0-3) of words that contain the target phoneme"
    )
    explanation: str = Field(..., description="Why these words have the sound")


class PhonemeAwarenessTask(GeneratedTaskBase):
    instructions: str
    target_phoneme: TargetPhoneme
    phoneme_description: str = Field(
        ..., description="Plain-English description, e.g. 'the soft th in think'"
    )
    items: list[PhonemeAwarenessItem] = Field(..., min_length=4, max_length=8)


# ─── Template 2: Identify Mispronounced Word (Listen) ─────────────────


class MispronouncedItem(BaseModel):
    item_id: str
    audio_transcript: str = Field(
        ..., description="Sentence as it should be pronounced correctly"
    )
    mispronounced_word: str = Field(
        ..., description="The word to be deliberately mispronounced in the audio"
    )
    common_mispronunciation: str = Field(
        ..., description="How the word is wrongly pronounced (phonetic spelling)"
    )
    target_phoneme: TargetPhoneme
    options: list[str] = Field(
        ..., min_length=4, max_length=4,
        description="4 words from the sentence — user picks the wrong one",
    )


class IdentifyMispronouncedTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled by TTS pipeline with deliberate mispronunciation"
    )
    items: list[MispronouncedItem] = Field(..., min_length=3, max_length=6)


# ─── Template 3: Detect Stress Pattern (Listen) ───────────────────────


class StressPatternItem(BaseModel):
    item_id: str
    word: str
    syllables: list[str] = Field(
        ..., min_length=2, max_length=5,
        description="Word broken into syllables, e.g. ['pho', 'to', 'graph']",
    )
    correct_stress_position: StressPosition
    distractor_meaning_if_wrong_stress: str | None = Field(
        None,
        description="If wrong stress changes meaning (e.g. RECord noun vs reCORD verb)",
    )


class StressPatternTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = None
    items: list[StressPatternItem] = Field(..., min_length=4, max_length=8)


# ─── Template 4: Read Aloud (Speak) ───────────────────────────────────


class ReadAloudTask(GeneratedTaskBase):
    instructions: str
    sentence_to_read: str = Field(..., min_length=20, max_length=200)
    reference_accent: ReferenceAccent
    target_phonemes_in_sentence: list[TargetPhoneme] = Field(
        ..., min_length=1,
        description="Which problem phonemes appear in this sentence (for focused scoring)",
    )
    expected_difficult_words: list[str] = Field(
        ..., min_length=1,
        description="Words the learner is most likely to mispronounce",
    )
    reference_audio_url: str | None = Field(
        None, description="ElevenLabs TTS reference audio, filled later"
    )
    minimum_acceptable_score: float = Field(
        default=0.7, ge=0, le=1,
        description="Azure Speech overall score threshold to pass",
    )


# ─── Template 5: Minimal Pairs Drill (Speak) ──────────────────────────


class MinimalPair(BaseModel):
    pair_id: str
    word_a: str = Field(..., description="e.g. 'ship'")
    word_b: str = Field(..., description="e.g. 'sheep'")
    contrasting_phonemes: list[TargetPhoneme] = Field(..., min_length=1, max_length=2)
    sample_sentence_a: str
    sample_sentence_b: str


class MinimalPairsDrillTask(GeneratedTaskBase):
    instructions: str
    target_phoneme_contrast: TargetPhoneme
    pairs: list[MinimalPair] = Field(..., min_length=4, max_length=8)
    reference_audio_url: str | None = None
    drill_format: Literal[
        "say_each_pair",          # speak both words clearly
        "say_in_sentence",        # use each in its sample sentence
        "rapid_alternation",      # alternate quickly to test discrimination
    ]


# ─── Template 6: Shadow Audio (Speak) ─────────────────────────────────


class ShadowAudioTask(GeneratedTaskBase):
    instructions: str
    text_to_shadow: str = Field(..., min_length=30, max_length=300)
    reference_audio_url: str | None = Field(
        None, description="ElevenLabs TTS reference, filled later"
    )
    reference_accent: ReferenceAccent
    speaking_speed: Literal["slow", "normal", "fast"] = "normal"
    focus_areas: list[Literal[
        "intonation_rise_fall",
        "word_stress",
        "sentence_stress",
        "rhythm_and_pacing",
        "linking_words",
    ]] = Field(..., min_length=1, max_length=3)
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 7: Connected Speech (Speak) ─────────────────────────────


class ConnectedSpeechItem(BaseModel):
    item_id: str
    written_form: str = Field(..., description="e.g. 'What are you doing?'")
    natural_spoken_form: str = Field(
        ..., description="e.g. 'Whaddaya doin'?' — how natives actually say it",
    )
    feature_demonstrated: Literal[
        "linking",                # "an apple" → "anapple"
        "elision",                # "fish and chips" → "fish'n chips"
        "assimilation",           # "good boy" → "goob boy"
        "weak_form",              # "and" → /ən/
        "reduction",              # "going to" → "gonna"
    ]
    common_mistake: str = Field(
        ..., description="What over-careful learners say instead",
    )


class ConnectedSpeechTask(GeneratedTaskBase):
    instructions: str
    items: list[ConnectedSpeechItem] = Field(..., min_length=3, max_length=6)
    reference_audio_url: str | None = None
    grading_criteria: list[str] = Field(..., min_length=3)


# ═════════════════════════════════════════════════════════════════════
# LAYER 1 — TEMPLATE DEFINITIONS
# ═════════════════════════════════════════════════════════════════════


PRON_READ_PHONEME_AWARENESS_V1 = TaskTemplate(
    template_id="pron_read_phoneme_awareness_v1",
    sub_skill=SubSkill.PRONUNCIATION,
    activity=Activity.READ,
    task_type="phoneme_awareness",
    difficulty_range=(1, 8),
    estimated_time_minutes=4,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a phoneme awareness exercise. The learner reads sets of 4 words
and identifies which contain a target sound.

LEARNER PROFILE
- Sub-level: {sub_level}
- Native language background: {native_language}
- Known problem phonemes: {weak_phonemes}

TASK
1. Pick ONE target phoneme from the learner's weak phonemes: {weak_phonemes}
2. Provide a plain-English description of the sound (no IPA jargon)
3. Generate {item_count} sets of 4 words each
4. In each set, 1–3 words contain the target phoneme; others don't
5. Mix similar-looking spellings to make it tricky
   (e.g. for /θ/: "think, this, three, throw" — "this" is /ð/ not /θ/)
6. Provide a clear explanation per item

Return ONLY valid JSON matching the PhonemeAwarenessTask schema.
""",
    output_model_name="PhonemeAwarenessTask",
    evaluation_logic={
        "method": "exact_match_set",
        "scoring_rule": "Per item: 1 point if user's selected indices == correct_indices",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "beginner": {"item_count": 4},
        "intermediate": {"item_count": 6},
        "advanced": {"item_count": 8},
    },
)


PRON_LISTEN_IDENTIFY_MISPRONOUNCED_V1 = TaskTemplate(
    template_id="pron_listen_identify_mispronounced_v1",
    sub_skill=SubSkill.PRONUNCIATION,
    activity=Activity.LISTEN,
    task_type="identify_mispronounced",
    difficulty_range=(2, 9),
    estimated_time_minutes=5,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a listening task where the learner spots a deliberately mispronounced
word in an audio clip.

LEARNER PROFILE
- Sub-level: {sub_level}
- Weak phonemes: {weak_phonemes}

TASK
Generate {item_count} sentences:
1. Each is a natural 8–15 word sentence
2. ONE word will be mispronounced in the audio (the TTS pipeline handles this)
3. Mispronunciation must target a weak phoneme: {weak_phonemes}
4. Provide common_mispronunciation as a phonetic spelling
   (e.g. for "think" mispronounced: "tink" or "sink")
5. Provide 4 options from the sentence — only one is the wrong word

Return ONLY valid JSON matching the IdentifyMispronouncedTask schema.
Set audio_url to null.
""",
    output_model_name="IdentifyMispronouncedTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correctly identified mispronounced word",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "beginner": {"item_count": 3},
        "intermediate": {"item_count": 5},
        "advanced": {"item_count": 6},
    },
)


PRON_LISTEN_STRESS_PATTERN_V1 = TaskTemplate(
    template_id="pron_listen_stress_pattern_v1",
    sub_skill=SubSkill.PRONUNCIATION,
    activity=Activity.LISTEN,
    task_type="detect_stress_pattern",
    difficulty_range=(3, 10),
    estimated_time_minutes=5,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a listening task where the learner hears a multi-syllable word
and identifies which syllable carries the primary stress.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
Generate {item_count} multi-syllable words:
1. Each word has 2–5 syllables
2. Break each into a syllables array (e.g. "photograph" → ["pho", "to", "graph"])
3. Mark the correct stress position
4. INCLUDE at least 2 stress-shift word pairs if possible
   (e.g. RECord (n) vs reCORD (v), CONtent (n) vs conTENT (adj))
   Use distractor_meaning_if_wrong_stress to capture this
5. Mix difficulty: some common words, some {domain}-specific

Return ONLY valid JSON matching the StressPatternTask schema.
Set audio_url to null.
""",
    output_model_name="StressPatternTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correctly identified stress position",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "intermediate": {"item_count": 5},
        "advanced": {"item_count": 8},
    },
)


PRON_SPEAK_READ_ALOUD_V1 = TaskTemplate(
    template_id="pron_speak_read_aloud_v1",
    sub_skill=SubSkill.PRONUNCIATION,
    activity=Activity.SPEAK,
    task_type="read_aloud",
    difficulty_range=(1, 10),
    estimated_time_minutes=4,
    scoring_method=ScoringMethod.SPEECH_API,
    llm_prompt_template="""
Create a read-aloud task. The learner reads a sentence aloud; Azure Speech
Pronunciation Assessment scores phoneme-level accuracy.

LEARNER PROFILE
- Sub-level: {sub_level}
- Weak phonemes: {weak_phonemes}
- Domain: {domain}
- Reference accent: {reference_accent}

TASK
1. Generate ONE sentence (15–30 words) appropriate for sub-level {sub_level}
2. The sentence MUST contain at least 2 of the learner's weak phonemes: {weak_phonemes}
3. Tag which weak phonemes appear (target_phonemes_in_sentence)
4. List 3–5 expected_difficult_words the learner is most likely to mispronounce
5. Topic should fit the {domain} domain (relatable to the learner)
6. Set reference_audio_url to null (ElevenLabs fills it)
7. Set minimum_acceptable_score to 0.7

Return ONLY valid JSON matching the ReadAloudTask schema.
""",
    output_model_name="ReadAloudTask",
    evaluation_logic={
        "method": "azure_pronunciation_assessment",
        "metrics_returned": [
            "accuracy_score",      # phoneme accuracy 0-100
            "fluency_score",       # speed and pause naturalness
            "completeness_score",  # did they read all words
            "prosody_score",       # rhythm and intonation
            "pron_score",          # overall composite
        ],
        "weights": {
            "accuracy_score": 0.5,
            "fluency_score": 0.2,
            "completeness_score": 0.15,
            "prosody_score": 0.15,
        },
        "passing_threshold": 0.7,
        "feedback_triggers": {
            "below_0.5": "list every mispronounced word + give phonetic guidance",
            "0.5_to_0.7": "highlight 2–3 worst phonemes + practice tip",
            "above_0.7": "praise + 1 advanced subtlety to work on",
        },
    },
    difficulty_modifiers={
        "beginner": {"reference_accent": "neutral_international"},
        "intermediate": {"reference_accent": "general_american"},
        "advanced": {"reference_accent": "general_american"},
    },
)


PRON_SPEAK_MINIMAL_PAIRS_V1 = TaskTemplate(
    template_id="pron_speak_minimal_pairs_v1",
    sub_skill=SubSkill.PRONUNCIATION,
    activity=Activity.SPEAK,
    task_type="minimal_pairs_drill",
    difficulty_range=(2, 9),
    estimated_time_minutes=5,
    scoring_method=ScoringMethod.SPEECH_API,
    llm_prompt_template="""
Create a minimal pairs drill targeting a specific phoneme contrast that
the learner struggles with.

LEARNER PROFILE
- Sub-level: {sub_level}
- Weak phonemes: {weak_phonemes}

TASK
1. Pick ONE phoneme contrast from the learner's weak phonemes: {weak_phonemes}
   (e.g. short_i vs long_i → ship/sheep)
2. Generate {pair_count} minimal pairs that contrast this phoneme
3. For each pair, provide:
   - word_a and word_b (the contrasting pair)
   - sample sentences using each word naturally
4. Pick a drill_format: {drill_format}
5. Set reference_audio_url to null

Return ONLY valid JSON matching the MinimalPairsDrillTask schema.
""",
    output_model_name="MinimalPairsDrillTask",
    evaluation_logic={
        "method": "azure_pronunciation_assessment_per_word",
        "scoring_rule": "Each word scored individually; pair fails if either word's accuracy < 0.6",
        "weights": {"phoneme_accuracy": 0.7, "consistency_across_pairs": 0.3},
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "beginner": {"pair_count": 4, "drill_format": "say_each_pair"},
        "intermediate": {"pair_count": 6, "drill_format": "say_in_sentence"},
        "advanced": {"pair_count": 8, "drill_format": "rapid_alternation"},
    },
)


PRON_SPEAK_SHADOW_AUDIO_V1 = TaskTemplate(
    template_id="pron_speak_shadow_audio_v1",
    sub_skill=SubSkill.PRONUNCIATION,
    activity=Activity.SPEAK,
    task_type="shadow_audio",
    difficulty_range=(3, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.SPEECH_API,
    llm_prompt_template="""
Create a shadowing exercise. The learner listens to a reference audio and
repeats it immediately, matching rhythm, stress, and intonation.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}
- Reference accent: {reference_accent}

TASK
1. Generate a {word_range}-word passage on a {domain}-relevant topic
2. The text should have NATURAL rhythm with varied sentence lengths
3. Set reference_accent to {reference_accent}
4. Set speaking_speed to {speed}
5. Pick 2–3 focus_areas (which prosody features matter most here)
6. List 3 grading criteria specific to shadowing
   (rhythm match, stress placement, intonation contour)
7. Set reference_audio_url to null (ElevenLabs fills it)

Return ONLY valid JSON matching the ShadowAudioTask schema.
""",
    output_model_name="ShadowAudioTask",
    evaluation_logic={
        "method": "azure_pronunciation_assessment + prosody_match",
        "weights": {
            "prosody_score": 0.4,        # rhythm + intonation match
            "accuracy_score": 0.3,
            "fluency_score": 0.2,
            "speed_match": 0.1,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "intermediate": {
            "word_range": "30-50",
            "speed": "slow",
            "reference_accent": "neutral_international",
        },
        "advanced": {
            "word_range": "50-80",
            "speed": "normal",
            "reference_accent": "general_american",
        },
    },
)


PRON_SPEAK_CONNECTED_SPEECH_V1 = TaskTemplate(
    template_id="pron_speak_connected_speech_v1",
    sub_skill=SubSkill.PRONUNCIATION,
    activity=Activity.SPEAK,
    task_type="connected_speech",
    difficulty_range=(5, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.SPEECH_API,
    llm_prompt_template="""
Create a connected-speech exercise. Non-native speakers tend to over-pronounce
every word; natives link, reduce, and assimilate. This task fixes that.

LEARNER PROFILE
- Sub-level: {sub_level}
- Domain: {domain}

TASK
Generate {item_count} short phrases or sentences:
1. Each demonstrates ONE connected-speech feature:
   linking, elision, assimilation, weak_form, or reduction
2. For each item provide:
   - written_form: how it's written (e.g. "What are you doing?")
   - natural_spoken_form: how natives say it (e.g. "Whaddaya doin'?")
   - feature_demonstrated: which feature it shows
   - common_mistake: what over-careful learners say
3. Mix all 5 features across the items
4. List 3 grading criteria (linking smoothness, reduction accuracy, naturalness)

Return ONLY valid JSON matching the ConnectedSpeechTask schema.
Set reference_audio_url to null.
""",
    output_model_name="ConnectedSpeechTask",
    evaluation_logic={
        "method": "azure_pronunciation_assessment + naturalness_check",
        "weights": {
            "naturalness_score": 0.4,
            "feature_execution": 0.3,
            "fluency_score": 0.3,
        },
        "passing_threshold": 0.6,
        "notes": "Naturalness rewards reductions; over-careful 'textbook' speech is penalized",
    },
    difficulty_modifiers={
        "intermediate": {"item_count": 4},
        "advanced": {"item_count": 6},
    },
)


# ═════════════════════════════════════════════════════════════════════
# REGISTRY
# ═════════════════════════════════════════════════════════════════════


PRONUNCIATION_TEMPLATES: list[TaskTemplate] = [
    PRON_READ_PHONEME_AWARENESS_V1,
    PRON_LISTEN_IDENTIFY_MISPRONOUNCED_V1,
    PRON_LISTEN_STRESS_PATTERN_V1,
    PRON_SPEAK_READ_ALOUD_V1,
    PRON_SPEAK_MINIMAL_PAIRS_V1,
    PRON_SPEAK_SHADOW_AUDIO_V1,
    PRON_SPEAK_CONNECTED_SPEECH_V1,
]


PRONUNCIATION_OUTPUT_MODELS = {
    "PhonemeAwarenessTask": PhonemeAwarenessTask,
    "IdentifyMispronouncedTask": IdentifyMispronouncedTask,
    "StressPatternTask": StressPatternTask,
    "ReadAloudTask": ReadAloudTask,
    "MinimalPairsDrillTask": MinimalPairsDrillTask,
    "ShadowAudioTask": ShadowAudioTask,
    "ConnectedSpeechTask": ConnectedSpeechTask,
}
