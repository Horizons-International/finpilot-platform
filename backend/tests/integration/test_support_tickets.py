"""Integration tests for customer support ticket isolation and lifecycle."""

import asyncio
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.core.config import settings
from app.core.security import hash_password
from app.models.support_ticket import SupportTicket
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.support_ticket import SupportTicketCommentCreate, SupportTicketCreate
from app.services.support_ticket_service import SupportTicketService
from app.storages.base_storage import BaseStorage
from app.utils.enums import TenantStatus, UserRole, UserStatus
from tests.conftest import TestSessionLocal


class MemoryStorage(BaseStorage):
    """Small in-memory storage provider for attachment workflow tests."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def save(self, file_content: bytes, filename: str, folder: str) -> str:
        path = f"{folder}/{uuid4()}-{filename}"
        self.files[path] = file_content
        return path

    def read(self, storage_path: str) -> bytes:
        return self.files[storage_path]

    def exists(self, storage_path: str) -> bool:
        return storage_path in self.files

    def delete(self, storage_path: str) -> None:
        self.files.pop(storage_path, None)


def _delete_ticket(db, ticket_id, tenant_id) -> None:
    if ticket_id is None:
        return
    db.rollback()
    db.info["tenant_id"] = tenant_id
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if ticket is not None:
        db.delete(ticket)
        db.commit()


def test_ticket_creation_comment_status_history_and_resolution_time(
    create_test_user,
) -> None:
    actor = create_test_user(
        role=UserRole.ANALYST,
        email=f"ticket-customer-{uuid4().hex}@example.com",
    )
    db = TestSessionLocal()
    ticket_id = None
    support_tenant_id = None
    support_agent_id = None
    try:
        db.info["tenant_id"] = actor.tenant_id
        support_tenant = Tenant(
            name=f"Support Operations {uuid4().hex[:8]}",
            code=f"SUPPORT-{uuid4().hex[:12]}",
            status=TenantStatus.ACTIVE,
        )
        db.add(support_tenant)
        db.commit()
        db.refresh(support_tenant)
        support_tenant_id = support_tenant.id

        db.info["tenant_id"] = support_tenant.id
        support_agent = User(
            first_name="Support",
            last_name="Agent",
            email=f"support-agent-{uuid4().hex}@example.com",
            password_hash=hash_password("Password123!"),
            status=UserStatus.ACTIVE,
            role=UserRole.SUPPORT_AGENT,
            tenant_id=support_tenant.id,
            is_platform_admin=False,
            is_deleted=False,
        )
        db.add(support_agent)
        db.commit()
        db.refresh(support_agent)
        support_agent_id = support_agent.id

        db.info["tenant_id"] = actor.tenant_id
        service = SupportTicketService(db, actor)
        ticket = service.create_ticket(
            SupportTicketCreate(
                title="Unable to call the API",
                description="Requests to the transaction endpoint return HTTP 500.",
                category="API_ISSUE",
                priority="HIGH",
            )
        )
        ticket_id = ticket.id
        assert ticket.status == "OPEN"
        assert ticket.tenant_id == actor.tenant_id

        comment = service.add_comment(
            ticket.id,
            SupportTicketCommentCreate(body="We can reproduce this issue."),
        )
        assert comment.is_internal is False

        db.info["tenant_id"] = support_agent.tenant_id
        agent_service = SupportTicketService(db, support_agent)
        assigned = agent_service.assign_ticket(ticket.id, support_agent.id)
        assert assigned.assigned_to == support_agent.id
        assert assigned.status == "ASSIGNED"
        assigned = agent_service.update_status(ticket.id, "IN_PROGRESS")
        assert assigned.status == "IN_PROGRESS"
        assigned = agent_service.update_status(ticket.id, "RESOLVED")
        assert assigned.resolved_at is not None
        assert assigned.resolution_time_seconds is not None
        assert assigned.resolution_time_seconds >= 0
        event_types = {
            event.event_type for event in agent_service.list_history(ticket.id)
        }
        assert {
            "TICKET_CREATED",
            "COMMENT_ADDED",
            "TICKET_ASSIGNED",
            "STATUS_CHANGED",
        } <= event_types
    finally:
        if ticket_id is not None:
            _delete_ticket(db, ticket_id, actor.tenant_id)
        if support_agent_id is not None and support_tenant_id is not None:
            db.rollback()
            db.info["tenant_id"] = support_tenant_id

            support_agent_to_delete: User | None = (
                db.query(User).filter(User.id == support_agent_id).first()
            )

            if support_agent_to_delete is not None:
                db.delete(support_agent_to_delete)
                db.commit()
            if support_tenant_id is not None:
                db.rollback()
                db.info["tenant_id"] = support_tenant_id

                support_tenant_to_delete: Tenant | None = (
                    db.query(Tenant).filter(Tenant.id == support_tenant_id).first()
                )

                if support_tenant_to_delete is not None:
                    db.delete(support_tenant_to_delete)
                    db.commit()
        db.close()


def test_customer_cannot_read_another_users_ticket(create_test_user) -> None:
    owner = create_test_user(
        role=UserRole.ANALYST,
        email=f"ticket-owner-{uuid4().hex}@example.com",
    )
    other = create_test_user(
        role=UserRole.ANALYST,
        email=f"ticket-other-{uuid4().hex}@example.com",
        tenant_id=owner.tenant_id,
    )
    db = TestSessionLocal()
    ticket_id = None
    try:
        db.info["tenant_id"] = owner.tenant_id
        ticket = SupportTicketService(db, owner).create_ticket(
            SupportTicketCreate(
                title="Request a report",
                description="Please enable a monthly export for my dashboard.",
                category="REPORTING_REQUEST",
            )
        )
        ticket_id = ticket.id
        db.info["tenant_id"] = other.tenant_id
        with pytest.raises(HTTPException) as exc_info:
            SupportTicketService(db, other).get_ticket(ticket.id)
        assert exc_info.value.status_code == 404
    finally:
        if ticket_id is not None:
            _delete_ticket(db, ticket_id, owner.tenant_id)
        db.close()


def test_non_staff_cannot_change_status_or_add_internal_note(create_test_user) -> None:
    actor = create_test_user(
        role=UserRole.ANALYST,
        email=f"ticket-reporter-{uuid4().hex}@example.com",
    )
    db = TestSessionLocal()
    ticket_id = None
    try:
        db.info["tenant_id"] = actor.tenant_id
        service = SupportTicketService(db, actor)
        ticket = service.create_ticket(
            SupportTicketCreate(
                title="Need access restored",
                description="My analyst account is blocked from the report page.",
                category="USER_ACCESS_REQUEST",
            )
        )
        ticket_id = ticket.id
        with pytest.raises(HTTPException) as status_error:
            service.update_status(ticket.id, "RESOLVED")
        assert status_error.value.status_code == 403
        with pytest.raises(HTTPException) as comment_error:
            service.add_comment(
                ticket.id,
                SupportTicketCommentCreate(body="Internal detail", is_internal=True),
            )
        assert comment_error.value.status_code == 403
    finally:
        if ticket_id is not None:
            _delete_ticket(db, ticket_id, actor.tenant_id)
        db.close()


def test_attachment_upload_and_download_are_ticket_scoped(
    create_test_user, monkeypatch
) -> None:
    actor = create_test_user(
        role=UserRole.ANALYST,
        email=f"ticket-files-{uuid4().hex}@example.com",
    )
    monkeypatch.setattr(settings, "ALLOWED_FILE_TYPES", {"application/pdf"})
    db = TestSessionLocal()
    ticket_id = None
    storage = MemoryStorage()
    try:
        db.info["tenant_id"] = actor.tenant_id
        service = SupportTicketService(db, actor, storage=storage)
        ticket = service.create_ticket(
            SupportTicketCreate(
                title="Upload a diagnostic log",
                description="Support asked us to attach a diagnostic PDF.",
                category="SYSTEM_ERROR",
            )
        )
        ticket_id = ticket.id
        upload = UploadFile(
            file=BytesIO(b"%PDF-1.4 diagnostic test"),
            filename="diagnostic.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        attachment = asyncio.run(service.add_attachment(ticket.id, upload))
        content, filename, content_type = service.download_attachment(
            ticket.id, attachment.id
        )
        assert content == b"%PDF-1.4 diagnostic test"
        assert filename == "diagnostic.pdf"
        assert content_type == "application/pdf"
        assert [item.id for item in service.list_attachments(ticket.id)] == [
            attachment.id
        ]
    finally:
        if ticket_id is not None:
            _delete_ticket(db, ticket_id, actor.tenant_id)
        db.close()
