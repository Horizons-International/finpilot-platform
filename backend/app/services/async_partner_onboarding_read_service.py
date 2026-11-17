"""Async read operations for platform-managed partner onboarding."""

import hashlib
import hmac
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.partner_onboarding import (
    PartnerOnboarding,
    PartnerOnboardingDocument,
    PartnerOnboardingHistory,
)
from app.schemas.partner_onboarding import (
    PartnerOnboardingAdministratorResponse,
    PartnerOnboardingDocumentResponse,
    PartnerOnboardingProgressResponse,
    PartnerOnboardingProgressStep,
)
from app.utils.date_time import utc_now
from app.utils.enums import PartnerOnboardingStatus
from app.utils.errors import not_found, unauthorized

REQUIRED_DOCUMENT_TYPES = {"business_registration", "regulatory_license"}


class AsyncPartnerOnboardingReadService:
    """Read partner-onboarding data without blocking the event loop.

    Partner onboarding requests are platform-level records created before a tenant
    exists. This service intentionally does not apply tenant scoping. Administrative
    endpoints must continue to enforce ``require_platform_admin`` at the API layer.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_requests(
        self,
        *,
        status: PartnerOnboardingStatus | None = None,
        assigned_to: UUID | None = None,
    ) -> list[PartnerOnboarding]:
        statement = select(PartnerOnboarding)
        if status is not None:
            statement = statement.where(PartnerOnboarding.status == status)
        if assigned_to is not None:
            statement = statement.where(PartnerOnboarding.assigned_to == assigned_to)
        statement = statement.order_by(PartnerOnboarding.created_at.desc())
        result = await self.db.scalars(statement)
        return list(result.all())

    async def get_request(self, onboarding_id: UUID) -> PartnerOnboarding:
        onboarding = await self.db.scalar(
            select(PartnerOnboarding).where(PartnerOnboarding.id == onboarding_id)
        )
        if onboarding is None:
            raise not_found("Partner onboarding request")
        return onboarding

    async def get_history(self, onboarding_id: UUID) -> list[PartnerOnboardingHistory]:
        # Keep the existing API behavior: a missing parent returns 404 rather than
        # an indistinguishable empty history list.
        await self.get_request(onboarding_id)
        result = await self.db.scalars(
            select(PartnerOnboardingHistory)
            .where(PartnerOnboardingHistory.onboarding_id == onboarding_id)
            .order_by(
                PartnerOnboardingHistory.created_at.asc(),
                PartnerOnboardingHistory.id.asc(),
            )
        )
        return list(result.all())

    async def list_documents(
        self, onboarding_id: UUID
    ) -> list[PartnerOnboardingDocument]:
        # Validate the parent first to preserve the previous progress-based lookup.
        await self.get_request(onboarding_id)
        result = await self.db.scalars(
            select(PartnerOnboardingDocument)
            .where(PartnerOnboardingDocument.onboarding_id == onboarding_id)
            .order_by(
                PartnerOnboardingDocument.created_at.desc(),
                PartnerOnboardingDocument.id.desc(),
            )
        )
        return list(result.all())

    async def get_internal_progress(
        self, onboarding_id: UUID
    ) -> PartnerOnboardingProgressResponse:
        onboarding = await self._get_progress_request(onboarding_id)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        return self._build_progress(onboarding)

    async def get_portal_progress(
        self,
        onboarding_id: UUID,
        *,
        token: str,
    ) -> PartnerOnboardingProgressResponse:
        onboarding = await self._get_progress_request(onboarding_id)

        # Do not reveal whether an onboarding ID exists without a valid portal
        # credential. Match the synchronous portal service's 404 behavior.
        if onboarding is None or not onboarding.portal_token_hash:
            raise not_found("Onboarding portal")

        supplied_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(onboarding.portal_token_hash, supplied_hash):
            raise not_found("Onboarding portal")
        if (
            onboarding.portal_token_expires_at is None
            or onboarding.portal_token_expires_at <= utc_now()
        ):
            raise unauthorized("Onboarding portal token has expired.")

        return self._build_progress(onboarding)

    async def _get_progress_request(
        self, onboarding_id: UUID
    ) -> PartnerOnboarding | None:
        """Load progress relationships eagerly to avoid async lazy-load I/O."""
        return await self.db.scalar(
            select(PartnerOnboarding)
            .options(
                selectinload(PartnerOnboarding.documents),
                selectinload(PartnerOnboarding.administrators),
            )
            .where(PartnerOnboarding.id == onboarding_id)
        )

    @staticmethod
    def _business_information_complete(onboarding: PartnerOnboarding) -> bool:
        required = (
            onboarding.organization_name,
            onboarding.legal_name,
            onboarding.registration_number,
            onboarding.tax_identification_number,
            onboarding.industry,
            onboarding.contact_name,
            onboarding.contact_email,
            onboarding.country,
        )
        return all(isinstance(value, str) and bool(value.strip()) for value in required)

    @staticmethod
    def _latest_documents(
        onboarding: PartnerOnboarding,
    ) -> dict[str, PartnerOnboardingDocument]:
        latest: dict[str, PartnerOnboardingDocument] = {}
        for document in sorted(
            onboarding.documents,
            key=lambda item: (item.created_at, str(item.id)),
        ):
            latest[document.document_type] = document
        return latest

    @classmethod
    def _build_progress(
        cls, onboarding: PartnerOnboarding
    ) -> PartnerOnboardingProgressResponse:
        """Build the same progress response used by the synchronous portal flow."""
        business_complete = cls._business_information_complete(onboarding)
        administrators_complete = bool(onboarding.administrators)
        latest = cls._latest_documents(onboarding)
        documents_complete = all(
            document_type in latest
            and latest[document_type].review_status != "REJECTED"
            for document_type in REQUIRED_DOCUMENT_TYPES
        )
        technical_complete = (
            onboarding.technical_setup_completed_at is not None
            and bool(onboarding.technical_setup)
        )
        activated = onboarding.status == PartnerOnboardingStatus.ACTIVE
        approved = all(
            document_type in latest
            and latest[document_type].review_status == "APPROVED"
            for document_type in REQUIRED_DOCUMENT_TYPES
        )

        step_data = [
            (
                "business_information",
                "Business information",
                business_complete,
                (
                    "Required legal entity and contact details are complete."
                    if business_complete
                    else (
                        "Provide the legal name, registration/tax numbers, industry "
                        "and contact details."
                    )
                ),
            ),
            (
                "administrators",
                "Add administrators",
                administrators_complete,
                (
                    f"{len(onboarding.administrators)} administrator(s) nominated."
                    if administrators_complete
                    else "Nominate at least one organization administrator."
                ),
            ),
            (
                "documents",
                "Submit required documents",
                documents_complete,
                (
                    "Required documents are submitted; internal approval is pending."
                    if documents_complete and not approved
                    else (
                        "Required business registration and regulatory license "
                        "documents are approved."
                        if approved
                        else (
                            "Upload business_registration and "
                            "regulatory_license documents."
                        )
                    )
                ),
            ),
            (
                "technical_setup",
                "Complete technical setup",
                technical_complete,
                (
                    "Technical setup details are saved."
                    if technical_complete
                    else (
                        "Provide the target environment, HTTPS callback URL and "
                        "integration contact."
                    )
                ),
            ),
            (
                "credentials",
                "Generate access credentials",
                activated,
                (
                    "The initial API key and administrator invitations were generated."
                    if activated
                    else (
                        "Credentials are issued only with "
                        "the approved account activation."
                    )
                ),
            ),
            (
                "activation",
                "Review and activation",
                activated,
                (
                    "The organization tenant has been activated."
                    if activated
                    else "Internal review and approval are not complete."
                ),
            ),
        ]
        steps = [
            PartnerOnboardingProgressStep(
                key=key, label=label, complete=complete, detail=detail
            )
            for key, label, complete, detail in step_data
        ]
        progress_percent = round(
            100 * sum(step.complete for step in steps) / len(steps)
        )

        return PartnerOnboardingProgressResponse(
            onboarding_id=onboarding.id,
            status=onboarding.status,
            progress_percent=progress_percent,
            steps=steps,
            documents=[
                PartnerOnboardingDocumentResponse.model_validate(document)
                for document in sorted(
                    onboarding.documents,
                    key=lambda row: (row.created_at, str(row.id)),
                    reverse=True,
                )
            ],
            administrators=[
                PartnerOnboardingAdministratorResponse.model_validate(administrator)
                for administrator in onboarding.administrators
            ],
            technical_setup=onboarding.technical_setup,
            created_at=onboarding.created_at,
            updated_at=onboarding.updated_at,
        )
