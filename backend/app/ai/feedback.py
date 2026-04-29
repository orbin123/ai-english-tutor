"""Feedback Agent (Agent 3) - generates human-readable corrective feedback.

Input : original task + user's answer + evaluation report
Output : structured JSON matching FeedbackOutput schema
Rule : Never says "Good job!" alone. Every praise must be followed by a correction
"""

from typing import Literal
from pydantic import BaseModel, Field 

from app.ai.llm import get_llm

# 1. OUTPUT SCHEMA - What we force the LLM to return 
class ErrorExplanation(BaseModel):
    """One mistake, fully explained for the learner."""
    question_id: str = Field(description="e.g 'Q1', 'Q2'")
    user_answer: str = Field(description="What the user wrote")
    correct_answer: str = Field(description="The right answer")
    error_type: str = Field(description="Plain-English reason, 1-2 sentences")
    why_wrong: str = Field(description="Plain-English reason, 1-2 sentences")
    rule: str = Field(description="The grammar/usage rule in simple words")
    memory_tip: str = Field(description="A short trick to remember it")

class FeedbackOutput(BaseModel):
    """Full Feedback payload - saved into Feedback.body JSONB."""

    overall_message: str = Field(
        description=(
            "2-3 sentences. Acknowledge effort + name the main weakness. "
            "Never end with empty praise"
        )
    )
    errors: list[ErrorExplanation] = Field(
        description="One entry per wrong answer. Empty list if all correct."
    )
    score: int = Field(ge=0, le=100, description="Percentage 0-100")
    overall_level: Literal["needs_work", "okay", "good", "excellent"]
    practice_suggestion: str = Field(
        description="One concrete next step (e.g. 'Write 5 past-tense sentences')"
    )

# 2. SYSTEM PROMPT - the agent's personality + rules (never changes per call)
FEEDBACK_SYSTEM_PROMPT = """\
You are a strict but kind English tutor. You give feedback to non-native
English learners on their task answers.

YOUR RULES (follow exactly):
1. NEVER write empty praise like "Good job!" or "Well done!" alone.
   Every positive comment must be followed by a specific correction or tip.
2. Be FACTUAL and SPECIFIC. Point to the exact word or phrase that is wrong.
3. Use SIMPLE English. The learner is not a native speaker.
4. For each error, explain:
   - what is wrong
   - why it is wrong (the rule)
   - a small memory trick to remember the rule
5. End with ONE concrete practice suggestion. Not vague advice.
6. If all answers are correct, still give one tip to push the learner
   to the next level.

You will receive:
- The original task (passage + questions)
- The user's answers
- An evaluation report (which answers are right/wrong, error types)

Return your response in the required JSON schema. Nothing else.
"""

# 3. HUMAN MESSAGE TEMPLATE - formats the per-call data
def build_human_message(
    task_content: dict,
    user_answers: dict,
    evaluation_report: dict,
    score: int,
) -> str:
    """Format task + answers + eval into one message for the LLM."""
    import json 
    return f"""\
ORIGINAL TASK:
{json.dumps(task_content, indent=2)}

USER's ANSWERS:
{json.dumps(user_answers, indent=2)}

EVALUATION REPORT:
{json.dumps(evaluation_report, indent=2)}

SCORE: {score}/100

Generate corrective feedback now.
"""

# 4. THE AGENT FUNCTION
async def generate_feedback(
    task_content: dict,
    user_answers: dict,
    evaluation_report: dict,
    score: int 
) -> FeedbackOutput:
    """
    Call the Feedback Agent. Returns a validated FeedbackOutput.

    Raises pydantic. ValidationError if the LLM returns bad JSON
    (Very rare with structured output, but possible)
    """
    llm = get_llm()
    structured_llm = llm.with_structured_output(FeedbackOutput)

    messages = [
        ("system", FEEDBACK_SYSTEM_PROMPT),
        ("human", build_human_message(
            task_content, user_answers, evaluation_report, score
        )),
    ]

    result = await structured_llm.ainvoke(messages)
    return result