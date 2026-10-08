from uuid import uuid4

from app.models.audit_log import AuditLog
from app.utils.enums import UserRole
from tests.helpers import authenticate_client


def test_organization_admin_can_invite_user(
    client,
    create_test_user,
    cleanup_user_invitations,
):
    admin = create_test_user(
        email=f"org-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/users/invitations",
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "email": f"jane-{uuid4()}@example.com",
            "role": "Compliance Officer",
            "department": "Compliance",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["email"].startswith("jane-")
    assert data["role"] == "Compliance Officer"
    assert data["invitation_token"]
    assert data["expires_at"]


def test_invited_user_can_accept_invitation(
    client,
    create_test_user,
    cleanup_user_invitations,
):
    admin = create_test_user(
        email=f"org-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    email = f"employee-{uuid4()}@example.com"

    invite_response = client.post(
        "/api/v1/users/invitations",
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "email": email,
            "role": "Reviewer",
        },
    )

    assert invite_response.status_code == 201

    token = invite_response.json()["data"]["invitation_token"]

    response = client.post(
        "/api/v1/auth/accept-invitation",
        json={
            "token": token,
            "password": "Password123!",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["email"] == email


def test_organization_admin_can_view_users(
    client,
    create_test_user,
):
    admin = create_test_user(
        email=f"org-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    employee = create_test_user(
        email=f"employee-{uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/users",
    )

    assert response.status_code == 200

    users = response.json()["data"]["users"]

    user_ids = {user["id"] for user in users}

    assert str(employee.id) in user_ids


def test_organization_admin_can_assign_role(
    client,
    create_test_user,
):
    admin = create_test_user(
        email=f"org-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    employee = create_test_user(
        email=f"employee-{uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.put(
        f"/api/v1/users/{employee.id}",
        json={
            "role": "Analyst",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "Analyst"


def test_organization_admin_can_disable_user(
    client,
    create_test_user,
):
    admin = create_test_user(
        email=f"org-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    employee = create_test_user(
        email=f"employee-{uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.patch(
        f"/api/v1/users/{employee.id}/status",
        json={
            "status": "inactive",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "inactive"


def test_organization_admin_can_remove_user(
    client,
    create_test_user,
):
    admin = create_test_user(
        email=f"org-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    employee = create_test_user(
        email=f"employee-{uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.delete(
        f"/api/v1/users/{employee.id}",
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_deleted"] is True
    assert response.json()["data"]["status"] == "inactive"


def test_non_admin_cannot_manage_users(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        email=f"reviewer-{uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/users",
    )

    assert response.status_code == 403


def test_user_management_is_tenant_scoped(
    client,
    create_test_tenant,
    create_test_user,
):
    tenant_a = create_test_tenant(
        code=f"USER-A-{uuid4().hex[:8].upper()}",
    )

    tenant_b = create_test_tenant(
        code=f"USER-B-{uuid4().hex[:8].upper()}",
    )

    admin_a = create_test_user(
        email=f"admin-a-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
        tenant_id=tenant_a.id,
    )

    user_b = create_test_user(
        email=f"user-b-{uuid4()}@example.com",
        role=UserRole.REVIEWER,
        tenant_id=tenant_b.id,
    )

    authenticate_client(
        client,
        admin_a,
    )

    response = client.get(
        f"/api/v1/users/{user_b.id}",
    )

    assert response.status_code == 404


def test_user_invitation_is_audited(
    client,
    create_test_user,
    cleanup_user_invitations,
    db_session,
):
    admin = create_test_user(
        email=f"org-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/users/invitations",
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "email": f"jane-{uuid4()}@example.com",
            "role": "Viewer",
        },
    )

    assert response.status_code == 201

    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == "USER_INVITED",
            AuditLog.user_id == admin.id,
        )
        .order_by(
            AuditLog.timestamp.desc(),
        )
        .first()
    )

    assert audit is not None


def test_cannot_remove_last_organization_admin(
    client,
    create_test_user,
):
    admin = create_test_user(
        email=f"only-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.delete(
        f"/api/v1/users/{admin.id}",
    )

    assert response.status_code == 400
