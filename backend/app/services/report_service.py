from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.report_repository import ReportRepository
from app.schemas.report import DocumentSummaryResponse, VerificationSummaryResponse
from app.services.tenant_context import resolve_tenant_context
from app.utils.enums import DocumentStatus, VerificationStatus
from app.utils.errors import bad_request


class ReportService:
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        self.db = db
        self._requested_tenant_id = tenant_id
        self.tenant_id: UUID | None = tenant_id
        self.repository: ReportRepository | None = None

    def _repository(self) -> ReportRepository:
        if self.repository is None:
            self.tenant_id = resolve_tenant_context(
                self.db,
                self._requested_tenant_id,
                resource_name="verification and document reports",
            )
            self.repository = ReportRepository(self.db, tenant_id=self.tenant_id)
        return self.repository

    @staticmethod
    def _validate_date_range(date_from: date | None, date_to: date | None) -> None:
        if date_from is not None and date_to is not None and date_from > date_to:
            raise bad_request("date_from cannot be later than date_to.")

    def get_verification_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: VerificationStatus | None = None,
    ) -> VerificationSummaryResponse:
        self._validate_date_range(date_from, date_to)
        result = self._repository().get_verification_summary(
            date_from=date_from, date_to=date_to, status=status
        )
        return VerificationSummaryResponse(**result)

    def get_document_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: DocumentStatus | None = None,
    ) -> DocumentSummaryResponse:
        self._validate_date_range(date_from, date_to)
        result = self._repository().get_document_summary(
            date_from=date_from, date_to=date_to, status=status
        )
        return DocumentSummaryResponse(**result)
