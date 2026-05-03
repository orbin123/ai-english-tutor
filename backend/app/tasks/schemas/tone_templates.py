"""
Tone & Social Awareness — Task Templates.

Sub-Skill #7 of 7. The final sub-skill — and the most "social". Covers
how the learner reads, produces, and adjusts the social layer of language:
register, tone, and the confidence to deliver them under pressure.

KEY DIFFERENCE FROM OTHER SUB-SKILLS
This sub-skill has TWO seemingly different dimensions that actually
feed each other:
  • Tone & register awareness — picking the right "voice" for the situation
  • Confidence / speaking anxiety — feeling safe enough to actually do it

Anxious learners often default to over-formal or over-simple speech
because they're afraid of misreading the social context. So practicing
tone-control IS practicing confidence — the two cannot be separated.

TEMPLATES IN THIS FILE
──────────────────────
Read    │ 1. Identify tone & register (recognition)
        │ 2. Match message to scenario (context-fit awareness)
Write   │ 3. Register conversion (formal ↔ casual rewrites)
        │ 4. Tone-appropriate response (decline / disagree / apologize)
Listen  │ 5. Detect speaker tone & emotion
        │ 6. Spot register mismatch in dialogue
Speak   │ 7. Roleplay scenario (applied tone control)
        │ 8. Assertiveness / confidence drill

Total: 8 Tone templates.
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


# How formal/casual the language is. The single most important
# axis the learner has to control.
Register = Literal[
    "highly_formal",   # legal, academic, ceremonial — very stiff
    "formal",          # business email, client-facing, professional
    "neutral",         # standard educated English, default workplace
    "casual",          # colleagues you know, friendly emails
    "very_casual",     # close friends, slang, heavy contractions
]


# The emotional/attitudinal coloring on top of register.
# A message can be "formal + warm" or "formal + cold" — register and
# tone are independent dimensions.
ToneLabel = Literal[
    "polite",
    "warm_friendly",
    "neutral_professional",
    "assertive",
    "apologetic",
    "frustrated",
    "sarcastic",
    "enthusiastic",
    "concerned",
    "firm",
    "diplomatic",
]


# Real-world "face-threatening" situations learners commonly struggle with.
# These are the exact moments where tone awareness + confidence both matter.
SocialScenario = Literal[
    "decline_invitation",
    "decline_request_at_work",
    "ask_for_help",
    "deliver_bad_news",
    "disagree_with_boss",
    "give_negative_feedback",
    "apologize_for_mistake",
    "ask_for_raise_or_promotion",
    "introduce_yourself_at_event",
    "respond_to_compliment",
    "follow_up_after_no_response",
    "set_a_boundary",
    "interrupt_politely",
    "small_talk_with_stranger",
]


# ═════════════════════════════════════════════════════════════════════
# LAYER 2 — PYDANTIC MODELS (validate LLM output for each template)
# ═════════════════════════════════════════════════════════════════════


# ─── Template 1: Identify Tone & Register (Read) ──────────────────────


class ToneIdentificationItem(BaseModel):
    item_id: str
    message: str = Field(..., min_length=15, max_length=400)
    correct_register: Register
    correct_tone: ToneLabel
    register_options: list[Register] = Field(..., min_length=4, max_length=4)
    tone_options: list[ToneLabel] = Field(..., min_length=4, max_length=4)
    signal_phrases: list[str] = Field(
        ..., min_length=1, max_length=4,
        description="Specific phrases in the message that reveal register/tone",
    )
    explanation: str = Field(..., min_length=20, max_length=300)


class ToneIdentificationTask(GeneratedTaskBase):
    instructions: str
    items: list[ToneIdentificationItem] = Field(..., min_length=4, max_length=8)


# ─── Template 2: Match Message to Scenario (Read) ─────────────────────


class MessageScenarioItem(BaseModel):
    item_id: str
    message: str = Field(..., min_length=15, max_length=300)
    correct_scenario: SocialScenario
    scenario_options: list[SocialScenario] = Field(..., min_length=4, max_length=4)
    why_it_fits: str = Field(
        ..., description="What about the message language signals this scenario"
    )


class MessageToScenarioTask(GeneratedTaskBase):
    instructions: str
    items: list[MessageScenarioItem] = Field(..., min_length=4, max_length=8)


# ─── Template 3: Register Conversion (Write) ──────────────────────────


class RegisterConversionItem(BaseModel):
    item_id: str
    original_message: str = Field(..., min_length=20, max_length=300)
    original_register: Register
    target_register: Register
    sample_converted: str = Field(..., description="A model conversion")
    must_change: list[str] = Field(
        ..., min_length=2, max_length=6,
        description="Specific elements that MUST change "
        "(e.g. 'replace contractions', 'remove slang', 'add greeting')",
    )
    must_preserve: list[str] = Field(
        ..., min_length=1, max_length=4,
        description="Core meaning that must NOT be lost in the conversion",
    )


class RegisterConversionTask(GeneratedTaskBase):
    instructions: str
    items: list[RegisterConversionItem] = Field(..., min_length=3, max_length=6)
    grading_criteria: list[str] = Field(..., min_length=3)


# ─── Template 4: Tone-Appropriate Response (Write) ────────────────────


class ToneResponseTask(GeneratedTaskBase):
    instructions: str
    scenario: SocialScenario
    scenario_context: str = Field(
        ..., min_length=40, max_length=500,
        description="The full situation: who, what, why this is socially tricky",
    )
    target_register: Register
    target_tone: ToneLabel
    target_word_count_min: int = Field(..., ge=20, le=200)
    target_word_count_max: int = Field(..., ge=40, le=300)
    required_elements: list[str] = Field(
        ..., min_length=3, max_length=6,
        description="Things the response must include "
        "(e.g. 'acknowledge their request', 'offer alternative', 'maintain warmth')",
    )
    things_to_avoid: list[str] = Field(
        ..., min_length=2, max_length=5,
        description="Common mistakes "
        "(e.g. 'avoid blaming language', 'no excessive apology', 'no hedging')",
    )
    sample_response: str = Field(
        ..., description="A model response showing the right tone in action"
    )
    grading_criteria: list[str] = Field(..., min_length=4)


# ─── Template 5: Detect Speaker Tone & Emotion (Listen) ───────────────


class SpeakerToneItem(BaseModel):
    item_id: str
    audio_transcript: str = Field(
        ..., min_length=15, max_length=250,
        description="What the speaker says — IMPORTANT: word choice and structure "
        "should carry the tone, not just prosody (TTS may not convey sarcasm well)",
    )
    correct_tone: ToneLabel
    tone_options: list[ToneLabel] = Field(..., min_length=4, max_length=4)
    verbal_cues: list[str] = Field(
        ..., min_length=1, max_length=4,
        description="Word choices, hedging, or phrasing that signal the tone",
    )
    explanation: str = Field(..., min_length=20, max_length=300)


class DetectSpeakerToneTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled later by TTS pipeline; null until audio is generated"
    )
    items: list[SpeakerToneItem] = Field(..., min_length=4, max_length=7)


# ─── Template 6: Spot Register Mismatch in Dialogue (Listen) ──────────


class DialogueLine(BaseModel):
    line_id: str = Field(..., description="e.g. 'l1', 'l2'")
    speaker: str = Field(..., description="e.g. 'Manager', 'Employee', 'Customer'")
    text: str = Field(..., min_length=5, max_length=200)
    is_mismatch: bool = Field(
        ..., description="Whether THIS line uses inappropriate register for the context"
    )
    why_mismatch: str | None = Field(
        None, description="If is_mismatch=true, explain the misfire. Else null."
    )


class RegisterMismatchTask(GeneratedTaskBase):
    instructions: str
    audio_url: str | None = Field(
        None, description="Filled later by TTS pipeline; null until audio is generated"
    )
    scenario_context: str = Field(
        ..., min_length=30, max_length=300,
        description="The dialogue's setting (e.g. 'a job interview', 'a customer call')",
    )
    expected_register: Register = Field(
        ..., description="The register appropriate for this scenario"
    )
    dialogue: list[DialogueLine] = Field(..., min_length=5, max_length=10)
    total_mismatches: int = Field(..., ge=1, le=4)


# ─── Template 7: Roleplay Scenario (Speak) ────────────────────────────


class RoleplayTurn(BaseModel):
    turn_id: str
    other_speaker_says: str = Field(
        ..., description="What the other character says (the prompt the learner responds to)"
    )
    target_intent: str = Field(
        ..., description="What the learner needs to accomplish in their reply"
    )
    sample_learner_response: str = Field(
        ..., description="A model response demonstrating the right tone"
    )


class RoleplayScenarioTask(GeneratedTaskBase):
    instructions: str
    scenario: SocialScenario
    scenario_setup: str = Field(
        ..., min_length=40, max_length=500,
        description="The full setup: who, where, why this conversation is happening",
    )
    learner_role: str = Field(
        ..., description="The role the learner plays (e.g. 'You are an employee asking your manager...')"
    )
    target_register: Register
    target_tone: ToneLabel
    turns: list[RoleplayTurn] = Field(
        ..., min_length=2, max_length=4,
        description="The conversation turns — learner responds to each prompt in sequence",
    )
    minimum_duration_seconds: int = Field(default=60, ge=30, le=180)
    grading_criteria: list[str] = Field(..., min_length=4)


# ─── Template 8: Assertiveness / Confidence Drill (Speak) ─────────────


class AssertivenessChallenge(BaseModel):
    challenge_id: str
    pressure_situation: str = Field(
        ..., min_length=20, max_length=300,
        description="A face-threatening prompt the learner must respond to",
    )
    target_intent: Literal[
        "say_no_clearly",
        "disagree_respectfully",
        "ask_directly",
        "hold_position_under_pushback",
        "redirect_back_to_topic",
        "decline_without_apologizing_excessively",
    ]
    sample_confident_response: str = Field(
        ..., description="A model response that is direct AND polite"
    )
    confidence_markers: list[str] = Field(
        ..., min_length=3, max_length=6,
        description="Specific signals the response should contain "
        "(e.g. 'no excessive apology', 'declarative not interrogative', "
        "'clear refusal verb', 'no hedging like \"maybe\" / \"I think\"')",
    )
    anti_patterns: list[str] = Field(
        ..., min_length=2, max_length=5,
        description="Patterns to AVOID "
        "(e.g. 'over-apologizing', 'excessive hedging', 'rambling justification')",
    )


class AssertivenessDrillTask(GeneratedTaskBase):
    instructions: str
    challenges: list[AssertivenessChallenge] = Field(..., min_length=2, max_length=4)
    minimum_duration_seconds_per_challenge: int = Field(default=20, ge=10, le=60)
    grading_criteria: list[str] = Field(
        ..., min_length=4,
        description="Should include: directness, absence_of_anti_patterns, "
        "tone_remains_polite, fluency",
    )


# ═════════════════════════════════════════════════════════════════════
# LAYER 1 — TEMPLATE DEFINITIONS (loaded by the Task Selector at startup)
# ═════════════════════════════════════════════════════════════════════


TONE_READ_IDENTIFY_V1 = TaskTemplate(
    template_id="tone_read_identify_v1",
    sub_skill=SubSkill.TONE,
    activity=Activity.READ,
    task_type="identify_tone_register",
    difficulty_range=(3, 10),
    estimated_time_minutes=6,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a tone & register identification exercise. The learner reads a
short message and identifies BOTH its register (formality level) AND
its tone (emotional coloring).

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Generate exactly {item_count} short messages from a MIX of contexts:
   workplace emails, text messages, customer service, social media, etc.
2. For each message:
   - Set correct_register from: highly_formal, formal, neutral, casual, very_casual
   - Set correct_tone from: polite, warm_friendly, neutral_professional, assertive,
     apologetic, frustrated, sarcastic, enthusiastic, concerned, firm, diplomatic
   - Provide 4 register_options (correct + 3 distractors — pick adjacent registers
     so the choice is not too easy)
   - Provide 4 tone_options (correct + 3 plausible distractors)
   - List 1–4 signal_phrases — the exact words/phrases revealing the tone
   - Write a 1–2 sentence explanation
3. Use vocabulary appropriate to {vocab_level}

Return ONLY valid JSON matching the ToneIdentificationTask schema.
No prose, no markdown fences.
""",
    output_model_name="ToneIdentificationTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "0.5 for correct register + 0.5 for correct tone, per item",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "beginner": {"item_count": 4, "vocab_level": "basic"},
        "intermediate": {"item_count": 6, "vocab_level": "intermediate"},
        "advanced": {"item_count": 8, "vocab_level": "advanced"},
    },
)


TONE_READ_MATCH_SCENARIO_V1 = TaskTemplate(
    template_id="tone_read_match_scenario_v1",
    sub_skill=SubSkill.TONE,
    activity=Activity.READ,
    task_type="match_message_to_scenario",
    difficulty_range=(3, 10),
    estimated_time_minutes=5,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a context-matching exercise. The learner reads a short message
and identifies WHICH social scenario the message belongs to.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Generate exactly {item_count} messages
2. For each message:
   - Pick a correct_scenario from this set: {scenario_pool}
   - Write a message that clearly fits that scenario (15–300 chars)
   - Provide 4 scenario_options (correct + 3 plausible distractors —
     pick scenarios that share register but differ in intent)
   - Explain in 1–2 sentences why the language signals this scenario
     (e.g. "the phrase 'I'd like to discuss my growth' signals
      ask_for_raise_or_promotion, not give_negative_feedback")

Return ONLY valid JSON matching the MessageToScenarioTask schema.
""",
    output_model_name="MessageToScenarioTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct scenario, normalized to 0–1",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "beginner": {
            "item_count": 4,
            "scenario_pool": (
                "decline_invitation, ask_for_help, "
                "introduce_yourself_at_event, respond_to_compliment"
            ),
        },
        "intermediate": {
            "item_count": 6,
            "scenario_pool": (
                "decline_request_at_work, deliver_bad_news, apologize_for_mistake, "
                "follow_up_after_no_response, small_talk_with_stranger, "
                "interrupt_politely"
            ),
        },
        "advanced": {
            "item_count": 8,
            "scenario_pool": (
                "all 14 scenarios including disagree_with_boss, "
                "give_negative_feedback, ask_for_raise_or_promotion, set_a_boundary"
            ),
        },
    },
)


TONE_WRITE_REGISTER_CONVERSION_V1 = TaskTemplate(
    template_id="tone_write_register_conversion_v1",
    sub_skill=SubSkill.TONE,
    activity=Activity.WRITE,
    task_type="register_conversion",
    difficulty_range=(3, 10),
    estimated_time_minutes=10,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a register-conversion exercise. The learner rewrites messages,
shifting them between formal and casual registers.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Generate exactly {item_count} conversion items
2. For each item:
   - Provide an original_message (a real-world style: email, text, slack, etc.)
   - Set original_register and target_register (use a mix of directions:
     formal→casual AND casual→formal — not just one direction)
   - Make the gap meaningful — e.g. casual → formal, or very_casual → neutral
     (skipping levels is the most useful drill)
   - Provide a sample_converted version
   - List 2–6 must_change elements (concrete: "remove contractions",
     "replace 'hey' with proper greeting", "add closing line")
   - List 1–4 must_preserve elements (the core meaning)
3. Provide 3+ grading_criteria: register_match, meaning_preserved,
   appropriate_tone, language_quality

Return ONLY valid JSON matching the RegisterConversionTask schema.
""",
    output_model_name="RegisterConversionTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "register_match": 0.40,
            "meaning_preserved": 0.30,
            "appropriate_tone": 0.20,
            "language_quality": 0.10,
        },
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "beginner": {"item_count": 3},
        "intermediate": {"item_count": 4},
        "advanced": {"item_count": 6},
    },
)


TONE_WRITE_RESPONSE_V1 = TaskTemplate(
    template_id="tone_write_tone_appropriate_response_v1",
    sub_skill=SubSkill.TONE,
    activity=Activity.WRITE,
    task_type="tone_appropriate_response",
    difficulty_range=(5, 10),
    estimated_time_minutes=12,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a tone-under-pressure writing task. The learner faces a socially
TRICKY situation and must write a response with the right tone.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick ONE scenario from: {scenario_pool}
2. Write scenario_context (40–300 words): describe who is involved, what
   happened, why this is socially difficult, and what the learner needs to do
3. Set target_register and target_tone — these should be the appropriate
   choices for the scenario (e.g. decline_request_at_work → formal + diplomatic)
4. Set target_word_count_min={min_words} and target_word_count_max={max_words}
5. List 3–6 required_elements the response MUST include
   (e.g. "acknowledge their request", "give a clear no", "offer alternative")
6. List 2–5 things_to_avoid common mistakes
   (e.g. "no over-apologizing", "no blaming language", "no excessive hedging")
7. Write a sample_response that demonstrates the target tone in action
8. Provide 4+ grading_criteria: scenario_handled, tone_match,
   required_elements_present, anti_patterns_avoided

Return ONLY valid JSON matching the ToneResponseTask schema.
""",
    output_model_name="ToneResponseTask",
    evaluation_logic={
        "method": "ai_evaluator",
        "weights": {
            "scenario_handled": 0.30,
            "tone_match": 0.30,
            "required_elements_present": 0.25,
            "anti_patterns_avoided": 0.15,
        },
        "passing_threshold": 0.65,
    },
    difficulty_modifiers={
        "intermediate": {
            "min_words": 60, "max_words": 120,
            "scenario_pool": (
                "decline_invitation, decline_request_at_work, "
                "apologize_for_mistake, follow_up_after_no_response"
            ),
        },
        "advanced": {
            "min_words": 100, "max_words": 220,
            "scenario_pool": (
                "disagree_with_boss, give_negative_feedback, "
                "ask_for_raise_or_promotion, set_a_boundary, deliver_bad_news"
            ),
        },
    },
)


TONE_LISTEN_DETECT_TONE_V1 = TaskTemplate(
    template_id="tone_listen_detect_tone_v1",
    sub_skill=SubSkill.TONE,
    activity=Activity.LISTEN,
    task_type="detect_speaker_tone",
    difficulty_range=(4, 10),
    estimated_time_minutes=7,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a tone-detection listening exercise. The learner hears short
spoken utterances and identifies the speaker's tone.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Generate exactly {item_count} short utterance items
2. For each item:
   - Write an audio_transcript (15–250 chars). IMPORTANT: word choice and
     phrasing must CARRY the tone — don't rely only on prosody, since basic
     TTS may not convey sarcasm or frustration well.
     For example: a sarcastic line should use words like "oh great, just
     what I needed" rather than depending on vocal inflection alone.
   - Set correct_tone from: {tone_pool}
   - Provide 4 tone_options (correct + 3 plausible distractors)
   - List 1–4 verbal_cues — exact words/phrases that signal the tone
   - Write a 1–2 sentence explanation
3. Set audio_url to null (TTS pipeline fills it later)

Return ONLY valid JSON matching the DetectSpeakerToneTask schema.
""",
    output_model_name="DetectSpeakerToneTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correct tone, normalized to 0–1",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "intermediate": {
            "item_count": 5,
            "tone_pool": (
                "polite, warm_friendly, neutral_professional, "
                "apologetic, enthusiastic, concerned"
            ),
        },
        "advanced": {
            "item_count": 7,
            "tone_pool": (
                "all 11 tones — including the harder-to-detect ones: "
                "sarcastic, frustrated, firm, diplomatic, assertive"
            ),
        },
    },
)


TONE_LISTEN_REGISTER_MISMATCH_V1 = TaskTemplate(
    template_id="tone_listen_register_mismatch_v1",
    sub_skill=SubSkill.TONE,
    activity=Activity.LISTEN,
    task_type="register_mismatch_dialogue",
    difficulty_range=(5, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.RULE_BASED,
    llm_prompt_template="""
Create a "spot the social misfire" exercise. The learner listens to a
dialogue and identifies which lines use a register that's INAPPROPRIATE
for the context.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick a clear scenario_context (e.g. "a job interview", "a customer support
   call", "an apology to a senior client")
2. Set the expected_register for that context
3. Write a dialogue of {line_count} lines between 2 speakers
4. Make exactly {mismatch_count} lines REGISTER MISMATCHES — they're
   grammatically fine but socially WRONG (too casual in a formal context,
   or oddly stiff in a casual context)
5. For each line:
   - line_id, speaker, text
   - is_mismatch (true/false)
   - why_mismatch: explain the misfire (or null if not a mismatch)
6. Set total_mismatches to match the actual count
7. Set audio_url to null (TTS pipeline fills it later)

Return ONLY valid JSON matching the RegisterMismatchTask schema.
""",
    output_model_name="RegisterMismatchTask",
    evaluation_logic={
        "method": "exact_match",
        "scoring_rule": "1 point per correctly flagged line (true positive OR true negative), "
                        "normalized to 0–1",
        "passing_threshold": 0.7,
    },
    difficulty_modifiers={
        "intermediate": {"line_count": 6, "mismatch_count": 2},
        "advanced": {"line_count": 8, "mismatch_count": 3},
    },
)


TONE_SPEAK_ROLEPLAY_V1 = TaskTemplate(
    template_id="tone_speak_roleplay_v1",
    sub_skill=SubSkill.TONE,
    activity=Activity.SPEAK,
    task_type="roleplay_scenario",
    difficulty_range=(4, 10),
    estimated_time_minutes=10,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create a roleplay speaking task. The learner takes on a role and responds
to prompts in a multi-turn scenario, using the right register and tone.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Pick a scenario from: {scenario_pool}
2. Write scenario_setup (40–400 words): the full situation
3. Write learner_role: who the learner plays in this scene
4. Set target_register and target_tone (the appropriate combo for this scenario)
5. Generate {turn_count} turns — each turn:
   - turn_id (e.g. "t1")
   - other_speaker_says: what the other character says (the prompt)
   - target_intent: what the learner must accomplish in their reply
   - sample_learner_response: a model response showing right tone
6. Set minimum_duration_seconds={duration}
7. Provide 4+ grading_criteria: register_match, tone_match,
   intent_accomplished, fluency

Return ONLY valid JSON matching the RoleplayScenarioTask schema.
""",
    output_model_name="RoleplayScenarioTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "register_match": 0.30,
            "tone_match": 0.25,
            "intent_accomplished": 0.30,
            "fluency": 0.15,
        },
        "passing_threshold": 0.6,
    },
    difficulty_modifiers={
        "intermediate": {
            "turn_count": 2, "duration": 60,
            "scenario_pool": (
                "small_talk_with_stranger, introduce_yourself_at_event, "
                "ask_for_help, decline_invitation"
            ),
        },
        "advanced": {
            "turn_count": 3, "duration": 90,
            "scenario_pool": (
                "disagree_with_boss, ask_for_raise_or_promotion, "
                "give_negative_feedback, set_a_boundary, deliver_bad_news"
            ),
        },
    },
)


TONE_SPEAK_ASSERTIVENESS_V1 = TaskTemplate(
    template_id="tone_speak_assertiveness_drill_v1",
    sub_skill=SubSkill.TONE,
    activity=Activity.SPEAK,
    task_type="assertiveness_drill",
    difficulty_range=(5, 10),
    estimated_time_minutes=8,
    scoring_method=ScoringMethod.AI_BASED,
    llm_prompt_template="""
Create an assertiveness / confidence drill. This directly trains the
"confidence" dimension of this sub-skill — the learner practices
responding to face-threatening situations directly and politely,
WITHOUT over-apologizing or hedging excessively.

LEARNER PROFILE
- Sub-level: {sub_level}

TASK
1. Generate exactly {challenge_count} pressure_situation challenges. Each
   should be a short prompt that triggers anxious / passive responses in
   non-native speakers, like:
   - "Your boss asks you to take on extra weekend work. You can't."
   - "A colleague keeps interrupting you in meetings."
   - "A client pushes back on a price you already agreed."
2. For each challenge:
   - target_intent (one of: say_no_clearly, disagree_respectfully, ask_directly,
     hold_position_under_pushback, redirect_back_to_topic,
     decline_without_apologizing_excessively)
   - sample_confident_response: a model that is DIRECT *and* POLITE
     (the key skill is doing both, not picking one)
   - confidence_markers: 3–6 specific signals to look for
     (e.g. "uses 'no' or clear refusal verb", "single brief reason — not 5",
      "no 'I'm so sorry but...'", "declarative not interrogative")
   - anti_patterns: 2–5 things to avoid
     (e.g. "over-apologizing", "rambling justification",
      "hedging with 'maybe', 'I think', 'I'm not sure but'")
3. Set minimum_duration_seconds_per_challenge={duration}
4. Provide 4+ grading_criteria covering: directness, absence_of_anti_patterns,
   tone_remains_polite, fluency

Return ONLY valid JSON matching the AssertivenessDrillTask schema.
""",
    output_model_name="AssertivenessDrillTask",
    evaluation_logic={
        "method": "ai_evaluator + speech_to_text",
        "weights": {
            "directness": 0.30,
            "absence_of_anti_patterns": 0.30,
            "tone_remains_polite": 0.25,
            "fluency": 0.15,
        },
        "passing_threshold": 0.6,
        "track_anti_pattern_frequency": True,  # build a "user always over-apologizes" signal
    },
    difficulty_modifiers={
        "intermediate": {"challenge_count": 2, "duration": 25},
        "advanced": {"challenge_count": 3, "duration": 30},
    },
)


# ═════════════════════════════════════════════════════════════════════
# REGISTRY — every template grouped for the Task Selector
# ═════════════════════════════════════════════════════════════════════


TONE_TEMPLATES: list[TaskTemplate] = [
    TONE_READ_IDENTIFY_V1,
    TONE_READ_MATCH_SCENARIO_V1,
    TONE_WRITE_REGISTER_CONVERSION_V1,
    TONE_WRITE_RESPONSE_V1,
    TONE_LISTEN_DETECT_TONE_V1,
    TONE_LISTEN_REGISTER_MISMATCH_V1,
    TONE_SPEAK_ROLEPLAY_V1,
    TONE_SPEAK_ASSERTIVENESS_V1,
]


# Map of LLM-output Pydantic models — used by the validator to pick the
# right schema based on `template.output_model_name`.
TONE_OUTPUT_MODELS = {
    "ToneIdentificationTask": ToneIdentificationTask,
    "MessageToScenarioTask": MessageToScenarioTask,
    "RegisterConversionTask": RegisterConversionTask,
    "ToneResponseTask": ToneResponseTask,
    "DetectSpeakerToneTask": DetectSpeakerToneTask,
    "RegisterMismatchTask": RegisterMismatchTask,
    "RoleplayScenarioTask": RoleplayScenarioTask,
    "AssertivenessDrillTask": AssertivenessDrillTask,
}
