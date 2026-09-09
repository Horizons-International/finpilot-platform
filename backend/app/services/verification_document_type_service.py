from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.verification_document_type import VerificationDocumentType
from app.repositories.verification_document_type_repository import (
    VerificationDocumentTypeRepository,
)
from app.schemas.verification_document_type import (
    VerificationDocumentTypeCreate,
    VerificationDocumentTypeUpdate,
)
from app.services.audit_service import AuditService
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, not_found


class VerificationDocumentTypeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = VerificationDocumentTypeRepository(db)
        self.audit_service = AuditService(db)

    def get_all(self) -> list[VerificationDocumentType]:
        return self.repository.get_all()

    def get_active(self) -> list[VerificationDocumentType]:
        return self.repository.get_active()

    def get_by_id(
        self,
        document_type_id: UUID,
    ) -> VerificationDocumentType:
        document_type = self.repository.get_by_id(document_type_id)

        if document_type is None:
            raise not_found("Verification document type")

        return document_type

    def create(
        self,
        data: VerificationDocumentTypeCreate,
        user_id: UUID,
        email: str,
    ) -> VerificationDocumentType:
        existing = self.repository.get_by_name(data.name)

        if existing is not None:
            raise bad_request(
                "A verification document type with this name already exists."
            )

        document_type = VerificationDocumentType(
            name=data.name,
            category=data.category,
            supported_countries=data.supported_countries,
            is_active=data.is_active,
        )

        try:
            document_type = self.repository.create(document_type)

            self.audit_service.log_event(
                event_type=AuditEventType.VERIFICATION_DOCUMENT_TYPE_CREATED,
                user_id=user_id,
                email=email,
                resource_type="verification_document_type",
                resource_id=document_type.id,
            )

            self.db.commit()
            self.db.refresh(document_type)

            return document_type

        except IntegrityError as exc:
            self.db.rollback()

            constraint_name = getattr(
                getattr(exc.orig, "diag", None),
                "constraint_name",
                None,
            )

            if constraint_name == "uq_verification_document_types_name":
                raise bad_request(
                    "A verification document type with this name already exists."
                ) from exc

            raise

    def update(
        self,
        document_type_id: UUID,
        data: VerificationDocumentTypeUpdate,
        user_id: UUID,
        email: str,
    ) -> VerificationDocumentType:
        document_type = self.repository.get_by_id(document_type_id)

        if document_type is None:
            raise not_found("Verification document type")

        changes = data.model_dump(exclude_unset=True)

        if "name" in changes and changes["name"] != document_type.name:
            existing = self.repository.get_by_name(changes["name"])

            if existing is not None and existing.id != document_type.id:
                raise bad_request(
                    "A verification document type with this name already exists."
                )

        status_changed = (
            "is_active" in changes and changes["is_active"] != document_type.is_active
        )

        for field, value in changes.items():
            setattr(document_type, field, value)

        try:
            document_type = self.repository.update(document_type)

            self.audit_service.log_event(
                event_type=(
                    AuditEventType.VERIFICATION_DOCUMENT_TYPE_STATUS_CHANGED
                    if status_changed
                    else AuditEventType.VERIFICATION_DOCUMENT_TYPE_UPDATED
                ),
                user_id=user_id,
                email=email,
                resource_type="verification_document_type",
                resource_id=document_type.id,
            )

            self.db.commit()
            self.db.refresh(document_type)

            return document_type

        except IntegrityError as exc:
            self.db.rollback()

            constraint_name = getattr(
                getattr(exc.orig, "diag", None),
                "constraint_name",
                None,
            )

            if constraint_name == "uq_verification_document_types_name":
                raise bad_request(
                    "A verification document type with this name already exists."
                ) from exc

            raise
