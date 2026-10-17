# mypy: ignore-errors

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.analytics.models import (
    ComplianceAnalyticsDaily,  # noqa: F401
    ComplianceAnalyticsMonthly,  # noqa: F401
    CustomerAnalyticsDaily,  # noqa: F401
    CustomerAnalyticsMonthly,  # noqa: F401
    MetricDefinition,  # noqa: F401
    MetricResult,  # noqa: F401
    OperationsAnalyticsDaily,  # noqa: F401
    OperationsAnalyticsMonthly,  # noqa: F401
)
from app.core.config import settings
from app.core.database import Base
from app.models.ai_decision_explanation import AIDecisionExplanation  # noqa: F401
from app.models.ai_model_feedback import AIModelFeedback  # noqa: F401
from app.models.ai_model_metric import AIModelMetric  # noqa: F401
from app.models.ai_risk_recommendation import AIRiskRecommendation  # noqa: F401
from app.models.aml_investigation_analysis import (
    AMLInvestigationAnalysis,  # noqa: F401
)
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.case_priority import CasePriority  # noqa: F401
from app.models.communication_log import CommunicationLog  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.customer_address import CustomerAddress  # noqa: F401
from app.models.customer_status_history import CustomerStatusHistory  # noqa: F401
from app.models.document_extraction import DocumentExtraction  # noqa: F401
from app.models.document_extraction_review_log import (
    DocumentExtractionReviewLog,  # noqa: F401
)
from app.models.document_fraud_analysis import DocumentFraudAnalysis  # noqa: F401
from app.models.file import File  # noqa: F401
from app.models.integration import Integration  # noqa: F401
from app.models.knowledge_document import KnowledgeDocument  # noqa: F401
from app.models.ocr_result import OCRResult  # noqa: F401
from app.models.partner_onboarding import (
    PartnerOnboarding,  # noqa: F401
    PartnerOnboardingHistory,  # noqa: F401
)
from app.models.risk_prediction import RiskPrediction  # noqa: F401
from app.models.security_event import SecurityEvent  # noqa: F401
from app.models.subscription import (
    Subscription,  # noqa: F401
    SubscriptionUsageCounter,  # noqa: F401
)
from app.models.transaction_anomaly import (
    TransactionAnomaly,  # noqa: F401
    TransactionAnomalyActivity,  # noqa: F401
)
from app.models.transaction_risk_analysis import (
    TransactionRiskAnalysis,  # noqa: F401
    TransactionRiskTransaction,  # noqa: F401
)
from app.models.user import User  # noqa: F401
from app.models.user_session import UserSession  # noqa: F401
from app.models.webhook import Webhook, WebhookEvent  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
