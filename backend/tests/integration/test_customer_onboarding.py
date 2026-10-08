from app.utils.enums import UserRole
from tests.helpers import authenticate_client, create_customer_with_data


def test_customer_onboarding_can_start(
    client,
    create_test_tenant,
    create_test_user,
    cleanup_test_customers,
    cleanup_workflow_executions,
):
    admin = create_test_user(
        email="onboarding-start-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer = create_customer_with_data(
        client,
        email="onboarding-start@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["entity_id"] == customer_id
    assert data["status"] == "IN_PROGRESS"
    assert data["current_step_id"] is not None
    assert len(data["step_executions"]) == 7

    assert data["step_executions"][0]["step_name"] == "Create Account"
    assert data["step_executions"][0]["status"] == "IN_PROGRESS"

    assert all(step["status"] == "PENDING" for step in data["step_executions"][1:])


def test_customer_onboarding_steps_execute_in_order(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_workflow_executions,
):
    admin = create_test_user(
        email="onboarding-order-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer = create_customer_with_data(
        client,
        email="onboarding-order@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    start_response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding",
    )

    assert start_response.status_code == 200

    expected_steps = [
        "Customer Information",
        "Address Collection",
        "Document Upload",
        "Identity Verification",
        "Compliance Review",
        "Approved",
    ]

    for expected_step in expected_steps:
        response = client.post(
            f"/api/v1/customers/{customer_id}/onboarding/advance",
            json={},
        )

        assert response.status_code == 200

        data = response.json()["data"]

        current_step = next(
            step for step in data["step_executions"] if step["status"] == "IN_PROGRESS"
        )

        assert current_step["step_name"] == expected_step

    final_response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding/advance",
        json={},
    )

    assert final_response.status_code == 200

    data = final_response.json()["data"]

    assert data["status"] == "COMPLETED"
    assert data["current_step_id"] is None

    assert all(step["status"] == "COMPLETED" for step in data["step_executions"])


def test_failed_onboarding_step_can_be_retried(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_workflow_executions,
):
    admin = create_test_user(
        email="onboarding-retry-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer = create_customer_with_data(
        client,
        email="onboarding-retry@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    start_response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding",
    )

    assert start_response.status_code == 200

    fail_response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding/fail",
        json={
            "notes": "Required customer information is incomplete.",
        },
    )

    assert fail_response.status_code == 200

    failed_data = fail_response.json()["data"]

    assert failed_data["status"] == "FAILED"

    failed_step = next(
        step
        for step in failed_data["step_executions"]
        if step["step_name"] == "Create Account"
    )

    assert failed_step["status"] == "FAILED"
    assert failed_step["notes"] == ("Required customer information is incomplete.")

    retry_response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding/retry",
    )

    assert retry_response.status_code == 200

    retry_data = retry_response.json()["data"]

    assert retry_data["status"] == "IN_PROGRESS"

    retried_step = next(
        step
        for step in retry_data["step_executions"]
        if step["step_name"] == "Create Account"
    )

    assert retried_step["status"] == "IN_PROGRESS"

    advance_response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding/advance",
        json={},
    )

    assert advance_response.status_code == 200

    data = advance_response.json()["data"]

    current_step = next(
        step for step in data["step_executions"] if step["status"] == "IN_PROGRESS"
    )

    assert current_step["step_name"] == "Customer Information"


def test_customer_cannot_start_duplicate_onboarding(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_workflow_executions,
):
    admin = create_test_user(
        email="onboarding-duplicate-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer = create_customer_with_data(
        client,
        email="onboarding-duplicate@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    first_response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding",
    )

    assert first_response.status_code == 200

    second_response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding",
    )

    assert second_response.status_code == 400

    data = second_response.json()

    assert data["success"] is False


def test_onboarding_advance_moves_only_one_step_at_a_time(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_workflow_executions,
):
    admin = create_test_user(
        email="onboarding-no-skip-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer = create_customer_with_data(
        client,
        email="onboarding-no-skip@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding",
    )

    assert response.status_code == 200

    response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding/advance",
        json={},
    )

    assert response.status_code == 200

    data = response.json()["data"]

    completed_steps = [
        step for step in data["step_executions"] if step["status"] == "COMPLETED"
    ]

    in_progress_steps = [
        step for step in data["step_executions"] if step["status"] == "IN_PROGRESS"
    ]

    assert len(completed_steps) == 1
    assert completed_steps[0]["step_name"] == "Create Account"

    assert len(in_progress_steps) == 1
    assert in_progress_steps[0]["step_name"] == "Customer Information"
