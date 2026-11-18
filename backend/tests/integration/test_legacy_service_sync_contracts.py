"""Guard against async declarations on legacy Session-backed services."""

from inspect import iscoroutinefunction

from app.services.document_service import DocumentService
from app.services.file_service import FileService
from app.services.knowledge_indexing_service import KnowledgeIndexingService
from app.services.partner_onboarding_portal_service import (
    PartnerOnboardingPortalService,
)
from app.services.support_ticket_service import SupportTicketService


def test_legacy_session_backed_methods_are_synchronous() -> None:
    assert not iscoroutinefunction(FileService.upload_file)
    assert not iscoroutinefunction(DocumentService.upload_document)
    assert not iscoroutinefunction(KnowledgeIndexingService.index_document)
    assert not iscoroutinefunction(SupportTicketService.add_attachment)
    assert not iscoroutinefunction(PartnerOnboardingPortalService.upload_document)
