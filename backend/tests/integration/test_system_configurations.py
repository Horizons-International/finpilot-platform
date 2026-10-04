from app.utils.enums import (
    UserRole,
)


def authenticate_client(
    client,
    user,
):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    token = response.json()["data"]["access_token"]

    client.headers.update(
        {
            "Authorization": f"Bearer {token}",
        }
    )


def test_admin_can_create_and_view_configuration(
    client,
    create_test_user,
    cleanup_system_configurations,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "system-config-admin@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/system-configurations",
        json={
            "key": "sla.rules",
            "category": "SLA",
            "status": "ACTIVE",
            "value": {
                "approaching_threshold_percent": 20,
                "monitor_interval_seconds": 60,
            },
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True

    configuration = body["data"]

    assert configuration["key"] == "sla.rules"
    assert configuration["category"] == "SLA"
    assert configuration["status"] == "ACTIVE"
    assert configuration["value"]["approaching_threshold_percent"] == 20

    configuration_id = configuration["id"]

    response = client.get(
        f"/api/v1/system-configurations/{configuration_id}",
    )

    assert response.status_code == 200

    assert response.json()["data"]["key"] == "sla.rules"


def test_admin_can_update_configuration(
    client,
    create_test_user,
    cleanup_system_configurations,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "system-config-update@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/system-configurations",
        json={
            "key": "sla.rules",
            "category": "SLA",
            "value": {
                "approaching_threshold_percent": 20,
            },
        },
    )

    configuration_id = create_response.json()["data"]["id"]

    response = client.put(
        f"/api/v1/system-configurations/{configuration_id}",
        json={
            "value": {
                "approaching_threshold_percent": 25,
                "monitor_interval_seconds": 60,
            },
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["value"]["approaching_threshold_percent"] == 25
    assert data["value"]["monitor_interval_seconds"] == 60
    assert data["updated_by"] == str(admin.id)


def test_admin_can_activate_and_deactivate_configuration(
    client,
    create_test_user,
    cleanup_system_configurations,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "system-config-status@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/system-configurations",
        json={
            "key": "workflow.settings",
            "category": "WORKFLOW",
            "value": {
                "enabled": True,
            },
        },
    )

    configuration_id = create_response.json()["data"]["id"]

    response = client.patch(
        f"/api/v1/system-configurations/{configuration_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "INACTIVE"

    response = client.patch(
        f"/api/v1/system-configurations/{configuration_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ACTIVE"


def test_invalid_configuration_is_rejected(
    client,
    create_test_user,
    cleanup_system_configurations,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "system-config-invalid@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/system-configurations",
        json={
            "key": "sla.rules",
            "category": "SLA",
            "value": {
                "approaching_threshold_percent": 150,
            },
        },
    )

    assert response.status_code == 400


def test_configuration_key_must_match_category(
    client,
    create_test_user,
    cleanup_system_configurations,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "system-config-key@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/system-configurations",
        json={
            "key": "risk.rules",
            "category": "SLA",
            "value": {
                "approaching_threshold_percent": 20,
            },
        },
    )

    assert response.status_code == 400


def test_configuration_changes_are_audited(
    client,
    create_test_user,
    cleanup_system_configurations,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "system-config-audit@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/system-configurations",
        json={
            "key": "document.settings",
            "category": "DOCUMENT",
            "value": {
                "max_file_size_mb": 10,
            },
        },
    )

    configuration_id = create_response.json()["data"]["id"]

    client.put(
        f"/api/v1/system-configurations/{configuration_id}",
        json={
            "value": {
                "max_file_size_mb": 20,
            },
        },
    )

    client.patch(
        f"/api/v1/system-configurations/{configuration_id}/status",
        json={
            "status": "INACTIVE",
        },
    )

    response = client.get(
        f"/api/v1/system-configurations/{configuration_id}/history",
    )

    assert response.status_code == 200

    history = response.json()["data"]

    event_types = {item["event_type"] for item in history}

    assert "SYSTEM_CONFIGURATION_CREATED" in event_types
    assert "SYSTEM_CONFIGURATION_UPDATED" in event_types
    assert "SYSTEM_CONFIGURATION_STATUS_CHANGED" in event_types


def test_non_admin_cannot_manage_configurations(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        UserRole.REVIEWER,
        "system-config-reviewer@example.com",
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/system-configurations",
    )

    assert response.status_code == 403


def test_admin_can_filter_configurations(
    client,
    create_test_user,
    cleanup_system_configurations,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "system-config-filter@example.com",
    )

    authenticate_client(
        client,
        admin,
    )

    client.post(
        "/api/v1/system-configurations",
        json={
            "key": "sla.rules",
            "category": "SLA",
            "value": {
                "approaching_threshold_percent": 20,
            },
        },
    )

    client.post(
        "/api/v1/system-configurations",
        json={
            "key": "workflow.settings",
            "category": "WORKFLOW",
            "value": {
                "enabled": True,
            },
        },
    )

    response = client.get(
        "/api/v1/system-configurations",
        params={
            "category": "SLA",
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 200

    configurations = response.json()["data"]

    assert len(configurations) == 1
    assert configurations[0]["key"] == "sla.rules"
