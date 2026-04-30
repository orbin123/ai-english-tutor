"""Rule-based evaluator for fill-in-the-blanks tasks (Agent 2, MVP).

For FIB, an LLM is overkill — there is exactly ONE correct answer per
question. Simple string compare with normalization is fast, free, and
deterministic. Later stages (writing/speaking) will add an LLM-based
evaluator behind the same interface.

This module is PURE: data in, data out. No DB, no commits.
Persistence happens in the service layer (next stage).
"""

from typing import Literal

# Error taxonomy — keep it tiny for MVP.
# Add fancier labels (wrong_tense, subject_verb_disagreement, ...) later
# when we have grammar logic to detect them.
ErrorType = Literal["correct", "missing_answer", "wrong_answer"]


def _normalize(text: str) -> str:
    """Lowercase + strip. The minimum needed so 'Went ' == 'went'.

    We intentionally do NOT strip punctuation or collapse spaces yet —
    FIB answers are short single words/phrases; over-normalizing would
    hide real errors (e.g. user writes 'is not' as 'isnt').
    """
    return text.strip().lower()

def _check_one(user_answer: str, correct_answer: str) -> dict:
    """Score ONE question. Returns the per-question dict.

    Shape matches what the Feedback Agent (S10) already expects:
      {
        "correct": bool,
        "user_answer": str,        # original, NOT normalized — for display
        "correct_answer": str,
        "error_type": ErrorType,
      }
    """
    # Empty / whitespace-only → missing, not wrong.
    # We split these because the feedback message should differ:
    # "you didn't answer" vs "you answered, but wrong".
    if not user_answer.strip():
        return {
            "correct": False,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "error_type": "missing_answer",
        }

    is_correct = _normalize(user_answer) == _normalize(correct_answer)

    return {
        "correct": is_correct,
        "user_answer": user_answer,
        "correct_answer": correct_answer,
        "error_type": "correct" if is_correct else "wrong_answer",
    }

class EvaluationService:
    """Rule-based evaluator for fill-in-the-blanks tasks.

    Pure logic, no DB. Service layer (next stage) will:
      1. Load Task + UserResponse from DB.
      2. Call EvaluationService.evaluate_fill_in_blanks(...).
      3. Persist the returned dict into the Evaluation row.
    """

    def evaluate_fill_in_blanks(
        self,
        *,
        task_content: dict,
        user_answers: dict,
    ) -> dict:
        """Score a fill-in-the-blanks submission.

        Args:
            task_content: The Task.content JSONB. Expected shape includes
                an `activities` list with at least one fill_in_the_blanks
                activity that has `answers` (the key).
            user_answers: Flat dict {"Q1": "went", "Q2": "has", ...}
                — same shape as UserResponse.content.

        Returns:
            Evaluation report dict — shape documented at the bottom.
        """
        answer_key = self._extract_answer_key(task_content)

        per_question: dict[str, dict] = {}
        correct_count = 0

        # We loop over the ANSWER KEY, not user_answers.
        # Why? If the user skipped Q3 entirely, we still want it in the
        # report as a 'missing_answer'. Looping over user_answers would
        # silently drop unanswered questions.
        for qid, correct in answer_key.items():
            user_ans = user_answers.get(qid, "")  # missing → empty string
            result = _check_one(user_ans, correct)
            per_question[qid] = result
            if result["correct"]:
                correct_count += 1

        total = len(answer_key)
        # Guard against divide-by-zero on a malformed task with 0 questions
        percentage = round((correct_count / total) * 100, 2) if total else 0.0

        return {
            "task_type": "fill_in_the_blanks",
            "total": total,
            "correct_count": correct_count,
            "percentage": percentage,
            "questions": per_question,
        }

    @staticmethod
    def _extract_answer_key(task_content: dict) -> dict[str, str]:
        """Find the FIB activity in task_content and return its answers.

        Task content shape (from seed files):
            {
              "activities": [
                {"activity_type": "fill_in_the_blanks", "answers": {...}, ...},
                {"activity_type": "mcq", ...},
              ]
            }

        Raises:
            ValueError: if no fill_in_the_blanks activity is found.
        """
        for activity in task_content.get("activities", []):
            if activity.get("activity_type") == "fill_in_the_blanks":
                return activity["answers"]
        raise ValueError(
            "task_content has no fill_in_the_blanks activity"
        )