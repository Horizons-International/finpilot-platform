from datetime import date, datetime, time, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.document import CustomerDocument
from app.models.verification_case import IdentityVerificationCase
from app.utils.enums import DocumentStatus, VerificationStatus


class ReportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _date_range(
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[datetime | None, datetime | None]:
        start_datetime = (
            datetime.combine(date_from, time.min) if date_from is not None else None
        )

        end_datetime = (
            datetime.combine(date_to + timedelta(days=1), time.min)
            if date_to is not None
            else None
        )

        return start_datetime, end_datetime

    def get_verification_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: VerificationStatus | None = None,
    ) -> dict[str, int]:
        start_datetime, end_datetime = self._date_range(
            date_from,
            date_to,
        )

        query = self.db.query(
            func.count(IdentityVerificationCase.id).label("total_cases"),
            func.sum(
                case(
                    (
                        IdentityVerificationCase.status == VerificationStatus.PENDING,
                        1,
                    ),
                    else_=0,
                )
            ).label("pending_cases"),
            func.sum(
                case(
                    (
                        IdentityVerificationCase.status == VerificationStatus.APPROVED,
                        1,
                    ),
                    else_=0,
                )
            ).label("approved_cases"),
            func.sum(
                case(
                    (
                        IdentityVerificationCase.status == VerificationStatus.REJECTED,
                        1,
                    ),
                    else_=0,
                )
            ).label("rejected_cases"),
        )

        if start_datetime is not None:
            query = query.filter(IdentityVerificationCase.created_at >= start_datetime)

        if end_datetime is not None:
            query = query.filter(IdentityVerificationCase.created_at < end_datetime)

        if status is not None:
            query = query.filter(IdentityVerificationCase.status == status)

        result = query.one()

        return {
            "total_cases": int(result.total_cases or 0),
            "pending_cases": int(result.pending_cases or 0),
            "approved_cases": int(result.approved_cases or 0),
            "rejected_cases": int(result.rejected_cases or 0),
        }

    def get_document_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: DocumentStatus | None = None,
    ) -> dict[str, int]:
        start_datetime, end_datetime = self._date_range(
            date_from,
            date_to,
        )

        query = self.db.query(
            func.count(CustomerDocument.id).label("uploaded_documents"),
            func.sum(
                case(
                    (
                        CustomerDocument.status == DocumentStatus.VERIFIED,
                        1,
                    ),
                    else_=0,
                )
            ).label("accepted_documents"),
            func.sum(
                case(
                    (
                        CustomerDocument.status == DocumentStatus.REJECTED,
                        1,
                    ),
                    else_=0,
                )
            ).label("rejected_documents"),
        )

        if start_datetime is not None:
            query = query.filter(CustomerDocument.created_at >= start_datetime)

        if end_datetime is not None:
            query = query.filter(CustomerDocument.created_at < end_datetime)

        if status is not None:
            query = query.filter(CustomerDocument.status == status)

        result = query.one()

        return {
            "uploaded_documents": int(result.uploaded_documents or 0),
            "accepted_documents": int(result.accepted_documents or 0),
            "rejected_documents": int(result.rejected_documents or 0),
        }
