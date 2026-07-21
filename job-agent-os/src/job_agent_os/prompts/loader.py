"""Prompt loader (YAML file + DB dual source)."""

import os
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template

# Base path for prompt templates
TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_prompt(key: str, variables: dict[str, Any] | None = None) -> tuple[str, str]:
    """Load a prompt template by key and render with variables.

    Args:
        key: Prompt key (e.g., "intent_parse", "structure_jd")
        variables: Variables to render in the template

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    variables = variables or {}

    # Map key to file path
    key_to_path = {
        "intent_parse": "intent/parse_intent.yaml",
        "structure_jd": "parse/structure_jd.yaml",
        "score_and_rank": "match/score_and_rank.yaml",
        "optimize_resume": "resume/optimize_resume.yaml",
        "tech_questions": "interview/tech_questions.yaml",
        "behavior_questions": "interview/behavior_questions.yaml",
    }

    file_path = TEMPLATES_DIR / key_to_path.get(key, f"{key}.yaml")

    if not file_path.exists():
        # Return default prompts if file not found
        return (
            f"You are a helpful assistant for {key}.",
            f"Please process the following: {{{{ input }}}}",
        )

    with open(file_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    system_prompt = config.get("system", "")
    user_template = config.get("user_template", "")

    # Render templates with Jinja2
    system_rendered = Template(system_prompt).render(**variables)
    user_rendered = Template(user_template).render(**variables)

    return system_rendered, user_rendered


def get_prompt_config(key: str) -> dict[str, Any]:
    """Get full prompt configuration including model settings."""
    key_to_path = {
        "intent_parse": "intent/parse_intent.yaml",
        "structure_jd": "parse/structure_jd.yaml",
        "score_and_rank": "match/score_and_rank.yaml",
        "optimize_resume": "resume/optimize_resume.yaml",
        "tech_questions": "interview/tech_questions.yaml",
        "behavior_questions": "interview/behavior_questions.yaml",
    }

    file_path = TEMPLATES_DIR / key_to_path.get(key, f"{key}.yaml")

    if not file_path.exists():
        return {}

    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f)
