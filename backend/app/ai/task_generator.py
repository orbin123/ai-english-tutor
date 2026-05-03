"""Task Generator Agent — turns TaskTemplate schemas into real task content
by calling the LLM and validating the output against Pydantic models.

Usage:
    from app.ai.task_generator import TaskGeneratorAgent

    agent = TaskGeneratorAgent()
    content = await agent.generate(template, user_profile)
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.tasks.schemas import ALL_OUTPUT_MODELS
from app.tasks.schemas.base import (
    TaskTemplate,
    difficulty_tier_for_sublevel,
)

logger = logging.getLogger(__name__)


class TaskGeneratorAgent:
    """Generates task content by filling a TaskTemplate prompt, calling the LLM,
    and validating the response against the template's Pydantic output model.

    Stateless — safe to instantiate per-request or cache as a singleton.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
    ) -> None:
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = model
        self._temperature = temperature

    async def generate(
        self,
        template: TaskTemplate,
        user_profile: dict,
    ) -> dict:
        """Generate a single task from a template + user context.

        Args:
            template: The TaskTemplate defining the prompt and output schema.
            user_profile: Must include at minimum:
                - sub_level (int): 1–10
                - weak_areas (str): comma-separated weak grammar/skill areas
                - topic (str): context topic, e.g. "workplace"

        Returns:
            A dict of the validated Pydantic model (model.model_dump()).

        Raises:
            ValueError: If the LLM response fails Pydantic validation.
            openai.APIError: If the LLM call itself fails.
        """
        # 1. Determine difficulty tier from sub_level
        sub_level = user_profile.get("sub_level", 5)
        tier = difficulty_tier_for_sublevel(sub_level)

        # 2. Get modifiers for this tier
        modifiers = template.difficulty_modifiers.get(tier.value, {})

        # 3. Fill the prompt template with user data + modifiers
        prompt_vars = {**user_profile, **modifiers}
        try:
            filled_prompt = template.llm_prompt_template.format(**prompt_vars)
        except KeyError as exc:
            raise ValueError(
                f"Missing placeholder in prompt template: {exc}. "
                f"Available keys: {list(prompt_vars.keys())}"
            ) from exc

        logger.info(
            "Generating task for template=%s tier=%s model=%s",
            template.template_id,
            tier.value,
            self._model,
        )

        # 4. Build the JSON schema string for the output model
        output_model_cls = ALL_OUTPUT_MODELS.get(template.output_model_name)
        if output_model_cls is None:
            raise ValueError(
                f"Unknown output model: {template.output_model_name!r}. "
                f"Available: {list(ALL_OUTPUT_MODELS.keys())}"
            )

        schema_json = json.dumps(
            output_model_cls.model_json_schema(), indent=2, ensure_ascii=False
        )

        # 5. Call OpenAI with schema guidance
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a task content generator for an English learning app. "
                        "Return ONLY valid JSON that EXACTLY matches the JSON schema below. "
                        "Use the EXACT field names from the schema. "
                        "No markdown fences, no prose, no explanation.\n\n"
                        f"TARGET JSON SCHEMA:\n{schema_json}"
                    ),
                },
                {"role": "user", "content": filled_prompt},
            ],
            response_format={"type": "json_object"},
        )

        raw_text = response.choices[0].message.content
        logger.debug("LLM raw response (first 500 chars): %s", raw_text[:500])

        # 6. Parse JSON
        try:
            raw_data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM returned invalid JSON: {exc}\n"
                f"Raw response: {raw_text[:500]}"
            ) from exc

        # 7. Validate against the Pydantic model (already resolved at step 4)

        try:
            validated = output_model_cls.model_validate(raw_data)
        except Exception as exc:
            raise ValueError(
                f"LLM output failed validation for {template.output_model_name}: {exc}\n"
                f"Raw data keys: {list(raw_data.keys()) if isinstance(raw_data, dict) else type(raw_data)}"
            ) from exc

        # 7. Return as dict
        logger.info(
            "Task generated successfully: template=%s model=%s",
            template.template_id,
            template.output_model_name,
        )
        return validated.model_dump()
