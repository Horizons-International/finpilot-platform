from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.ai_prompt import AIPrompt
from app.models.ai_prompt_assignment import AIPromptAssignment
from app.models.user import User
from app.utils.enums import (
    AIFunction,
    AIPromptStatus,
    UserRole,
    UserStatus,
)

AI_SYSTEM_USER_EMAIL = "aisystem@example.com"


AI_PROMPTS = (
    {
        "name": "case-summary",
        "purpose": "Summarize a customer's compliance and verification case",
        "prompt_text": (
            "You are a compliance assistant. Summarize the customer's "
            "verification case using only the information provided in the "
            "context. Identify the current verification status, relevant "
            "verification information, missing documents or information, "
            "important findings, and any required follow-up actions. "
            "Do not invent facts. Return a concise structured summary."
        ),
        "ai_function": AIFunction.CASE_SUMMARY,
    },
    {
        "name": "customer-summary",
        "purpose": "Summarize customer information relevant to compliance review",
        "prompt_text": (
            "You are a compliance assistant. Summarize the customer's "
            "information using only the information provided in the context. "
            "Include relevant identity information, contact information, "
            "nationality, country of residence, customer status, and other "
            "compliance-relevant information available in the context. "
            "Do not invent or infer facts that are not explicitly provided. "
            "Return a concise structured summary."
        ),
        "ai_function": AIFunction.CUSTOMER_SUMMARY,
    },
    {
        "name": "document-review-summary",
        "purpose": "Summarize customer documents and document review findings",
        "prompt_text": (
            "You are a compliance document review assistant. Review the "
            "document information and extracted content provided in the "
            "context. Summarize the document type, available document "
            "information, extraction results, verification findings, missing "
            "information, inconsistencies, and potential issues. Use only "
            "the provided information. Do not invent facts. Clearly "
            "distinguish between confirmed information and potential issues."
        ),
        "ai_function": AIFunction.DOCUMENT_REVIEW_SUMMARY,
    },
    {
        "name": "compliance-notes",
        "purpose": "Generate structured compliance review notes",
        "prompt_text": (
            "You are a compliance review assistant. Generate concise "
            "compliance notes using only the customer, verification case, "
            "document, and review information provided in the context. "
            "Identify relevant findings, outstanding issues, missing "
            "information, and suggested follow-up actions. Do not make "
            "unsupported allegations or invent facts. Clearly distinguish "
            "facts from observations and recommendations."
        ),
        "ai_function": AIFunction.COMPLIANCE_NOTES,
    },
)


def get_or_create_ai_system_user(db: Session) -> User:
    user = db.query(User).filter(User.email == AI_SYSTEM_USER_EMAIL).first()

    if user is not None:
        return user

    user = User(
        id=UUID("00000000-0000-0000-0000-000000000010"),
        first_name="AI",
        last_name="System",
        email=AI_SYSTEM_USER_EMAIL,
        password_hash=hash_password(uuid4().hex),
        status=UserStatus.INACTIVE,
        role=UserRole.ADMINISTRATOR,
        is_deleted=False,
    )

    db.add(user)
    db.flush()

    return user


def seed_ai_prompts(db: Session) -> None:
    system_user = get_or_create_ai_system_user(db)

    for prompt_data in AI_PROMPTS:
        prompt = (
            db.query(AIPrompt)
            .filter(AIPrompt.name == prompt_data["name"])
            .order_by(AIPrompt.version.desc())
            .first()
        )

        if prompt is None:
            prompt = AIPrompt(
                name=prompt_data["name"],
                purpose=prompt_data["purpose"],
                prompt_text=prompt_data["prompt_text"],
                version=1,
                status=AIPromptStatus.ACTIVE,
                created_by=system_user.id,
            )

            db.add(prompt)
            db.flush()

        assignment = (
            db.query(AIPromptAssignment)
            .filter(AIPromptAssignment.ai_function == prompt_data["ai_function"])
            .first()
        )

        if assignment is None:
            db.add(
                AIPromptAssignment(
                    ai_function=prompt_data["ai_function"],
                    prompt_id=prompt.id,
                )
            )
        elif assignment.prompt_id != prompt.id:
            assignment.prompt_id = prompt.id

    db.commit()
