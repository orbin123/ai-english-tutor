"""Agent — Diagnosis Feedback.

Generates a human-friendly interpretation of the user's diagnosis scores.
Called once, right after DiagnosisService computes the 7 skill scores.

Purpose: explain the user's starting profile in plain English so they
understand their weaknesses and why LingosAI will help them reach their goal.

Input  : 7 skill scores + user goal + self-assessed level + weakest 2 skills
Output : DiagnosisFeedbackOutput (structured JSON from LLM)
"""

from pydantic import BaseModel, Field
from app.ai.llm import get_llm


# ---------------------------------------------------------------------------
# 1. OUTPUT SCHEMA — what the LLM must return
# ---------------------------------------------------------------------------

class WeakSkillExplanation(BaseModel):
    """Plain-English explanation for one weak skill."""
    skill_name: str = Field(description="e.g. 'grammar', 'vocabulary'")
    what_it_means: str = Field(
        description="What this skill is, in 1 simple sentence"
    )
    why_it_matters: str = Field(
        description=(
            "Why this skill matters for the user's specific goal "
            "(professional / academic / casual). 1-2 sentences."
        )
    )
    what_to_expect: str = Field(
        description=(
            "What kind of tasks LingosAI will give them to improve this skill. "
            "1 concrete sentence."
        )
    )


class DiagnosisFeedbackOutput(BaseModel):
    """Full diagnosis feedback payload returned to the frontend."""

    estimated_level_label: str = Field(
        description=(
            "A human-friendly level label based on the scores. "
            "Examples: 'Upper Beginner', 'Lower Intermediate', 'Solid Intermediate', "
            "'Upper Intermediate', 'Advanced'. Pick the closest match."
        )
    )
    summary: str = Field(
        description=(
            "2-3 sentences. Summarise the user's overall English profile honestly. "
            "Name their strongest area briefly. Name their main weakness clearly. "
            "Do NOT use empty praise like 'Great job!'. Be direct and kind."
        )
    )
    weak_skill_explanations: list[WeakSkillExplanation] = Field(
        description="One entry per weak skill passed in. Usually 2 items."
    )
    motivation: str = Field(
        description=(
            "1-2 sentences. Honest, specific encouragement tied to their goal. "
            "Tell them exactly what they will be able to do after improving these skills. "
            "No generic motivational fluff."
        )
    )
    first_week_focus: str = Field(
        description=(
            "One sentence telling the user what their first week of tasks will focus on."
        )
    )


# ---------------------------------------------------------------------------
# 2. SYSTEM PROMPT
# ---------------------------------------------------------------------------

DIAGNOSIS_FEEDBACK_SYSTEM_PROMPT = """\
You are a diagnostic interpreter for LingosAI, an AI-powered English learning app.

Your job: take a new user's skill scores from a short diagnostic test and explain
their profile to them in plain, honest, encouraging English.

YOUR RULES:
1. Use SIMPLE English. The user is a non-native speaker.
2. Be HONEST. If scores are low, say so clearly but kindly. Do not sugarcoat.
3. NEVER use generic phrases like "Great job!", "You're doing amazing!", or
   "Keep it up!" alone. Any encouragement must be specific and tied to their goal.
4. Always connect weaknesses to the user's GOAL (professional, academic, or casual).
   A professional user cares about emails and meetings.
   An academic user cares about essays and presentations.
   A casual user cares about everyday conversation.
5. Be CONCRETE. Tell the user exactly what kind of tasks they will practice.
6. Keep each field short and focused. Do not repeat yourself across fields.

You will receive:
- The user's self-assessed level (beginner / intermediate / advanced)
- Their goal (professional / academic / casual)
- Their 7 skill scores (scale 1.0 to 4.0)
- Their 2 weakest skill names

Return your response in the required JSON schema. Nothing else.
"""


# ---------------------------------------------------------------------------
# 3. HUMAN MESSAGE BUILDER
# ---------------------------------------------------------------------------

def _build_human_message(
    self_assessed_level: str,
    goal: str,
    skill_scores: dict[str, float],
    weakest_skills: list[str],
) -> str:
    scores_text = "\n".join(
        f"  {name}: {score:.2f} / 4.00"
        for name, score in sorted(skill_scores.items(), key=lambda kv: kv[1])
    )
    weak_text = ", ".join(weakest_skills)

    return f"""\
USER PROFILE:
  Self-assessed level : {self_assessed_level}
  Goal                : {goal}

SKILL SCORES (1.0 = very weak, 4.0 = excellent):
{scores_text}

WEAKEST SKILLS (focus these in your explanation):
  {weak_text}

Generate the diagnosis feedback now.
"""


# ---------------------------------------------------------------------------
# 4. PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

async def generate_diagnosis_feedback(
    *,
    self_assessed_level: str,
    goal: str,
    skill_scores: dict[str, float],
    weakest_skills: list[str],
) -> DiagnosisFeedbackOutput:
    """Call the LLM and return a validated DiagnosisFeedbackOutput.

    Args:
        self_assessed_level: "beginner" | "intermediate" | "advanced"
        goal: "professional" | "academic" | "casual"
        skill_scores: dict of 7 skill names → float scores
        weakest_skills: list of 2 skill name strings

    Returns:
        DiagnosisFeedbackOutput — structured, validated feedback object.

    Raises:
        pydantic.ValidationError: if the LLM returns bad JSON (very rare
            with structured output).
    """
    llm = get_llm()
    structured_llm = llm.with_structured_output(DiagnosisFeedbackOutput)

    messages = [
        ("system", DIAGNOSIS_FEEDBACK_SYSTEM_PROMPT),
        (
            "human",
            _build_human_message(
                self_assessed_level=self_assessed_level,
                goal=goal,
                skill_scores=skill_scores,
                weakest_skills=weakest_skills,
            ),
        ),
    ]

    result = await structured_llm.ainvoke(messages)
    return result
