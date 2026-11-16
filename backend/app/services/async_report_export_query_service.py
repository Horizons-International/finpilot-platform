"""Async, tenant-scoped reads for report export history and status."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_export import ReportExport
from app.services.async_tenant_access_audit import deny_tenant_access


class AsyncReportExportQueryService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "Report export tenant does not match the active session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    async def get_export(self, export_id: UUID) -> ReportExport:
        report_export = await self.db.scalar(
            select(ReportExport).where(
                ReportExport.id == export_id,
                ReportExport.tenant_id == self.tenant_id,
            )
        )
        if report_export is None:
            await deny_tenant_access(
                self.db,
                resource_type="report_export",
                resource_id=export_id,
                resource_name="Report export",
            )
        return report_export

    async def list_exports(
        self, *, page: int, page_size: int
    ) -> tuple[list[ReportExport], int]:
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive integers.")
        statement = (
            select(ReportExport)
            .where(ReportExport.tenant_id == self.tenant_id)
            .order_by(ReportExport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = await self.db.scalars(statement)
        total = int(
            await self.db.scalar(
                select(func.count(ReportExport.id)).where(
                    ReportExport.tenant_id == self.tenant_id
                )
            )
            or 0
        )
        return list(rows.all()), total
