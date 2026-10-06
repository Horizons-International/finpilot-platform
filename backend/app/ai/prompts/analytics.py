import json
from typing import Any

from app.core.config import settings


def build_analytics_prompt(
    *,
    system_prompt: str,
    question: str,
    context: dict[str, Any],
) -> str:
    serialized_context = json.dumps(
        context,
        indent=2,
        default=str,
    )

    max_context_characters = settings.AI_MAX_CONTEXT_CHARACTERS

    if len(serialized_context) > max_context_characters:
        serialized_context = serialized_context[:max_context_characters]

        serialized_context += "\n\n[CONTEXT TRUNCATED]"

    return f"""
{system_prompt}

You are FinPilot's business analytics assistant.

Rules:

- Use only the supplied analytics evidence and platform context.
- The analytics evidence is authoritative for numerical answers.
- Do not invent numbers.
- Do not invent trends.
- Do not invent business facts.
- Do not infer missing data as though it were known.
- When comparison data is unavailable, explicitly say so.
- When percentage change cannot be calculated because the comparison value is
  zero or unavailable, say that it is not calculable.
- Use the requested reporting period exactly as supplied.
- Clearly distinguish current values from comparison values.
- Give a concise business-focused answer.
- Produce 1 to 3 suggested insights when the data supports them.
- Suggested insights must be directly supported by the supplied data.
- Do not provide legal or regulatory conclusions.

Return structured information containing:

1. summary
2. suggested_insights
3. confidence

USER QUESTION:
{question}

ANALYTICS CONTEXT:
{serialized_context}
""".strip()
