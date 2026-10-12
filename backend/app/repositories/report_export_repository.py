from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.report_export import ReportExport
from app.models.user import User
from app.utils.date_time import utc_now
from app.utils.enums import ReportExportStatus


class ReportExportRepository:
    """Tenant-scoped report exports, including worker claim/update operations."""

    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for report exports.")
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != resolved_tenant_id:
            raise ValueError(
                "The SQLAlchemy session is already bound to another tenant."
            )
        # Also scope relationship/lazy loads covered by tenant_filter.py.
        db.info["tenant_id"] = resolved_tenant_id

        self.db = db
        self.tenant_id = resolved_tenant_id

    def _owned_statement(self, export_id: UUID):
        return select(ReportExport).where(
            ReportExport.id == export_id,
            ReportExport.tenant_id == self.tenant_id,
        )

    def _assert_owned(self, report_export: ReportExport) -> None:
        if report_export.tenant_id != self.tenant_id:
            raise ValueError("Cannot modify a report export owned by another tenant.")

        exists = self.db.scalar(
            select(ReportExport.id).where(
                ReportExport.id == report_export.id,
                ReportExport.tenant_id == self.tenant_id,
            )
        )
        if exists is None:
            raise ValueError("Report export does not belong to the current tenant.")

    def _validate_requester(self, requested_by: UUID | None) -> None:
        if requested_by is None:
            return
        requester = self.db.scalar(
            select(User.id).where(
                User.id == requested_by,
                User.tenant_id == self.tenant_id,
            )
        )
        if requester is None:
            raise ValueError("Report requester does not belong to the current tenant.")

    def create(self, report_export: ReportExport) -> ReportExport:
        if (
            report_export.tenant_id is not None
            and report_export.tenant_id != self.tenant_id
        ):
            raise ValueError("Cannot create a report export for another tenant.")

        self._validate_requester(report_export.requested_by)
        report_export.tenant_id = self.tenant_id
        self.db.add(report_export)
        self.db.flush()
        self.db.refresh(report_export)
        return report_export

    def get_by_id(self, export_id: UUID) -> ReportExport | None:
        return self.db.scalars(self._owned_statement(export_id)).first()

    def list(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[ReportExport], int]:
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive integers.")

        offset = (page - 1) * page_size
        statement = (
            select(ReportExport)
            .where(ReportExport.tenant_id == self.tenant_id)
            .order_by(ReportExport.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        exports = list(self.db.scalars(statement).all())

        count_statement = select(func.count(ReportExport.id)).where(
            ReportExport.tenant_id == self.tenant_id,
        )
        total = int(self.db.scalar(count_statement) or 0)
        return exports, total

    def claim_next_requested(self) -> ReportExport | None:
        """Claim only this tenant's next export; workers should iterate tenants."""
        statement = (
            select(ReportExport)
            .where(
                ReportExport.tenant_id == self.tenant_id,
                ReportExport.status == ReportExportStatus.REQUESTED,
            )
            .order_by(ReportExport.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
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
        self._assert_owned(report_export)
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
        self._assert_owned(report_export)
        report_export.status = ReportExportStatus.FAILED
        report_export.error_message = error_message[:2000]
        report_export.completed_at = utc_now()
        self.db.commit()
        self.db.refresh(report_export)
        return report_export
