import json
from typing import Any


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

    return f"""
{system_prompt}

You are assisting a compliance officer.

Rules:
- Use only information contained in the supplied platform context.
- Do not invent customer facts.
- Do not invent document requirements.
- Do not invent compliance policies.
- Clearly distinguish facts from recommendations.
- If information is unavailable, say that it is unavailable.
- Do not claim that a customer is compliant or non-compliant unless the supplied
  context supports that conclusion.
- Do not make a final legal or regulatory determination.
- Return structured information.
- Keep recommendations actionable and concise.

USER QUESTION:
{question}

PLATFORM CONTEXT:
{serialized_context}
""".strip()
