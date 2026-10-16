from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.ai.exceptions import AIConfigurationError
from app.analytics.services.compliance_analytics_service import (
    ComplianceAnalyticsService,
)
from app.analytics.services.customer_analytics_service import (
    CustomerAnalyticsService,
)
from app.analytics.services.executive_dashboard_service import (
    ExecutiveDashboardService,
)
from app.analytics.services.metric_service import MetricService
from app.analytics.services.operations_analytics_service import (
    OperationsAnalyticsService,
)
from app.communication.providers.base import EmailProvider, SMSProvider
from app.communication.providers.factory import (
    get_email_provider,
    get_sms_provider,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.tenant import Tenant
from app.models.user import User
from app.rag.embeddings import EmbeddingService
from app.rag.retrieval import RetrievalService
from app.services.ai_analytics_assistant_service import (
    AIAnalyticsAssistantService,
)
from app.services.ai_compliance_service import (
    AIComplianceService,
)
from app.services.ai_usage_service import AIUsageService
from app.services.communication_service import CommunicationService
from app.services.compliance_service import ComplianceService
from app.services.customer_onboarding import (
    CustomerOnboardingService,
)
from app.services.customer_risk_profile_service import CustomerRiskProfileService
from app.services.customer_service import CustomerService
from app.services.dashboard_service import DashboardService
from app.services.document_review_service import DocumentReviewService
from app.services.document_service import DocumentService
from app.services.file_service import FileService
from app.services.knowledge_document_service import (
    KnowledgeDocumentService,
)
from app.services.knowledge_indexing_service import KnowledgeIndexingService
from app.services.notification_service import NotificationService
from app.services.organization_service import OrganizationService
from app.services.organization_user_service import (
    OrganizationUserService,
)
from app.services.regulatory_assistant_service import RegulatoryAssistantService
from app.services.report_export_service import (
    ReportExportService,
)
from app.services.report_service import ReportService
from app.services.risk_prediction_service import (
    RiskPredictionService,
)
from app.services.risk_scoring_service import RiskScoringService
from app.services.system_configuration_service import (
    SystemConfigurationService,
)
from app.services.task_assignment_service import (
    TaskAssignmentService,
)
from app.services.task_service import TaskService
from app.services.tenant_service import TenantService
from app.services.user_invitation_service import (
    UserInvitationService,
)
from app.services.verification_review_service import VerificationReviewService
from app.services.verification_service import VerificationService
from app.services.workflow_service import WorkflowService
from app.storages.base_storage import BaseStorage
from app.storages.local_storage import LocalStorage
from app.utils.errors import unauthorized


def get_storage() -> BaseStorage:
    return LocalStorage(settings.STORAGE_PATH)


def get_file_service(
    request: Request,
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
    current_user: User = Depends(get_current_user),
) -> FileService:
    return FileService(
        db=db,
        storage=storage,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def get_document_service(
    request: Request,
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
    current_user: User = Depends(get_current_user),
) -> DocumentService:
    return DocumentService(
        db=db,
        storage=storage,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def get_verification_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VerificationService:
    return VerificationService(
        db,
        tenant_id=current_user.tenant_id,
    )


def get_verification_review_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VerificationReviewService:
    return VerificationReviewService(
        db,
        tenant_id=current_user.tenant_id,
    )


def get_knowledge_document_service(
    db: Session = Depends(get_db),
    file_service: FileService = Depends(get_file_service),
    current_user: User = Depends(get_current_user),
) -> KnowledgeDocumentService:
    return KnowledgeDocumentService(
        db=db,
        file_service=file_service,
        tenant_id=current_user.tenant_id,
    )


def get_knowledge_indexing_service(
    db: Session = Depends(get_db),
    file_service: FileService = Depends(get_file_service),
    current_user: User = Depends(get_current_user),
) -> KnowledgeIndexingService:
    return KnowledgeIndexingService(
        db=db,
        file_service=file_service,
        embedding_service=EmbeddingService(),
        tenant_id=current_user.tenant_id,
    )


def get_retrieval_service(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> RetrievalService:
    return RetrievalService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_ai_usage_service(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> AIUsageService:
    return AIUsageService(
        db,
        tenant_id=current_user.tenant_id,
    )


def get_compliance_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComplianceService:
    return ComplianceService(
        db,
        tenant_id=current_user.tenant_id,
    )


def get_document_review_service(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentReviewService:
    return DocumentReviewService(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def get_ai_compliance_service(
    db: Session = Depends(get_db),
    retrieval_service: RetrievalService = Depends(
        get_retrieval_service,
    ),
    current_user: User = Depends(get_current_user),
) -> AIComplianceService:
    return AIComplianceService(
        db,
        retrieval_service=retrieval_service,
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


def get_customer_risk_profile_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CustomerRiskProfileService:
    return CustomerRiskProfileService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_workflow_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowService:
    return WorkflowService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_customer_onboarding_service(
    db: Session = Depends(get_db),
    workflow_service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: User = Depends(get_current_user),
) -> CustomerOnboardingService:
    return CustomerOnboardingService(
        db=db,
        workflow_service=workflow_service,
        tenant_id=current_user.tenant_id,
    )


def get_task_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskService:
    return TaskService(
        db,
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


def get_notification_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationService:
    return NotificationService(
        db,
        tenant_id=current_user.tenant_id,
    )


def get_communication_service(
    db: Session = Depends(get_db),
    email_provider: EmailProvider = Depends(get_email_provider),
    sms_provider: SMSProvider = Depends(get_sms_provider),
    current_user: User = Depends(get_current_user),
) -> CommunicationService:
    return CommunicationService(
        db=db,
        email_provider=email_provider,
        sms_provider=sms_provider,
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


def get_executive_dashboard_service(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ExecutiveDashboardService:
    return ExecutiveDashboardService(db, tenant_id=current_user.tenant_id)


def get_compliance_analytics_service(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ComplianceAnalyticsService:
    return ComplianceAnalyticsService(db, tenant_id=current_user.tenant_id)


def get_customer_analytics_service(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> CustomerAnalyticsService:
    return CustomerAnalyticsService(db, tenant_id=current_user.tenant_id)


def get_operations_analytics_service(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> OperationsAnalyticsService:
    return OperationsAnalyticsService(db, tenant_id=current_user.tenant_id)


def get_optional_retrieval_service(
    db: Session = Depends(get_db),
) -> RetrievalService | None:
    try:
        return RetrievalService(db)
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


def get_risk_prediction_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RiskPredictionService:
    return RiskPredictionService(
        db=db,
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


def get_report_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportService:
    return ReportService(
        db=db,
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


def get_customer_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CustomerService:
    return CustomerService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_organization_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrganizationService:
    return OrganizationService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


def get_organization_user_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrganizationUserService:
    return OrganizationUserService(
        db=db,
        tenant_id=current_user.tenant_id,
    )


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
