"""Build tenant-scoped compliance context with eager async ORM loading."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.models.customer import Customer
from app.models.customer_address import CustomerAddress
from app.models.customer_contact import CustomerContact
from app.models.document import CustomerDocument
from app.models.ocr_result import OCRResult
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_review import VerificationReview
from app.services.compliance_context_service import ComplianceContextService
from app.utils.enums import AIFunction, AIResourceType
from app.utils.errors import bad_request, not_found


class AsyncAIContextService:
    """Build the legacy compliance context without synchronous Session queries."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "AI context tenant does not match the active session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    def _tenant_loader_options(self) -> tuple[Any, ...]:
        tenant_id = self.tenant_id
        return (
            with_loader_criteria(
                Customer,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                CustomerAddress,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                CustomerContact,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                CustomerDocument,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                IdentityVerificationCase,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                OCRResult,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                VerificationReview,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
        )

    async def build_context(
        self,
        ai_function: AIFunction,
        *,
        customer_id: UUID | None = None,
        verification_case_id: UUID | None = None,
        document_id: UUID | None = None,
    ) -> tuple[dict[str, Any], AIResourceType, UUID]:
        if ai_function == AIFunction.CUSTOMER_SUMMARY:
            if customer_id is None:
                raise bad_request("customer_id is required for customer summaries.")
            customer = await self.db.scalar(
                select(Customer)
                .where(
                    Customer.id == customer_id,
                    Customer.tenant_id == self.tenant_id,
                )
                .options(
                    selectinload(Customer.addresses),
                    selectinload(Customer.contacts),
                    selectinload(Customer.verification_cases)
                    .selectinload(IdentityVerificationCase.documents)
                    .selectinload(CustomerDocument.ocr_results),
                    selectinload(Customer.verification_cases)
                    .selectinload(IdentityVerificationCase.documents)
                    .selectinload(CustomerDocument.document_type),
                    selectinload(Customer.verification_cases).selectinload(
                        IdentityVerificationCase.reviews
                    ),
                    *self._tenant_loader_options(),
                )
            )
            if customer is None:
                raise not_found("Customer")
            return (
                ComplianceContextService._serialize_customer(customer),
                AIResourceType.CUSTOMER,
                customer.id,
            )

        if ai_function in {
            AIFunction.CASE_SUMMARY,
            AIFunction.COMPLIANCE_NOTES,
        }:
            if verification_case_id is None:
                raise bad_request(
                    "verification_case_id is required for this AI function."
                )
            case = await self.db.scalar(
                select(IdentityVerificationCase)
                .where(
                    IdentityVerificationCase.id == verification_case_id,
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                )
                .options(
                    selectinload(IdentityVerificationCase.customer),
                    selectinload(IdentityVerificationCase.documents).selectinload(
                        CustomerDocument.ocr_results
                    ),
                    selectinload(IdentityVerificationCase.documents).selectinload(
                        CustomerDocument.document_type
                    ),
                    selectinload(IdentityVerificationCase.reviews),
                    *self._tenant_loader_options(),
                )
            )
            if case is None:
                raise not_found("Verification case")
            return (
                ComplianceContextService._serialize_case(case),
                AIResourceType.VERIFICATION_CASE,
                case.id,
            )

        if ai_function == AIFunction.DOCUMENT_REVIEW_SUMMARY:
            if document_id is None:
                raise bad_request(
                    "document_id is required for document review summaries."
                )
            document = await self.db.scalar(
                select(CustomerDocument)
                .where(
                    CustomerDocument.id == document_id,
                    CustomerDocument.tenant_id == self.tenant_id,
                )
                .options(
                    selectinload(CustomerDocument.customer),
                    selectinload(CustomerDocument.verification_case),
                    selectinload(CustomerDocument.document_type),
                    selectinload(CustomerDocument.ocr_results),
                    *self._tenant_loader_options(),
                )
            )
            if document is None:
                raise not_found("Customer document")
            return (
                ComplianceContextService._serialize_document(document),
                AIResourceType.DOCUMENT,
                document.id,
            )

        raise bad_request(
            f"Unsupported compliance assistant function: {ai_function.value}."
        )
