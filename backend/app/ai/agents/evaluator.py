"""Agent 2 — Evaluator Agent.

Scores a user's answer against an answer key. Returns a structured
evaluation report with per-question correctness and an overall score.

Implementation: rule-based for fill-in-the-blanks (FIB).
For FIB an LLM is overkill — there is exactly ONE correct answer per
question. Simple string compare with normalization is fast, free, and
deterministic.

Later activity types (writing/speaking) will add an LLM-backed evaluator
behind the same `EvaluationService` interface — callers won't change.

This module is PURE: data in, data out. No DB, no commits.
Persistence happens in the service layer (responses/service.py).
"""

from typing import Literal


# ---------------------------------------------------------------------------
# Error taxonomy — keep it tiny for MVP.
# Add fancier labels (wrong_tense, subject_verb_disagreement, ...) later
# when we have grammar logic to detect them.
# ---------------------------------------------------------------------------
ErrorType = Literal[
    "correct",
    "missing_answer",
    "wrong_answer",
    "too_short",          # paraphrasing: answer is shorter than min_words
    "too_similar",        # paraphrasing: user copied the original
    "needs_review",       # paraphrasing: passed rule checks, needs LLM later
]


# Activity types this evaluator knows how to score.
# Keep this list in sync with the dispatcher (`evaluate`) below.
SupportedActivity = Literal[
    "fill_in_the_blanks",
    "sentence_engineering",
    "paraphrasing",
]


# ---------------------------------------------------------------------------
# Internal helpers (pure functions, no side effects)
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    """Lowercase + strip. The minimum needed so 'Went ' == 'went'.

    We intentionally do NOT strip punctuation or collapse spaces yet —
    FIB answers are short single words/phrases; over-normalizing would
    hide real errors (e.g. user writes 'is not' as 'isnt').
    """
    return text.strip().lower()


def _normalize_sentence(text: str) -> str:
    """Normalize a full sentence for comparison.

    Stronger than `_normalize` because for sentence engineering we want
    'She went to the market yesterday' to match 'she went to the market
    yesterday.' — same word order is what matters, NOT capitalization or
    a missing period (we still flag those in feedback later).

    Steps:
      1. lowercase + strip
      2. remove trailing punctuation (. ! ?)
      3. collapse multiple spaces into one
    """
    s = text.strip().lower()
    # Remove trailing sentence-ending punctuation
    while s.endswith((".", "!", "?")):
        s = s[:-1].rstrip()
    # Collapse internal whitespace
    return " ".join(s.split())


def _check_one(user_answer: str, correct_answer: str) -> dict:
    """Score ONE question. Returns the per-question dict.

    Shape matches what the Feedback Agent expects:
        {
          "correct": bool,
          "user_answer": str,        # original, NOT normalized — for display
          "correct_answer": str,
          "error_type": ErrorType,
        }
    """
    # Empty / whitespace-only → missing, not wrong.
    # Feedback should differ: "you didn't answer" vs "you answered, but wrong".
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


def _score_paraphrase(
    *,
    user_answer: str,
    original: str,
    reference: str | None,
    min_words: int,
) -> dict:
    """Cheap rule-based paraphrase scoring.

    Returns a dict with the same fields as `_check_one` PLUS a numeric
    `score` in [0.0, 1.0]. The dispatcher uses `score` to compute the
    overall percentage; per-question display still uses `error_type`.

    Rules (in order):
      1. Empty            → missing_answer        score=0.0
      2. < min_words      → too_short             score=0.0
      3. Identical to src → too_similar           score=0.0
      4. Otherwise        → needs_review          score=0.7

    The 0.7 placeholder reflects "this passed cheap checks but a real
    grader has not seen it yet." When we add the LLM evaluator, this
    function is the ONLY thing that changes.
    """
    # `correct_answer` field shows the user a sample paraphrase if we have
    # one, otherwise the original sentence (less useful but never None).
    sample = reference or original

    # Rule 1: empty
    if not user_answer.strip():
        return {
            "correct": False,
            "user_answer": user_answer,
            "correct_answer": sample,
            "error_type": "missing_answer",
            "score": 0.0,
        }

    word_count = len(user_answer.strip().split())

    # Rule 2: too short
    if word_count < min_words:
        return {
            "correct": False,
            "user_answer": user_answer,
            "correct_answer": sample,
            "error_type": "too_short",
            "score": 0.0,
        }

    # Rule 3: copied the original (after light normalization)
    if _normalize_sentence(user_answer) == _normalize_sentence(original):
        return {
            "correct": False,
            "user_answer": user_answer,
            "correct_answer": sample,
            "error_type": "too_similar",
            "score": 0.0,
        }

    # Passed rule checks — needs a real grader to confirm semantic match.
    return {
        "correct": True,         # True = "accepted", not "perfect"
        "user_answer": user_answer,
        "correct_answer": sample,
        "error_type": "needs_review",
        "score": 0.7,
    }


# ---------------------------------------------------------------------------
# Public agent class
# ---------------------------------------------------------------------------
class EvaluationService:
    """Rule-based evaluator for fill-in-the-blanks tasks.

    Pure logic, no DB. The service layer (responses/service.py) calls
    `evaluate_fill_in_blanks(...)` and persists the returned dict into
    the Evaluation row.

    Why a class (not plain functions)? Future evaluators (writing,
    speaking) may need shared state — e.g. a cached LLM client, an
    Azure Speech client, prompt templates. Keeping the class form now
    means we can add `evaluate_writing(...)`, `evaluate_speaking(...)`
    methods alongside without changing existing callers.
    """

    def evaluate_fill_in_blanks(
        self,
        *,
        task_content: dict,
        user_answers: dict,
    ) -> dict:
        """Score a fill-in-the-blanks submission.

        Args:
            task_content: The Task.content JSONB. Expected to contain an
                `activities` list with at least one fill_in_the_blanks
                activity that has an `answers` key.
            user_answers: Flat dict {"Q1": "went", "Q2": "has", ...}
                — same shape as UserResponse.content.

        Returns:
            Evaluation report dict — see shape at end of method.
        """
        answer_key = self._extract_answer_key(task_content)

        per_question: dict[str, dict] = {}
        correct_count = 0

        # Loop over the ANSWER KEY, not user_answers.
        # Why? If the user skipped Q3 entirely, we still want it in the
        # report as 'missing_answer'. Looping over user_answers would
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

    # ------------------------------------------------------------------
    # Sentence engineering — string match against the canonical answer.
    # ------------------------------------------------------------------
    def evaluate_sentence_engineering(
        self,
        *,
        task_content: dict,
        user_answers: dict,
    ) -> dict:
        """Score a sentence-engineering submission.

        Same pattern as FIB but uses `_normalize_sentence` so a missing
        period or wrong capitalization does not count as wrong — the
        user got the WORD ORDER right, which is what this activity
        teaches.

        Returns the same report shape as FIB so the Feedback Agent and
        the score updater don't need a special branch.
        """
        activity = self._find_activity(task_content, "sentence_engineering")
        answer_key: dict[str, str] = activity["answers"]

        per_question: dict[str, dict] = {}
        correct_count = 0

        for qid, correct in answer_key.items():
            user_ans = user_answers.get(qid, "")

            if not user_ans.strip():
                per_question[qid] = {
                    "correct": False,
                    "user_answer": user_ans,
                    "correct_answer": correct,
                    "error_type": "missing_answer",
                }
                continue

            is_correct = (
                _normalize_sentence(user_ans) == _normalize_sentence(correct)
            )
            per_question[qid] = {
                "correct": is_correct,
                "user_answer": user_ans,
                "correct_answer": correct,
                "error_type": "correct" if is_correct else "wrong_answer",
            }
            if is_correct:
                correct_count += 1

        total = len(answer_key)
        percentage = round((correct_count / total) * 100, 2) if total else 0.0

        return {
            "task_type": "sentence_engineering",
            "total": total,
            "correct_count": correct_count,
            "percentage": percentage,
            "questions": per_question,
        }

    # ------------------------------------------------------------------
    # Paraphrasing — STUB grader.
    #
    # No single correct answer exists for paraphrasing. A real grader
    # would call an LLM to score semantic similarity + grammar. Today we
    # ship cheap rule-based checks so the loop works end-to-end:
    #
    #   - empty            → missing_answer        (0%)
    #   - too short        → too_short             (0%)
    #   - identical to src → too_similar           (0%)
    #   - otherwise        → needs_review          (70% placeholder)
    #
    # TODO(post-MVP): replace `_score_paraphrase` with an LLM call.
    # The dispatcher signature stays the same so callers don't change.
    # ------------------------------------------------------------------
    def evaluate_paraphrasing(
        self,
        *,
        task_content: dict,
        user_answers: dict,
    ) -> dict:
        """Score a paraphrasing submission with rule-based heuristics."""
        activity = self._find_activity(task_content, "paraphrasing")
        originals: dict[str, str] = activity["questions"]
        references: dict[str, str] = activity.get("reference_answers", {})
        min_words: int = int(activity.get("min_words", 4))

        per_question: dict[str, dict] = {}
        score_sum = 0.0

        for qid, original in originals.items():
            user_ans = user_answers.get(qid, "")
            result = _score_paraphrase(
                user_answer=user_ans,
                original=original,
                reference=references.get(qid),
                min_words=min_words,
            )
            per_question[qid] = result
            score_sum += result["score"]

        total = len(originals)
        # `score` is 0.0..1.0 per question. Average → percentage.
        percentage = round((score_sum / total) * 100, 2) if total else 0.0
        # `correct_count` for paraphrasing means "passed all rule checks"
        correct_count = sum(
            1 for r in per_question.values() if r["score"] >= 0.7
        )

        return {
            "task_type": "paraphrasing",
            "total": total,
            "correct_count": correct_count,
            "percentage": percentage,
            "questions": per_question,
        }

    # ------------------------------------------------------------------
    # Dispatcher — the ONE method service code should call.
    # ------------------------------------------------------------------
    def evaluate(
        self,
        *,
        activity_type: str,
        task_content: dict,
        user_answers: dict,
    ) -> dict:
        """Route to the right evaluator based on activity_type.

        This is the single entry point for the responses service. Adding
        a new activity later means: write `evaluate_xxx`, add one line
        here. Callers don't change.

        Raises:
            ValueError: unsupported activity_type.
        """
        if activity_type == "fill_in_the_blanks":
            return self.evaluate_fill_in_blanks(
                task_content=task_content, user_answers=user_answers
            )
        if activity_type == "sentence_engineering":
            return self.evaluate_sentence_engineering(
                task_content=task_content, user_answers=user_answers
            )
        if activity_type == "paraphrasing":
            return self.evaluate_paraphrasing(
                task_content=task_content, user_answers=user_answers
            )
        raise ValueError(
            f"Unsupported activity_type: {activity_type!r}. "
            f"Supported: fill_in_the_blanks, sentence_engineering, paraphrasing."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _find_activity(task_content: dict, activity_type: str) -> dict:
        """Return the first activity dict matching `activity_type`.

        Generic version of `_extract_answer_key` — works for any
        activity, returns the whole activity dict (not just answers).
        """
        for activity in task_content.get("activities", []):
            if activity.get("activity_type") == activity_type:
                return activity
        raise ValueError(
            f"task_content has no {activity_type!r} activity"
        )
