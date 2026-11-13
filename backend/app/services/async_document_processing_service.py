"""Native-async OCR, extraction, document review and fraud-screening services.

Provider SDKs currently expose synchronous interfaces.  Their calls are isolated in
Starlette's worker thread pool; all persistence and tenant-scoped reads stay on the
request's AsyncSession.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from time import monotonic
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.ai.config import get_ai_config
from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.ai.providers.async_factory import get_async_ai_provider
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.services.async_ai_service import AsyncAIService
from app.core.logger import get_logger
from app.extraction.exceptions import ExtractionProviderError, ExtractionResponseError
from app.extraction.providers.base import ExtractionProvider
from app.extraction.schemas.responses import (
    DocumentExtractionResponse as ProviderExtractionResponse,
)
from app.models.ai_usage_log import AIUsageLog
from app.models.customer import Customer
from app.models.customer_audit_log import CustomerAuditLog
from app.models.document import CustomerDocument
from app.models.document_extraction import DocumentExtraction
from app.models.document_extraction_review_log import DocumentExtractionReviewLog
from app.models.document_fraud_analysis import DocumentFraudAnalysis
from app.models.ocr_result import OCRResult
from app.models.verification_document_type import VerificationDocumentType
from app.ocr.exceptions import OCRProviderError, OCRResponseError
from app.ocr.providers.base import OCRProvider
from app.ocr.schemas.requests import OCRRequest
from app.schemas.document_fraud_analysis import (
    DocumentFraudAnalysisListResponse,
    DocumentFraudAnalysisResponse,
    DocumentFraudDuplicateMatch,
    DocumentFraudResult,
)
from app.schemas.extraction_review import ExtractionReviewUpdate
from app.services.async_audit_service import AsyncAuditService
from app.services.async_customer_supporting_service import _bind_tenant
from app.services.async_subscription_service import record_subscription_usage
from app.services.document_fraud_analysis_service import DocumentFraudAnalysisService
from app.utils.audit import serialize_audit_value
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    ExtractionReviewStatus,
    ExtractionStatus,
    OCRProcessingStatus,
)
from app.utils.errors import bad_request, not_found

logger = get_logger(__name__)


def _normalize_document_number(value: str | None) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").casefold())
    return re.sub(r"[^a-z0-9]", "", raw.encode("ascii", "ignore").decode("ascii"))


def _normalize_ocr_text(value: str | None) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "")[:100000]).strip().casefold()
    return cleaned if len(cleaned) >= 40 else ""


class _AsyncDocumentService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        _bind_tenant(db, tenant_id)
        self.db = db
        self.tenant_id = tenant_id
        self.audit = AsyncAuditService(db)

    async def _document(self, document_id: UUID) -> CustomerDocument:
        document = await self.db.scalar(
            select(CustomerDocument).where(
                CustomerDocument.id == document_id,
                CustomerDocument.tenant_id == self.tenant_id,
            )
        )
        if document is None:
            await self.audit.log_access_denied(
                resource_type="customer_document",
                resource_id=document_id,
                user_id=self.db.info.get("tenant_user_id"),
                email=self.db.info.get("tenant_user_email"),
                ip_address=self.db.info.get("tenant_ip_address"),
                user_agent=self.db.info.get("tenant_user_agent"),
            )
            raise not_found("Customer document")
        return document

    async def _record_customer_audit(
        self,
        *,
        customer_id: UUID,
        actor_id: UUID,
        resource_type: str,
        resource_id: UUID,
        action: str,
        old_value: object | None = None,
        new_value: object | None = None,
    ) -> None:
        self.db.add(
            CustomerAuditLog(
                tenant_id=self.tenant_id,
                customer_id=customer_id,
                user_id=actor_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                old_value=serialize_audit_value(old_value),
                new_value=serialize_audit_value(new_value),
            )
        )
        await self.db.flush()


class AsyncOCRService(_AsyncDocumentService):
    def __init__(
        self, db: AsyncSession, provider: OCRProvider, tenant_id: UUID
    ) -> None:
        super().__init__(db, tenant_id)
        self.provider = provider

    async def get_latest_result(self, document_id: UUID) -> OCRResult | None:
        await self._document(document_id)
        return await self.db.scalar(
            select(OCRResult)
            .where(
                OCRResult.document_id == document_id,
                OCRResult.tenant_id == self.tenant_id,
            )
            .order_by(OCRResult.created_at.desc())
            .limit(1)
        )

    async def process_document_by_id(
        self,
        document_id: UUID,
        requested_by: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> OCRResult:
        document = await self._document(document_id)
        result = OCRResult(
            tenant_id=self.tenant_id,
            document_id=document.id,
            provider_name=self.provider.__class__.__name__,
            status=OCRProcessingStatus.SUBMITTED,
        )
        self.db.add(result)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.OCR_REQUESTED,
            user_id=requested_by,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="ocr_result",
            resource_id=result.id,
        )
        result.status = OCRProcessingStatus.PROCESSING
        await self.db.commit()
        try:
            provider_response = await run_in_threadpool(
                self.provider.process,
                OCRRequest(
                    document_id=document.id,
                    file_reference=document.file_reference,
                    file_name=document.file_name,
                    file_type=document.file_type,
                ),
            )
            if provider_response.document_id != document.id:
                raise OCRResponseError(
                    "OCR provider returned a response for a different document."
                )
            if (
                provider_response.processing_status
                != OCRProcessingStatus.COMPLETED.value
            ):
                raise OCRResponseError("OCR provider did not complete processing.")
            if not provider_response.extracted_text:
                raise OCRResponseError("OCR provider returned empty extracted text.")
            result.provider_name = provider_response.provider_name
            result.request_id = provider_response.request_id
            result.status = OCRProcessingStatus.COMPLETED
            result.extracted_text = provider_response.extracted_text
            result.error_message = None
            await self.audit.log_event(
                event_type=AuditEventType.OCR_COMPLETED,
                user_id=requested_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="ocr_result",
                resource_id=result.id,
            )
            await self.db.commit()
            await self.db.refresh(result)
            return result
        except (OCRProviderError, OCRResponseError) as exc:
            result.status = OCRProcessingStatus.FAILED
            result.error_message = str(exc)
            await self.audit.log_event(
                event_type=AuditEventType.OCR_FAILED,
                user_id=requested_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="ocr_result",
                resource_id=result.id,
            )
            await self.db.commit()
            raise
        except Exception as exc:
            result.status = OCRProcessingStatus.FAILED
            result.error_message = "Unexpected OCR processing error."
            await self.audit.log_event(
                event_type=AuditEventType.OCR_FAILED,
                user_id=requested_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="ocr_result",
                resource_id=result.id,
            )
            await self.db.commit()
            logger.exception("Unexpected OCR processing error for %s", document.id)
            raise OCRProviderError("OCR processing failed.") from exc


class AsyncDocumentExtractionService(_AsyncDocumentService):
    def __init__(
        self, db: AsyncSession, provider: ExtractionProvider, tenant_id: UUID
    ) -> None:
        super().__init__(db, tenant_id)
        self.provider = provider

    async def get_latest_result(self, document_id: UUID) -> DocumentExtraction | None:
        await self._document(document_id)
        return await self.db.scalar(
            select(DocumentExtraction)
            .where(
                DocumentExtraction.document_id == document_id,
                DocumentExtraction.tenant_id == self.tenant_id,
            )
            .order_by(DocumentExtraction.created_at.desc())
            .limit(1)
        )

    async def extract_document_by_id(
        self,
        document_id: UUID,
        requested_by: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DocumentExtraction:
        document = await self._document(document_id)
        ocr = await self.db.scalar(
            select(OCRResult)
            .where(
                OCRResult.document_id == document.id,
                OCRResult.tenant_id == self.tenant_id,
                OCRResult.status == OCRProcessingStatus.COMPLETED,
            )
            .order_by(OCRResult.created_at.desc())
            .limit(1)
        )
        if ocr is None:
            raise bad_request(
                "Document has no completed OCR result available for extraction."
            )
        extraction = DocumentExtraction(
            tenant_id=self.tenant_id,
            document_id=document.id,
            ocr_result_id=ocr.id,
            provider_name=self.provider.__class__.__name__,
            status=ExtractionStatus.SUBMITTED,
            review_status=ExtractionReviewStatus.PENDING_REVIEW,
        )
        self.db.add(extraction)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.DOCUMENT_EXTRACTION_REQUESTED,
            user_id=requested_by,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="document_extraction",
            resource_id=extraction.id,
        )
        extraction.status = ExtractionStatus.PROCESSING
        await self.db.commit()
        try:
            if not ocr.extracted_text:
                raise ExtractionResponseError(
                    "OCR result does not contain extracted text."
                )
            provider_response: ProviderExtractionResponse = await run_in_threadpool(
                self.provider.extract,
                document_id=document.id,
                ocr_text=ocr.extracted_text,
            )
            values = {
                "first_name": provider_response.first_name,
                "middle_name": provider_response.middle_name,
                "last_name": provider_response.last_name,
                "date_of_birth": provider_response.date_of_birth,
                "nationality": provider_response.nationality,
                "document_number": provider_response.document_number,
                "expiry_date": provider_response.expiry_date,
                "address": provider_response.address,
            }
            if not any(value is not None and value != "" for value in values.values()):
                raise ExtractionResponseError(
                    "Extraction provider returned no usable fields."
                )
            for field, value in values.items():
                setattr(extraction, field, value)
            extraction.status = ExtractionStatus.COMPLETED
            extraction.review_status = ExtractionReviewStatus.PENDING_REVIEW
            extraction.error_message = None
            await self.audit.log_event(
                event_type=AuditEventType.DOCUMENT_EXTRACTION_COMPLETED,
                user_id=requested_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="document_extraction",
                resource_id=extraction.id,
            )
            await self.db.commit()
            await self.db.refresh(extraction)
            return extraction
        except (ExtractionProviderError, ExtractionResponseError) as exc:
            extraction.status = ExtractionStatus.FAILED
            extraction.error_message = str(exc)
            await self.audit.log_event(
                event_type=AuditEventType.DOCUMENT_EXTRACTION_FAILED,
                user_id=requested_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="document_extraction",
                resource_id=extraction.id,
            )
            await self.db.commit()
            raise
        except Exception as exc:
            extraction.status = ExtractionStatus.FAILED
            extraction.error_message = "Unexpected extraction processing error."
            await self.audit.log_event(
                event_type=AuditEventType.DOCUMENT_EXTRACTION_FAILED,
                user_id=requested_by,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="document_extraction",
                resource_id=extraction.id,
            )
            await self.db.commit()
            raise ExtractionProviderError("Document extraction failed.") from exc


class AsyncDocumentReviewService(_AsyncDocumentService):
    async def get_review(
        self, document_id: UUID
    ) -> tuple[CustomerDocument, OCRResult, DocumentExtraction, Customer]:
        document = await self._document(document_id)
        ocr = await self.db.scalar(
            select(OCRResult)
            .where(
                OCRResult.document_id == document_id,
                OCRResult.tenant_id == self.tenant_id,
                OCRResult.status == OCRProcessingStatus.COMPLETED,
            )
            .order_by(OCRResult.created_at.desc())
            .limit(1)
        )
        if ocr is None:
            raise bad_request(
                "Document has no completed OCR result available for review."
            )
        extraction = await self.db.scalar(
            select(DocumentExtraction)
            .where(
                DocumentExtraction.document_id == document_id,
                DocumentExtraction.tenant_id == self.tenant_id,
                DocumentExtraction.ocr_result_id == ocr.id,
            )
            .order_by(DocumentExtraction.created_at.desc())
            .limit(1)
        )
        if extraction is None or extraction.status != ExtractionStatus.COMPLETED:
            raise bad_request(
                "Document has no completed extraction result available for review."
            )
        customer = await self.db.scalar(
            select(Customer).where(
                Customer.id == document.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer is None:
            raise not_found("Customer")
        return document, ocr, extraction, customer

    async def update_extraction(
        self,
        *,
        document_id: UUID,
        reviewer_id: UUID,
        data: ExtractionReviewUpdate,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DocumentExtraction:
        _, _, extraction, _ = await self.get_review(document_id)
        self._ensure_pending(extraction)
        changes = data.model_dump(exclude_unset=True)
        if not changes:
            raise bad_request("No extraction fields were provided for update.")
        for field, value in changes.items():
            old = getattr(extraction, field)
            if old == value:
                continue
            setattr(extraction, field, value)
            self.db.add(
                DocumentExtractionReviewLog(
                    tenant_id=self.tenant_id,
                    document_extraction_id=extraction.id,
                    reviewer_id=reviewer_id,
                    field_name=field,
                    old_value=str(old) if old is not None else None,
                    new_value=str(value) if value is not None else None,
                    action="UPDATE",
                )
            )
        await self.audit.log_event(
            event_type=AuditEventType.DOCUMENT_EXTRACTION_REVIEW_UPDATED,
            user_id=reviewer_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="document_extraction",
            resource_id=extraction.id,
        )
        await self.db.commit()
        await self.db.refresh(extraction)
        return extraction

    async def approve(
        self,
        *,
        document_id: UUID,
        reviewer_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DocumentExtraction:
        _, _, extraction, customer = await self.get_review(document_id)
        self._ensure_pending(extraction)
        self._validate_for_approval(extraction)
        changed = {}
        for field in (
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "nationality",
        ):
            value = getattr(extraction, field)
            if value is not None and getattr(customer, field) != value:
                changed[field] = (getattr(customer, field), value)
                setattr(customer, field, value)
        for field, (old, value) in changed.items():
            await self._record_customer_audit(
                customer_id=customer.id,
                actor_id=reviewer_id,
                resource_type="customer",
                resource_id=customer.id,
                action=f"UPDATE {field.replace('_', ' ').upper()} FROM DOCUMENT REVIEW",
                old_value=old,
                new_value=value,
            )
        extraction.review_status = ExtractionReviewStatus.APPROVED
        extraction.reviewed_by = reviewer_id
        extraction.reviewed_at = datetime.now(timezone.utc)
        extraction.rejection_reason = None
        await self.audit.log_event(
            event_type=AuditEventType.DOCUMENT_EXTRACTION_REVIEW_APPROVED,
            user_id=reviewer_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="document_extraction",
            resource_id=extraction.id,
        )
        await self.db.commit()
        await self.db.refresh(extraction)
        return extraction

    async def reject(
        self,
        *,
        document_id: UUID,
        reviewer_id: UUID,
        reason: str,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DocumentExtraction:
        document, _, extraction, _ = await self.get_review(document_id)
        self._ensure_pending(extraction)
        clean_reason = reason.strip()
        if not clean_reason:
            raise bad_request("Rejection reason is required.")
        extraction.review_status = ExtractionReviewStatus.REJECTED
        extraction.reviewed_by = reviewer_id
        extraction.reviewed_at = datetime.now(timezone.utc)
        extraction.rejection_reason = clean_reason
        from app.services.async_notification_service import AsyncNotificationService
        from app.utils.enums import NotificationChannel, NotificationEventType

        await AsyncNotificationService(self.db, self.tenant_id).create_notification(
            user_id=document.uploaded_by,
            title="Document rejected",
            message=(
                f'Document "{document.file_name}" was rejected. Reason: {clean_reason}'
            ),
            event_type=NotificationEventType.DOCUMENT_REJECTED,
            resource_type="document",
            resource_id=document.id,
            channels=(NotificationChannel.IN_APP,),
        )
        await self.audit.log_event(
            event_type=AuditEventType.DOCUMENT_EXTRACTION_REVIEW_REJECTED,
            user_id=reviewer_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="document_extraction",
            resource_id=extraction.id,
        )
        await self.db.commit()
        await self.db.refresh(extraction)
        return extraction

    @staticmethod
    def _ensure_pending(extraction: DocumentExtraction) -> None:
        if extraction.review_status != ExtractionReviewStatus.PENDING_REVIEW:
            raise bad_request("Document extraction has already been reviewed.")

    @staticmethod
    def _validate_for_approval(extraction: DocumentExtraction) -> None:
        if not any(
            getattr(extraction, field) is not None
            for field in (
                "first_name",
                "middle_name",
                "last_name",
                "date_of_birth",
                "nationality",
                "document_number",
                "expiry_date",
                "address",
            )
        ):
            raise bad_request("Document extraction contains no usable fields.")


class AsyncDocumentFraudAnalysisService(_AsyncDocumentService):
    """Run deterministic fraud checks asynchronously and offload optional AI SDKs."""

    @staticmethod
    def _response(row: DocumentFraudAnalysis) -> DocumentFraudAnalysisResponse:
        return DocumentFraudAnalysisResponse(
            id=row.id,
            document_id=row.document_id,
            customer_id=row.customer_id,
            status=row.status,
            risk_score=float(row.risk_score),
            risk_level=row.risk_level,
            needs_manual_review=row.needs_manual_review,
            result=(
                DocumentFraudResult.model_validate(row.result) if row.result else None
            ),
            provider_name=row.provider_name,
            model_name=row.model_name,
            error_message=row.error_message,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )

    async def list_history(
        self,
        *,
        document_id: UUID | None = None,
        customer_id: UUID | None = None,
        limit: int = 50,
    ) -> DocumentFraudAnalysisListResponse:
        statement = select(DocumentFraudAnalysis).where(
            DocumentFraudAnalysis.tenant_id == self.tenant_id
        )
        if document_id is not None:
            statement = statement.where(
                DocumentFraudAnalysis.document_id == document_id
            )
        if customer_id is not None:
            statement = statement.where(
                DocumentFraudAnalysis.customer_id == customer_id
            )
        rows = list(
            (
                await self.db.scalars(
                    statement.order_by(DocumentFraudAnalysis.created_at.desc()).limit(
                        limit
                    )
                )
            ).all()
        )
        return DocumentFraudAnalysisListResponse(
            items=[self._response(row) for row in rows], total=len(rows)
        )

    async def get_history_item(
        self, analysis_id: UUID
    ) -> DocumentFraudAnalysisResponse:
        row = await self.db.scalar(
            select(DocumentFraudAnalysis).where(
                DocumentFraudAnalysis.id == analysis_id,
                DocumentFraudAnalysis.tenant_id == self.tenant_id,
            )
        )
        if row is None:
            raise not_found("Document fraud analysis")
        return self._response(row)

    async def analyze(
        self, document_id: UUID, *, user_id: UUID, use_ai: bool = True
    ) -> DocumentFraudAnalysisResponse:
        document = await self._document(document_id)
        customer = await self.db.scalar(
            select(Customer).where(
                Customer.id == document.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer is None:
            raise not_found("Customer document")
        document_type = await self.db.get(
            VerificationDocumentType, document.document_type_id
        )
        extraction = await self.db.scalar(
            select(DocumentExtraction)
            .where(
                DocumentExtraction.document_id == document.id,
                DocumentExtraction.tenant_id == self.tenant_id,
            )
            .order_by(DocumentExtraction.created_at.desc())
            .limit(1)
        )
        ocr = await self.db.scalar(
            select(OCRResult)
            .where(
                OCRResult.document_id == document.id,
                OCRResult.tenant_id == self.tenant_id,
            )
            .order_by(OCRResult.created_at.desc())
            .limit(1)
        )
        base = DocumentFraudAnalysisService
        quality, missing, inconsistencies = base._run_rules(
            document=document,
            customer=customer,
            document_type=document_type,
            extraction=extraction,
            ocr_text=ocr.extracted_text if ocr else None,
        )
        duplicate_matches: list[DocumentFraudDuplicateMatch] = []
        seen_document_ids: set[UUID] = set()
        current_number = _normalize_document_number(
            extraction.document_number if extraction else None
        )
        if current_number:
            document_number_rows = await self.db.execute(
                select(DocumentExtraction, CustomerDocument)
                .join(
                    CustomerDocument,
                    CustomerDocument.id == DocumentExtraction.document_id,
                )
                .where(
                    DocumentExtraction.tenant_id == self.tenant_id,
                    CustomerDocument.tenant_id == self.tenant_id,
                    DocumentExtraction.document_id != document.id,
                    DocumentExtraction.status == ExtractionStatus.COMPLETED,
                    DocumentExtraction.document_number.is_not(None),
                )
                .order_by(DocumentExtraction.created_at.desc())
                .limit(500)
            )
            for other_extraction, other_document in document_number_rows.all():
                if other_document.id in seen_document_ids:
                    continue
                if (
                    _normalize_document_number(other_extraction.document_number)
                    == current_number
                ):
                    seen_document_ids.add(other_document.id)
                    duplicate_matches.append(
                        DocumentFraudDuplicateMatch(
                            document_id=other_document.id,
                            customer_id=other_document.customer_id,
                            match_type="DOCUMENT_NUMBER",
                            detail=(
                                "The extracted document number matches another "
                                "document in this tenant."
                            ),
                        )
                    )

        normalized_ocr = _normalize_ocr_text(ocr.extracted_text if ocr else None)
        if normalized_ocr:
            current_hash = hashlib.sha256(normalized_ocr.encode("utf-8")).hexdigest()
            ocr_rows = await self.db.execute(
                select(OCRResult, CustomerDocument)
                .join(CustomerDocument, CustomerDocument.id == OCRResult.document_id)
                .where(
                    OCRResult.tenant_id == self.tenant_id,
                    CustomerDocument.tenant_id == self.tenant_id,
                    CustomerDocument.id != document.id,
                    OCRResult.status == OCRProcessingStatus.COMPLETED,
                    OCRResult.extracted_text.is_not(None),
                )
                .order_by(OCRResult.created_at.desc())
                .limit(500)
            )
            for other_ocr, other_document in ocr_rows.all():
                if other_document.id in seen_document_ids:
                    continue
                other_text = _normalize_ocr_text(other_ocr.extracted_text)
                other_hash = hashlib.sha256(other_text.encode("utf-8")).hexdigest()
                if other_text and other_hash == current_hash:
                    seen_document_ids.add(other_document.id)
                    duplicate_matches.append(
                        DocumentFraudDuplicateMatch(
                            document_id=other_document.id,
                            customer_id=other_document.customer_id,
                            match_type="OCR_TEXT",
                            detail=(
                                "The normalized OCR text is identical to another "
                                "document in this tenant."
                            ),
                        )
                    )
                if len(duplicate_matches) >= 30:
                    break
        duplicate_matches = duplicate_matches[:30]
        score = base._score(quality, missing, inconsistencies, duplicate_matches)
        level = (
            "CRITICAL"
            if score >= 75
            else "HIGH"  # fmt: skip
            if score >= 50
            else "MEDIUM"  # fmt: skip
            if score >= 25
            else "LOW"  # fmt: skip
        )
        needs_review = bool(quality or missing or inconsistencies or duplicate_matches)
        row = DocumentFraudAnalysis(
            tenant_id=self.tenant_id,
            document_id=document.id,
            customer_id=customer.id,
            requested_by=user_id,
            status="PENDING",
            risk_score=Decimal(score),
            risk_level=level,
            needs_manual_review=needs_review,
        )
        self.db.add(row)
        await self.db.flush()
        ai_summary = None
        ai_observations: list[str] = []
        ai_actions: list[str] = []
        confidence = 0.45
        provider_name = None
        model_name = None
        ai_error = None
        ai_available = False
        ai_response = None
        ai_started_at = monotonic()
        if use_ai:
            try:
                context = base._context(
                    document, customer, document_type, extraction, ocr
                )
                prompt = base._build_prompt(context)
                async with AsyncAIService(
                    provider=get_async_ai_provider()
                ) as ai_service:
                    response = await ai_service.generate(
                        AIRequest(
                            request_type=AIRequestType.DOCUMENT_FRAUD_ANALYSIS,
                            prompt=prompt,
                            customer_id=customer.id,
                            document_id=document.id,
                            structured=True,
                        )
                    )
                ai_response = response
                if response.structured_data is None:
                    raise AIProviderError(
                        "The AI provider returned no structured fraud analysis."
                    )
                enrichment = base._validate_ai_result(response.structured_data)
                ai_summary = enrichment["summary"]
                ai_observations = (
                    enrichment["document_quality_notes"]
                    + enrichment["additional_risk_indicators"]
                )
                ai_actions = enrichment["recommended_actions"]
                confidence = enrichment["confidence"]
                provider_name = response.provider_name
                model_name = get_ai_config().model or None
                ai_available = True
            except (
                AIConfigurationError,
                AIProviderError,
                ValueError,
                TypeError,
            ) as exc:
                ai_error = (
                    f"AI enrichment unavailable ({type(exc).__name__}); "
                    "deterministic checks were retained."
                )
                logger.warning(
                    "AI fraud enrichment unavailable for %s: %s",
                    row.id,
                    type(exc).__name__,
                )
            except Exception as exc:
                ai_error = (
                    f"AI enrichment unavailable ({type(exc).__name__}); "
                    "deterministic checks were retained."
                )
                logger.exception("AI fraud enrichment failed for %s", row.id)
        recommendations = base._recommendations(
            quality, missing, inconsistencies, duplicate_matches
        )
        recommendations.extend(ai_actions)
        result = {
            "summary": base._summary(
                ai_summary=ai_summary if ai_available else None,
                score=score,
                level=level,
                quality_count=len(quality),
                missing_count=len(missing),
                inconsistency_count=len(inconsistencies),
                duplicate_count=len(duplicate_matches),
            ),
            "quality_assessment": base._quality_assessment(
                quality, ocr.extracted_text if ocr else None
            ),
            "risk_score": score,
            "risk_level": level,
            "needs_manual_review": needs_review,
            "quality_indicators": [item.model_dump(mode="json") for item in quality],
            "missing_information": missing,
            "inconsistencies": [
                item.model_dump(mode="json") for item in inconsistencies
            ],
            "duplicate_matches": [
                item.model_dump(mode="json") for item in duplicate_matches
            ],
            "ai_observations": ai_observations,
            "recommended_actions": list(dict.fromkeys(recommendations))[:30],
            "confidence": confidence if ai_available else 0.45,
            "ai_enrichment_available": ai_available,
        }
        row.status = "COMPLETED"
        row.risk_score = Decimal(score)
        row.risk_level = level
        row.needs_manual_review = needs_review
        row.result = result
        row.provider_name = provider_name
        row.model_name = model_name
        row.error_message = ai_error
        row.completed_at = utc_now()
        await self.db.commit()
        await self.db.refresh(row)
        if use_ai:
            # Match the synchronous service: meter every attempted AI analysis,
            # including provider failures, and persist token/error telemetry.
            await record_subscription_usage(self.db, self.tenant_id, "ai_requests")
            self.db.add(
                AIUsageLog(
                    tenant_id=self.tenant_id,
                    user_id=user_id,
                    feature="DOCUMENT_FRAUD_ANALYSIS",
                    model=model_name or "",
                    input_tokens=ai_response.input_tokens if ai_response else 0,
                    output_tokens=ai_response.output_tokens if ai_response else 0,
                    response_time=int((monotonic() - ai_started_at) * 1000),
                    error_message=ai_error,
                )
            )
            await self.db.commit()
        return self._response(row)
