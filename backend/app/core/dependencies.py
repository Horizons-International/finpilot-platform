from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.exceptions import AIConfigurationError
from app.analytics.services.metric_service import MetricService
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.tenant import Tenant
from app.models.user import User
from app.rag.retrieval import RetrievalService
from app.services.ai_analytics_assistant_service import (
    AIAnalyticsAssistantService,
)
from app.services.ai_compliance_service import (
    AIComplianceService,
)
from app.services.ai_usage_service import AIUsageService
from app.services.dashboard_service import DashboardService
from app.services.regulatory_assistant_service import RegulatoryAssistantService
from app.services.report_export_service import (
    ReportExportService,
)
from app.services.risk_scoring_service import RiskScoringService
from app.services.system_configuration_service import (
    SystemConfigurationService,
)
from app.services.task_assignment_service import (
    TaskAssignmentService,
)
from app.services.tenant_service import TenantService
from app.services.user_invitation_service import (
    UserInvitationService,
)
from app.storages.base_storage import BaseStorage
from app.storages.local_storage import LocalStorage
from app.utils.errors import unauthorized


def get_storage() -> BaseStorage:
    return LocalStorage(settings.STORAGE_PATH)


def get_ai_usage_service(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> AIUsageService:
    return AIUsageService(
        db,
        tenant_id=current_user.tenant_id,
    )


def get_risk_scoring_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RiskScoringService:
    return RiskScoringService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_task_assignment_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskAssignmentService:
    return TaskAssignmentService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_dashboard_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardService:
    return DashboardService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_system_configuration_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SystemConfigurationService:
    return SystemConfigurationService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_metric_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MetricService:
    return MetricService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_optional_retrieval_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RetrievalService | None:
    try:
        return RetrievalService(
            db,
            tenant_id=current_user.tenant_id,
        )
    except AIConfigurationError:
        return None


def get_ai_analytics_assistant_service(
    db: Session = Depends(get_db),
    retrieval_service: RetrievalService | None = Depends(
        get_optional_retrieval_service,
    ),
    current_user: User = Depends(get_current_user),
) -> AIAnalyticsAssistantService:
    return AIAnalyticsAssistantService(
        db=db,
        retrieval_service=retrieval_service,
        tenant_id=current_user.tenant_id,
    )


def get_report_export_service(
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
    current_user: User = Depends(get_current_user),
) -> ReportExportService:
    return ReportExportService(
        db=db,
        storage=storage,
        tenant_id=current_user.tenant_id,
    )


def get_tenant_service(
    db: Session = Depends(get_db),
) -> TenantService:
    return TenantService(db)


def get_tenant_context(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Tenant:
    tenant = db.get(
        Tenant,
        current_user.tenant_id,
    )

    if tenant is None:
        raise unauthorized("Tenant not found")

    return tenant


def get_user_invitation_service(
    db: Session = Depends(get_db),
) -> UserInvitationService:
    return UserInvitationService(
        db=db,
    )


def get_regulatory_assistant_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RegulatoryAssistantService:
    return RegulatoryAssistantService(
        db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        retrieval_service_factory=lambda: RetrievalService(
            db,
            tenant_id=current_user.tenant_id,
        ),
    )


def get_ai_compliance_service(
    db: Session = Depends(get_db),
    retrieval_service: RetrievalService | None = Depends(
        get_optional_retrieval_service,
    ),
    current_user: User = Depends(get_current_user),
) -> AIComplianceService:
    return AIComplianceService(
        db,
        retrieval_service=retrieval_service,
        tenant_id=current_user.tenant_id,
    )
