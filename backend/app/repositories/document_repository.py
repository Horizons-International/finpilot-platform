from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import CustomerDocument
from app.repositories.base_repository import BaseRepository


class CustomerDocumentRepository(BaseRepository[CustomerDocument]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, CustomerDocument)

    def get_by_id(
        self,
        document_id: UUID,
    ) -> CustomerDocument | None:
        return (
            self.db.query(CustomerDocument)
            .filter(CustomerDocument.id == document_id)
            .first()
        )

    def get_by_customer_id(
        self,
        customer_id: UUID,
    ) -> list[CustomerDocument]:
        return (
            self.db.query(CustomerDocument)
            .filter(CustomerDocument.customer_id == customer_id)
            .order_by(CustomerDocument.created_at.desc())
            .all()
        )

    def get_by_verification_case_id(
        self,
        verification_case_id: UUID,
    ) -> list[CustomerDocument]:
        return (
            self.db.query(CustomerDocument)
            .filter(CustomerDocument.verification_case_id == verification_case_id)
            .order_by(CustomerDocument.created_at.desc())
            .all()
        )

    def get_by_id_and_customer(
        self,
        document_id: UUID,
        customer_id: UUID,
    ) -> CustomerDocument | None:
        return (
            self.db.query(CustomerDocument)
            .filter(
                CustomerDocument.id == document_id,
                CustomerDocument.customer_id == customer_id,
            )
            .first()
        )

    def get_by_id_and_case(
        self,
        document_id: UUID,
        customer_id: UUID,
        verification_case_id: UUID,
    ) -> CustomerDocument | None:
        return (
            self.db.query(CustomerDocument)
            .filter(
                CustomerDocument.id == document_id,
                CustomerDocument.customer_id == customer_id,
                CustomerDocument.verification_case_id == verification_case_id,
            )
            .first()
        )
