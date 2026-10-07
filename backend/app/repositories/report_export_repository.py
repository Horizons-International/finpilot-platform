from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.report_export import ReportExport
from app.utils.date_time import utc_now
from app.utils.enums import ReportExportStatus


class ReportExportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        report_export: ReportExport,
    ) -> ReportExport:
        self.db.add(report_export)
        self.db.flush()
        self.db.refresh(report_export)

        return report_export

    def get_by_id(
        self,
        export_id: UUID,
    ) -> ReportExport | None:
        statement = select(ReportExport).where(
            ReportExport.id == export_id,
        )

        return self.db.scalars(statement).first()

    def list(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[ReportExport], int]:
        offset = (page - 1) * page_size

        statement = (
            select(ReportExport)
            .order_by(ReportExport.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        exports = list(self.db.scalars(statement).all())

        total = int(
            self.db.scalar(
                select(func.count(ReportExport.id)),
            )
            or 0
        )

        return exports, total

    def claim_next_requested(self) -> ReportExport | None:
        statement = (
            select(ReportExport)
            .where(
                ReportExport.status == ReportExportStatus.REQUESTED,
            )
            .order_by(ReportExport.created_at)
            .limit(1)
            .with_for_update(
                skip_locked=True,
            )
        )

        report_export = self.db.scalars(statement).first()

        if report_export is None:
            return None

        report_export.status = ReportExportStatus.PROCESSING
        report_export.started_at = utc_now()

        self.db.commit()
        self.db.refresh(report_export)

        return report_export

    def mark_completed(
        self,
        report_export: ReportExport,
        *,
        filename: str,
        content_type: str,
        storage_path: str,
        file_size: int,
        row_count: int,
    ) -> ReportExport:
        report_export.status = ReportExportStatus.COMPLETED
        report_export.filename = filename
        report_export.content_type = content_type
        report_export.storage_path = storage_path
        report_export.file_size = file_size
        report_export.row_count = row_count
        report_export.completed_at = utc_now()
        report_export.error_message = None

        self.db.commit()
        self.db.refresh(report_export)

        return report_export

    def mark_failed(
        self,
        report_export: ReportExport,
        *,
        error_message: str,
    ) -> ReportExport:
        report_export.status = ReportExportStatus.FAILED
        report_export.error_message = error_message[:2000]
        report_export.completed_at = utc_now()

        self.db.commit()
        self.db.refresh(report_export)

        return report_export
