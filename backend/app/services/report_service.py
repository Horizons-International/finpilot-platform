from datetime import date

from sqlalchemy.orm import Session

from app.repositories.report_repository import ReportRepository
from app.schemas.report import (
    DocumentSummaryResponse,
    VerificationSummaryResponse,
)
from app.utils.enums import DocumentStatus, VerificationStatus
from app.utils.errors import bad_request


class ReportService:
    def __init__(self, db: Session) -> None:
        self.repository = ReportRepository(db)

    @staticmethod
    def _validate_date_range(
        date_from: date | None,
        date_to: date | None,
    ) -> None:
        if date_from is not None and date_to is not None:
            if date_from > date_to:
                raise bad_request("date_from cannot be later than date_to.")

    def get_verification_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: VerificationStatus | None = None,
    ) -> VerificationSummaryResponse:
        self._validate_date_range(date_from, date_to)

        result = self.repository.get_verification_summary(
            date_from=date_from,
            date_to=date_to,
            status=status,
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

        result = self.repository.get_document_summary(
            date_from=date_from,
            date_to=date_to,
            status=status,
        )

        return DocumentSummaryResponse(**result)
