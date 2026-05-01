"""Agent 1 — Task Generator Agent.

Status: NOT IMPLEMENTED YET (placeholder for the 3-agent contract).

Today, all tasks come from the seeded DB pool (`tasks` table) and the
RotationEngine picks one per day. That covers MVP.

This file exists to make the 3-agent architecture explicit and to lock
in the function signature so a future implementation can plug in
without touching callers.

When we DO implement this:
    - Input  : user skill profile + target sub-skill + activity type
               + difficulty level (1-10) + task type (FIB / MCQ / writing)
    - Output : structured JSON matching a TaskOutput schema (to be
               defined). Same shape as a row in the Task.content JSONB
               so the generated task can be persisted as a Task row and
               assigned via UserTask exactly like seeded tasks.
    - Rule   : Always targets the *weakest* sub-skill at the user's
               current level. Difficulty within ±1 of user's level.

Implementation will follow the same pattern as `feedback.py`:
    - Pydantic output schema (TaskOutput)
    - Constant SYSTEM prompt
    - LLM call via `get_llm()` with `.with_structured_output(...)`
"""


async def generate_task(
    *,
    skill_name: str,
    activity_type: str,
    difficulty: int,
    user_level: int,
) -> dict:
    """Generate a personalized task for a user.

    NOT IMPLEMENTED. Tasks are currently seeded via SQL fixtures and
    served from the DB pool by RotationEngine + TaskRepository.

    Raises:
        NotImplementedError: always, until the LLM-backed generator is
            built. Caller should not import this function in the live
            request path yet.
    """
    raise NotImplementedError(
        "Task Generator agent is not implemented. "
        "Tasks are currently served from the seeded DB pool via "
        "TaskRepository.find_for_plan(). "
        "Implement this when LLM-generated tasks are needed "
        "(post-MVP)."
    )
