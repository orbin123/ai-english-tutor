"""The 3-Agent System for LingosAI.

Per the AI Orchestration doc, every AI interaction in this app flows
through one of three logical agents. Each agent lives in its own file,
has a single responsibility, and exposes ONE public function so the
caller doesn't need to know whether the implementation is rule-based,
LLM-based, or a future swap.

    Agent 1 — Task Generator   →  task_generator.generate_task()
    Agent 2 — Evaluator        →  evaluator.EvaluationService
    Agent 3 — Feedback         →  feedback.generate_feedback()

Re-exporting the public symbols here lets callers do the clean import:

    from app.ai.agents import generate_feedback, EvaluationService
"""

from app.ai.agents.evaluator import EvaluationService
from app.ai.agents.feedback import FeedbackOutput, generate_feedback
from app.ai.agents.task_generator import generate_task

__all__ = [
    "EvaluationService",
    "FeedbackOutput",
    "generate_feedback",
    "generate_task",
]
