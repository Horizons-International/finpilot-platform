from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.report_export import ReportExport
from app.reporting.data_service import ReportingDataService
from app.reporting.generator import ReportGenerator
from app.repositories.report_export_repository import (
    ReportExportRepository,
)
from app.schemas.report_exports import (
    ReportExportRequest,
)
from app.services.notification_service import NotificationService
from app.storages.base_storage import BaseStorage
from app.utils.date_time import utc_now
from app.utils.enums import (
    NotificationChannel,
    NotificationEventType,
    ReportExportStatus,
)
from app.utils.errors import bad_request, not_found


class ReportExportService:
    def __init__(
        self,
        db: Session,
        storage: BaseStorage,
    ) -> None:
        self.db = db
        self.repository = ReportExportRepository(db)
        self.data_service = ReportingDataService(db)
        self.generator = ReportGenerator()
        self.storage = storage
        self.notification_service = NotificationService(db)

    def request_export(
        self,
        *,
        request: ReportExportRequest,
        requested_by: UUID,
    ) -> ReportExport:
        row_count = self.data_service.count_rows(
            report_type=request.report_type,
            filters=request.filters,
        )

        if row_count > settings.REPORT_MAX_ROWS:
            raise bad_request(
                "The requested report is too large. "
                f"The maximum supported size is "
                f"{settings.REPORT_MAX_ROWS:,} rows."
            )

        report_export = ReportExport(
            report_type=request.report_type,
            format=request.format,
            requested_by=requested_by,
            filters=request.filters.model_dump(
                mode="json",
                exclude_none=True,
            ),
            status=ReportExportStatus.REQUESTED,
            row_count=row_count,
        )

        self.repository.create(
            report_export,
        )

        self.db.commit()
        self.db.refresh(report_export)

        should_run_async = (
            request.prefer_async or row_count > settings.REPORT_ASYNC_ROW_THRESHOLD
        )

        if not should_run_async:
            self.process_export(
                export_id=report_export.id,
            )

            updated_report_export = self.repository.get_by_id(
                report_export.id,
            )

            if updated_report_export is None:
                raise RuntimeError(
                    "Report export disappeared after generation.",
                )

            report_export = updated_report_export

        return report_export

    def process_export(
        self,
        *,
        export_id: UUID,
    ) -> ReportExport | None:
        report_export = self.repository.get_by_id(
            export_id,
        )

        if report_export is None:
            return None

        if report_export.status not in (
            ReportExportStatus.REQUESTED,
            ReportExportStatus.PROCESSING,
        ):
            return report_export

        try:
            if report_export.status == ReportExportStatus.REQUESTED:
                report_export.status = ReportExportStatus.PROCESSING
                report_export.started_at = utc_now()

                self.db.commit()
                self.db.refresh(report_export)

            filters = self._filters_from_dict(
                report_export.filters,
            )

            table = self.data_service.build_report(
                report_type=report_export.report_type,
                filters=filters,
            )

            content = self.generator.generate(
                table=table,
                format=report_export.format,
            )

            timestamp = utc_now().strftime(
                "%Y%m%dT%H%M%SZ",
            )

            extension = self.generator.extension(
                report_export.format,
            )

            filename = (
                "finpilot_"
                f"{report_export.report_type.value.lower()}_"
                f"{timestamp}."
                f"{extension}"
            )

            storage_path = self.storage.save(
                file_content=content,
                filename=filename,
                folder="reports",
            )

            completed = self.repository.mark_completed(
                report_export,
                filename=filename,
                content_type=self.generator.content_type(
                    report_export.format,
                ),
                storage_path=storage_path,
                file_size=len(content),
                row_count=len(table.rows),
            )

            self.notification_service.create_notification(
                user_id=completed.requested_by,
                title="Report ready",
                message=(
                    f"Your {completed.report_type.value.lower()} "
                    "report is ready for download."
                ),
                event_type=NotificationEventType.REPORT_GENERATED,
                resource_type="report_export",
                resource_id=completed.id,
                channels=(NotificationChannel.IN_APP,),
            )

            self.db.commit()

            return completed

        except Exception as exc:
            self.db.rollback()

            failed = self.repository.get_by_id(
                export_id,
            )

            if failed is not None:
                failed = self.repository.mark_failed(
                    failed,
                    error_message=str(exc),
                )

                try:
                    self.notification_service.create_notification(
                        user_id=failed.requested_by,
                        title="Report generation failed",
                        message=(
                            f"Your {failed.report_type.value.lower()} "
                            "report could not be generated."
                        ),
                        event_type=(NotificationEventType.REPORT_GENERATION_FAILED),
                        resource_type="report_export",
                        resource_id=failed.id,
                        channels=(NotificationChannel.IN_APP,),
                    )

                    self.db.commit()

                except Exception:
                    self.db.rollback()

            raise

    @staticmethod
    def _filters_from_dict(
        filters: dict,
    ):
        from app.schemas.report_exports import ReportFilters

        return ReportFilters.model_validate(filters)

    def get_export(
        self,
        *,
        export_id: UUID,
    ) -> ReportExport:
        report_export = self.repository.get_by_id(
            export_id,
        )

        if report_export is None:
            raise not_found("Report export")

        return report_export

    def list_exports(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[ReportExport], int]:
        return self.repository.list(
            page=page,
            page_size=page_size,
        )

    def read_export_file(
        self,
        *,
        export_id: UUID,
    ) -> tuple[ReportExport, bytes]:
        report_export = self.get_export(
            export_id=export_id,
        )

        if report_export.status != ReportExportStatus.COMPLETED:
            raise bad_request(
                "The report is not ready for download.",
            )

        if not report_export.storage_path:
            raise bad_request(
                "The generated report file is unavailable.",
            )

        if not self.storage.exists(
            report_export.storage_path,
        ):
            raise not_found("Report file")

        content = self.storage.read(
            report_export.storage_path,
        )

        return report_export, content
