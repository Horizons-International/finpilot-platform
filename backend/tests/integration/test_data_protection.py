from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.data_protection_service import (
    DataProtectionError,
    DataProtectionService,
)
from app.utils.enums import UserRole


def test_retention_policy_is_tenant_scoped(
    db_session, default_tenant_id, create_test_user
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="data-protection-policy@example.com",
        tenant_id=default_tenant_id,
    )
    service = DataProtectionService(db_session, default_tenant_id)
    saved = service.set_policy("CUSTOMER", 730, True, "Bank retention policy", admin.id)
    db_session.commit()

    assert saved.tenant_id == default_tenant_id
    assert saved.resource_type == "CUSTOMER"
    assert saved.retention_days == 730
    assert service.repo.get_policy("CUSTOMER").id == saved.id


def test_invalid_retention_policy_is_rejected(
    db_session, default_tenant_id, create_test_user
):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="data-protection-invalid-policy@example.com",
        tenant_id=default_tenant_id,
    )
    service = DataProtectionService(db_session, default_tenant_id)
    with pytest.raises(DataProtectionError):
        service.set_policy("CUSTOMER", 0, True, None, admin.id)


def test_disabled_or_missing_policy_does_not_mark_records_eligible(
    db_session, default_tenant_id
):
    service = DataProtectionService(db_session, default_tenant_id)
    now = datetime.now(timezone.utc)
    assert service.eligible("CUSTOMER", now - timedelta(days=100), now=now) is False
