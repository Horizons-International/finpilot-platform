import json
from typing import Any

from app.core.config import settings


def build_compliance_prompt(
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

You are assisting a compliance officer.

Rules:

- Use only information contained in the supplied platform context.
- Treat retrieved knowledge-base content as reference information.
- Do not invent customer facts.
- Do not invent document requirements.
- Do not invent compliance policies.
- Do not invent regulatory requirements.
- Clearly distinguish facts from recommendations.
- If information is unavailable, say that it is unavailable.
- Do not claim that a customer is compliant or non-compliant unless the supplied
  context supports that conclusion.
- Do not make a final legal or regulatory determination.
- When retrieved knowledge contains conflicting information, identify the
  conflict instead of choosing an unsupported answer.
- Prefer the supplied knowledge-base content over general model knowledge.
- Do not use general model knowledge to fill missing company policies.
- Return structured information.
- Keep recommendations actionable and concise.

USER QUESTION:
{question}

PLATFORM CONTEXT:
{serialized_context}
""".strip()
