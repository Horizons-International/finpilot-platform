"""Tenant-safe product usage analytics assembled from FinPilot's existing logs.

This intentionally reuses the audit/security, AI usage, workflow, and reporting
records instead of duplicating every request into another high-volume table.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.tenant_context import resolve_tenant_id
from app.models.ai_usage_log import AIUsageLog
from app.models.audit_log import AuditLog
from app.models.report_export import ReportExport
from app.models.security_event import SecurityEvent
from app.models.tenant import Tenant
from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import WorkflowExecution
from app.schemas.product_usage_analytics import (
    CustomerProductUsageSummary,
    ProductFeatureUsage,
    ProductUsageDashboardResponse,
    ProductUsageFeatureReport,
)
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, not_found

FEATURE_NAMES: dict[str, str] = {
    "customer_management": "Customer management",
    "verification": "Identity verification",
    "ai_services": "AI services and assistant",
    "workflows": "Workflows and task automation",
    "reporting": "Reports and analytics",
    "document_management": "Documents and extraction",
    "integrations": "Integrations and API keys",
    "support": "Support tickets",
    "developer_platform": "Developer portal and sandbox",
    "customer_success": "Customer success",
    "risk_monitoring": "Risk and transaction monitoring",
}

# The existing SecurityMonitoringMiddleware writes one tenant-linked event per
# authenticated request, including API-key requests and common rejected calls.
USAGE_EVENT_TYPES = (
    "API_ACCESS",
    "API_KEY_ACCESS",
    "REQUEST_REJECTED",
    "AUTHENTICATION_REJECTED",
    "AUTHORIZATION_DENIED",
    "REQUEST_TOO_LARGE",
    "INPUT_VALIDATION_REJECTED",
    "RATE_LIMIT_EXCEEDED",
)

ANALYTICS_PATH_PREFIX = "/api/v1/product-analytics"


def _feature_for_path(path: str | None) -> str | None:
    if not path or not path.startswith("/api/"):
        return None
    if path.startswith(ANALYTICS_PATH_PREFIX):
        return None

    # Match customer verification subroutes before generic customer management.
    if path.startswith("/api/v1/verification") or (
        path.startswith("/api/v1/customers/") and "verification" in path
    ):
        return "verification"
    if path.startswith(("/api/v1/ai", "/api/v1/rag", "/api/v1/case-priorities")):
        return "ai_services"
    if path.startswith(
        (
            "/api/v1/transaction-monitoring",
            "/api/v1/transaction-risk-analysis",
            "/api/v1/transaction-anomalies",
            "/api/v1/risk-scoring",
            "/api/v1/risk-predictions",
            "/api/v1/aml-rules",
            "/api/v1/compliance-cases",
        )
    ):
        return "risk_monitoring"
    if path.startswith(
        ("/api/v1/workflows", "/api/v1/tasks", "/api/v1/task-assignment-rules")
    ):
        return "workflows"
    if path.startswith(
        (
            "/api/v1/reports",
            "/api/v1/report-exports",
            "/api/v1/analytics",
            "/api/v1/metrics",
            "/api/v1/executive-dashboard",
        )
    ):
        return "reporting"
    if path.startswith(
        (
            "/api/v1/files",
            "/api/v1/documents",
            "/api/v1/ocr",
            "/api/v1/extraction",
            "/api/v1/document-review",
            "/api/v1/knowledge-documents",
        )
    ):
        return "document_management"
    if path.startswith(
        (
            "/api/v1/integrations",
            "/api/v1/integration-management",
            "/api/v1/webhooks",
            "/api/v1/api-keys",
        )
    ):
        return "integrations"
    if path.startswith(("/api/v1/support-tickets", "/api/v1/support")):
        return "support"
    if path.startswith(
        (
            "/api/v1/developer-portal",
            "/api/v1/sandbox",
            "/api/v1/implementation-workspaces",
            "/api/v1/partner-onboarding",
        )
    ):
        return "developer_platform"
    if path.startswith("/api/v1/customer-success"):
        return "customer_success"
    if path.startswith("/api/v1/customers"):
        return "customer_management"
    return None


class ProductUsageAnalyticsService:
    """Generate date-filtered usage summaries with explicit tenant permissions."""

    def __init__(
        self,
        db: Session,
        *,
        owner_tenant_id: UUID,
        cross_tenant_access: bool = False,
        tenant_filter_id: UUID | None = None,
    ) -> None:
        self.db = db
        self.owner_tenant_id = owner_tenant_id
        self.cross_tenant_access = cross_tenant_access
        self.tenant_filter_id = tenant_filter_id
        session_tenant = db.info.get("tenant_id")
        if session_tenant is not None and session_tenant != owner_tenant_id:
            raise ValueError("The database session is already bound to another tenant.")
        if not cross_tenant_access:
            self.owner_tenant_id = resolve_tenant_id(db, owner_tenant_id)
            if tenant_filter_id is not None and tenant_filter_id != owner_tenant_id:
                raise ValueError(
                    "Tenant filter does not match the authenticated tenant."
                )
            self.tenant_filter_id = owner_tenant_id

    @staticmethod
    def _validate_dates(start_date: date, end_date: date) -> None:
        if end_date < start_date:
            raise bad_request("end_date must be on or after start_date.")
        if (end_date - start_date).days > 366:
            raise bad_request(
                "Usage reports are limited to 367 calendar days per request."
            )

    @staticmethod
    def _range_filters(
        timestamp_column: Any, start_date: date, end_date: date
    ) -> list[Any]:
        start_at = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_exclusive = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
        )
        return [timestamp_column >= start_at, timestamp_column < end_exclusive]

    def _apply_scope(self, statement: Any, tenant_column: Any) -> Any:
        if self.cross_tenant_access:
            if self.tenant_filter_id is not None:
                statement = statement.where(tenant_column == self.tenant_filter_id)
            return statement.execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "Product usage analytics cross-tenant aggregation restricted "
                    "to authenticated users with the trusted platform-admin flag"
                ),
            )
        return statement.where(tenant_column == self.owner_tenant_id)

    def _count_by_tenant(
        self,
        model: Any,
        timestamp_column: Any,
        start_date: date,
        end_date: date,
        *,
        filters: tuple[Any, ...] = (),
    ) -> dict[UUID, int]:
        statement = (
            select(model.tenant_id, func.count(model.id))
            .where(
                *self._range_filters(timestamp_column, start_date, end_date), *filters
            )
            .where(model.tenant_id.is_not(None))
            .group_by(model.tenant_id)
        )
        statement = self._apply_scope(statement, model.tenant_id)
        counts: dict[UUID, int] = {}
        for tenant_id, count in self.db.execute(statement).all():
            # The SQL predicate excludes NULL tenants, but the ORM type remains
            # Optional because the column is nullable on some source tables.
            if tenant_id is not None:
                counts[tenant_id] = int(count)
        return counts

    def _feature_usage_by_tenant(
        self, start_date: date, end_date: date
    ) -> dict[UUID, dict[str, int]]:
        statement = (
            select(
                SecurityEvent.tenant_id,
                SecurityEvent.request_path,
                func.count(SecurityEvent.id),
            )
            .where(
                *self._range_filters(SecurityEvent.timestamp, start_date, end_date),
                SecurityEvent.event_type.in_(USAGE_EVENT_TYPES),
                SecurityEvent.request_path.is_not(None),
                SecurityEvent.request_path.like("/api/%"),
                SecurityEvent.request_path.not_like(f"{ANALYTICS_PATH_PREFIX}%"),
                SecurityEvent.tenant_id.is_not(None),
            )
            .group_by(SecurityEvent.tenant_id, SecurityEvent.request_path)
        )
        statement = self._apply_scope(statement, SecurityEvent.tenant_id)
        result: dict[UUID, dict[str, int]] = {}
        for tenant_id, path, count in self.db.execute(statement).all():
            if tenant_id is None:
                continue
            feature = _feature_for_path(path)
            if feature is not None:
                counts = result.setdefault(tenant_id, {})
                counts[feature] = counts.get(feature, 0) + int(count)
        return result

    def _tenant_rows(self) -> list[tuple[UUID, str]]:
        statement = select(Tenant.id, Tenant.name)
        if self.tenant_filter_id is not None:
            statement = statement.where(Tenant.id == self.tenant_filter_id)
        elif not self.cross_tenant_access:
            statement = statement.where(Tenant.id == self.owner_tenant_id)
        rows = [
            (tenant_id, name) for tenant_id, name in self.db.execute(statement).all()
        ]
        if not rows and self.tenant_filter_id is not None:
            raise not_found("Tenant")
        if not rows and not self.cross_tenant_access:
            raise not_found("Tenant")
        return rows

    @staticmethod
    def _feature_items(counts: dict[str, int]) -> list[ProductFeatureUsage]:
        return [
            ProductFeatureUsage(
                feature_key=key,
                feature_name=name,
                request_count=counts.get(key, 0),
            )
            for key, name in FEATURE_NAMES.items()
        ]

    def dashboard(
        self, *, start_date: date, end_date: date
    ) -> ProductUsageDashboardResponse:
        self._validate_dates(start_date, end_date)
        tenants = self._tenant_rows()
        tenant_ids = {tenant_id for tenant_id, _ in tenants}

        api_filters = (
            SecurityEvent.event_type.in_(USAGE_EVENT_TYPES),
            SecurityEvent.request_path.like("/api/%"),
            SecurityEvent.request_path.not_like(f"{ANALYTICS_PATH_PREFIX}%"),
        )
        login_counts = self._count_by_tenant(
            AuditLog,
            AuditLog.timestamp,
            start_date,
            end_date,
            filters=(AuditLog.event_type == AuditEventType.LOGIN_SUCCESS,),
        )
        api_counts = self._count_by_tenant(
            SecurityEvent,
            SecurityEvent.timestamp,
            start_date,
            end_date,
            filters=api_filters,
        )
        verification_counts = self._count_by_tenant(
            IdentityVerificationCase,
            IdentityVerificationCase.created_at,
            start_date,
            end_date,
        )
        ai_counts = self._count_by_tenant(
            AIUsageLog,
            AIUsageLog.created_at,
            start_date,
            end_date,
        )
        workflow_counts = self._count_by_tenant(
            WorkflowExecution,
            WorkflowExecution.started_at,
            start_date,
            end_date,
        )
        report_counts = self._count_by_tenant(
            ReportExport,
            ReportExport.created_at,
            start_date,
            end_date,
        )

        active_statement = (
            select(
                SecurityEvent.tenant_id,
                func.count(func.distinct(SecurityEvent.user_id)),
            )
            .where(
                *self._range_filters(SecurityEvent.timestamp, start_date, end_date),
                SecurityEvent.event_type.in_(USAGE_EVENT_TYPES),
                SecurityEvent.user_id.is_not(None),
                SecurityEvent.tenant_id.is_not(None),
                SecurityEvent.request_path.like("/api/%"),
                SecurityEvent.request_path.not_like(f"{ANALYTICS_PATH_PREFIX}%"),
            )
            .group_by(SecurityEvent.tenant_id)
        )
        active_statement = self._apply_scope(active_statement, SecurityEvent.tenant_id)
        active_counts: dict[UUID, int] = {}
        for tenant_id, count in self.db.execute(active_statement).all():
            if tenant_id is not None:
                active_counts[tenant_id] = int(count)
        feature_counts = self._feature_usage_by_tenant(start_date, end_date)

        customers: list[CustomerProductUsageSummary] = []
        for tenant_id, tenant_name in tenants:
            if tenant_id not in tenant_ids:
                continue
            feature_items = self._feature_items(feature_counts.get(tenant_id, {}))
            used = sorted(
                (item for item in feature_items if item.request_count > 0),
                key=lambda item: (-item.request_count, item.feature_name),
            )
            customers.append(
                CustomerProductUsageSummary(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    active_users=active_counts.get(tenant_id, 0),
                    login_count=login_counts.get(tenant_id, 0),
                    api_calls=api_counts.get(tenant_id, 0),
                    verification_requests=verification_counts.get(tenant_id, 0),
                    ai_requests=ai_counts.get(tenant_id, 0),
                    workflow_runs=workflow_counts.get(tenant_id, 0),
                    report_exports=report_counts.get(tenant_id, 0),
                    features=feature_items,
                    most_used_features=used[:5],
                    unused_features=[
                        item.feature_name
                        for item in feature_items
                        if item.request_count == 0
                    ],
                )
            )

        return ProductUsageDashboardResponse(
            start_date=start_date,
            end_date=end_date,
            tenant_filter=self.tenant_filter_id,
            total_customers=len(customers),
            active_users=sum(row.active_users for row in customers),
            login_count=sum(row.login_count for row in customers),
            api_calls=sum(row.api_calls for row in customers),
            verification_requests=sum(row.verification_requests for row in customers),
            ai_requests=sum(row.ai_requests for row in customers),
            workflow_runs=sum(row.workflow_runs for row in customers),
            report_exports=sum(row.report_exports for row in customers),
            customers=customers,
        )

    def feature_report(
        self, *, start_date: date, end_date: date
    ) -> ProductUsageFeatureReport:
        self._validate_dates(start_date, end_date)
        tenants = self._tenant_rows()
        tenant_ids = {tenant_id for tenant_id, _ in tenants}
        feature_counts = self._feature_usage_by_tenant(start_date, end_date)
        aggregate = {key: 0 for key in FEATURE_NAMES}
        for tenant_id, counts in feature_counts.items():
            if tenant_id not in tenant_ids:
                continue
            for feature, count in counts.items():
                aggregate[feature] = aggregate.get(feature, 0) + count
        items = self._feature_items(aggregate)
        used = sorted(
            (item for item in items if item.request_count > 0),
            key=lambda item: (-item.request_count, item.feature_name),
        )
        return ProductUsageFeatureReport(
            start_date=start_date,
            end_date=end_date,
            tenant_filter=self.tenant_filter_id,
            features=items,
            most_used_features=used[:5],
            unused_features=[
                item.feature_name for item in items if item.request_count == 0
            ],
        )
