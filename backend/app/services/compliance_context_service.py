from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.document import CustomerDocument
from app.models.verification_case import IdentityVerificationCase
from app.repositories.compliance_context_repository import (
    ComplianceContextRepository,
)
from app.utils.enums import (
    AIFunction,
    AIResourceType,
)
from app.utils.errors import bad_request, not_found


class ComplianceContextService:
    def __init__(self, db: Session) -> None:
        self.repository = ComplianceContextRepository(db)

    def build_context(
        self,
        ai_function: AIFunction,
        *,
        customer_id: UUID | None = None,
        verification_case_id: UUID | None = None,
        document_id: UUID | None = None,
    ) -> tuple[dict[str, Any], AIResourceType, UUID]:
        if ai_function == AIFunction.CUSTOMER_SUMMARY:
            return self._build_customer_context(customer_id)

        if ai_function in {
            AIFunction.CASE_SUMMARY,
            AIFunction.COMPLIANCE_NOTES,
        }:
            return self._build_case_context(verification_case_id)

        if ai_function == AIFunction.DOCUMENT_REVIEW_SUMMARY:
            return self._build_document_context(document_id)

        raise bad_request(
            f"Unsupported compliance assistant function: {ai_function.value}."
        )

    def _build_customer_context(
        self,
        customer_id: UUID | None,
    ) -> tuple[dict[str, Any], AIResourceType, UUID]:
        if customer_id is None:
            raise bad_request("customer_id is required for customer summaries.")

        customer = self.repository.get_customer(customer_id)

        if customer is None:
            raise not_found("Customer")

        context = self._serialize_customer(customer)

        return (
            context,
            AIResourceType.CUSTOMER,
            customer.id,
        )

    def _build_case_context(
        self,
        verification_case_id: UUID | None,
    ) -> tuple[dict[str, Any], AIResourceType, UUID]:
        if verification_case_id is None:
            raise bad_request("verification_case_id is required for this AI function.")

        case = self.repository.get_verification_case(verification_case_id)

        if case is None:
            raise not_found("Verification case")

        context = self._serialize_case(case)

        return (
            context,
            AIResourceType.VERIFICATION_CASE,
            case.id,
        )

    def _build_document_context(
        self,
        document_id: UUID | None,
    ) -> tuple[dict[str, Any], AIResourceType, UUID]:
        if document_id is None:
            raise bad_request("document_id is required for document review summaries.")

        document = self.repository.get_document(document_id)

        if document is None:
            raise not_found("Customer document")

        context = self._serialize_document(document)

        return (
            context,
            AIResourceType.DOCUMENT,
            document.id,
        )

    @staticmethod
    def _serialize_customer(
        customer: Customer,
    ) -> dict[str, Any]:
        return {
            "customer": {
                "id": str(customer.id),
                "first_name": customer.first_name,
                "middle_name": customer.middle_name,
                "last_name": customer.last_name,
                "date_of_birth": (
                    customer.date_of_birth.isoformat()
                    if customer.date_of_birth
                    else None
                ),
                "nationality": customer.nationality,
                "country_of_residence": customer.country_of_residence,
                "email": customer.email,
                "phone_number": customer.phone_number,
                "status": customer.status.value,
            },
            "addresses": [
                {
                    "address_line_1": address.address_line_1,
                    "address_line_2": address.address_line_2,
                    "city": address.city,
                    "state": address.state,
                    "country": address.country,
                    "postal_code": address.postal_code,
                    "address_type": address.address_type.value,
                    "is_primary": address.is_primary,
                }
                for address in customer.addresses
            ],
            "contacts": [
                {
                    "phone_number": contact.phone_number,
                    "email": contact.email,
                    "phone_verified": contact.phone_verified,
                    "email_verified": contact.email_verified,
                    "preferred_contact_method": (
                        contact.preferred_contact_method.value
                        if contact.preferred_contact_method
                        else None
                    ),
                }
                for contact in customer.contacts
            ],
            "verification_cases": [
                ComplianceContextService._serialize_case_summary(case)
                for case in customer.verification_cases
            ],
        }

    @staticmethod
    def _serialize_case(
        case: IdentityVerificationCase,
    ) -> dict[str, Any]:
        return {
            "customer": {
                "id": str(case.customer.id),
                "first_name": case.customer.first_name,
                "middle_name": case.customer.middle_name,
                "last_name": case.customer.last_name,
                "nationality": case.customer.nationality,
                "country_of_residence": case.customer.country_of_residence,
                "status": case.customer.status.value,
            },
            "verification_case": {
                "id": str(case.id),
                "verification_type": case.verification_type.value,
                "status": case.status.value,
                "assigned_to": (str(case.assigned_to) if case.assigned_to else None),
                "completed_at": (
                    case.completed_at.isoformat() if case.completed_at else None
                ),
            },
            "documents": [
                ComplianceContextService._serialize_document(document)
                for document in case.documents
            ],
            "reviews": [
                {
                    "id": str(review.id),
                    "reviewer_id": str(review.reviewer_id),
                    "decision": review.decision.value,
                    "notes": review.notes,
                    "created_at": (
                        review.created_at.isoformat() if review.created_at else None
                    ),
                }
                for review in case.reviews
            ],
        }

    @staticmethod
    def _serialize_case_summary(
        case: IdentityVerificationCase,
    ) -> dict[str, Any]:
        return {
            "id": str(case.id),
            "verification_type": case.verification_type.value,
            "status": case.status.value,
            "assigned_to": (str(case.assigned_to) if case.assigned_to else None),
            "completed_at": (
                case.completed_at.isoformat() if case.completed_at else None
            ),
            "documents": [
                ComplianceContextService._serialize_document_summary(document)
                for document in case.documents
            ],
            "reviews": [
                {
                    "decision": review.decision.value,
                    "notes": review.notes,
                }
                for review in case.reviews
            ],
        }

    @staticmethod
    def _serialize_document(
        document: CustomerDocument,
    ) -> dict[str, Any]:
        return {
            "document": {
                "id": str(document.id),
                "file_name": document.file_name,
                "file_type": document.file_type,
                "file_size": document.file_size,
                "status": document.status.value,
                "document_type": (
                    document.document_type.name if document.document_type else None
                ),
            },
            "customer": {
                "id": str(document.customer.id),
                "first_name": document.customer.first_name,
                "last_name": document.customer.last_name,
                "status": document.customer.status.value,
            },
            "verification_case": (
                {
                    "id": str(document.verification_case.id),
                    "verification_type": (
                        document.verification_case.verification_type.value
                    ),
                    "status": document.verification_case.status.value,
                }
                if document.verification_case
                else None
            ),
            "ocr_results": [
                {
                    "provider_name": result.provider_name,
                    "status": result.status.value,
                    "extracted_text": result.extracted_text,
                    "error_message": result.error_message,
                }
                for result in document.ocr_results
            ],
        }

    @staticmethod
    def _serialize_document_summary(
        document: CustomerDocument,
    ) -> dict[str, Any]:
        return {
            "id": str(document.id),
            "file_name": document.file_name,
            "document_type": (
                document.document_type.name if document.document_type else None
            ),
            "status": document.status.value,
            "ocr_results": [
                {
                    "status": result.status.value,
                    "extracted_text": result.extracted_text,
                }
                for result in document.ocr_results
            ],
        }
