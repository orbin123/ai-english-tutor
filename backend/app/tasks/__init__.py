"""
LingosAI Task Engine.

This package houses LLM-driven task generation logic — distinct from
`app/modules/tasks/` which holds the database layer (SQLAlchemy models for
the `tasks` and `user_tasks` tables).

Layout:
    schemas/   — Static task templates + Pydantic validators for LLM output

When the Task Generator agent runs, it picks a template from `schemas/`,
fills the prompt, calls the LLM, validates the response, then persists
the validated dict into `Task.content` (JSONB) via the modules/tasks layer.
"""
