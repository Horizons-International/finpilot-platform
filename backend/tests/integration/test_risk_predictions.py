from uuid import UUID

from app.models.risk_prediction import RiskPrediction
from app.utils.enums import UserRole
from tests.helpers import authenticate_client


def test_create_risk_prediction(
    client,
    create_test_user,
    create_test_customer,
    cleanup_risk_predictions,
):
    compliance_officer = create_test_user(
        email="prediction-officer@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    customer = create_test_customer(
        country_of_residence="Sudan",
    )

    authenticate_client(
        client,
        compliance_officer,
    )

    response = client.post(
        f"/api/v1/customers/{customer.id}/risk-predictions",
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["customer_id"] == str(customer.id)
    assert data["model_version"] == "rule-based-v1"
    assert 0 <= data["risk_probability"] <= 1
    assert data["features"]["country_of_residence"] == "Sudan"


def test_risk_prediction_is_persisted(
    client,
    create_test_user,
    create_test_customer,
    db_session,
    cleanup_risk_predictions,
):
    admin = create_test_user(
        email="prediction-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    customer = create_test_customer()

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        f"/api/v1/customers/{customer.id}/risk-predictions",
    )

    assert response.status_code == 201

    prediction_id = UUID(
        response.json()["data"]["id"],
    )

    prediction = db_session.get(
        RiskPrediction,
        prediction_id,
    )

    assert prediction is not None
    assert prediction.customer_id == customer.id
    assert prediction.model_version == "rule-based-v1"
    assert prediction.features is not None


def test_multiple_predictions_create_history(
    client,
    create_test_user,
    create_test_customer,
    cleanup_risk_predictions,
):
    admin = create_test_user(
        email="prediction-history@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    customer = create_test_customer()

    authenticate_client(
        client,
        admin,
    )

    first_response = client.post(
        f"/api/v1/customers/{customer.id}/risk-predictions",
    )

    second_response = client.post(
        f"/api/v1/customers/{customer.id}/risk-predictions",
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    history_response = client.get(
        f"/api/v1/customers/{customer.id}/risk-predictions",
    )

    assert history_response.status_code == 200

    predictions = history_response.json()["data"]

    assert len(predictions) >= 2


def test_get_latest_risk_prediction(
    client,
    create_test_user,
    create_test_customer,
    cleanup_risk_predictions,
):
    admin = create_test_user(
        email="prediction-latest@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    customer = create_test_customer()

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        f"/api/v1/customers/{customer.id}/risk-predictions",
    )

    assert create_response.status_code == 201

    prediction_id = create_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/customers/{customer.id}/risk-predictions/latest",
    )

    assert response.status_code == 200

    assert response.json()["data"]["id"] == prediction_id


def test_reviewer_cannot_create_risk_prediction(
    client,
    create_test_user,
    create_test_customer,
    cleanup_risk_predictions,
):
    reviewer = create_test_user(
        email="prediction-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    customer = create_test_customer()

    authenticate_client(
        client,
        reviewer,
    )

    response = client.post(
        f"/api/v1/customers/{customer.id}/risk-predictions",
    )

    assert response.status_code == 403


def test_auditor_can_read_latest_risk_prediction(
    client,
    create_test_user,
    create_test_customer,
    cleanup_risk_predictions,
):
    admin = create_test_user(
        email="prediction-create@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    auditor = create_test_user(
        email="prediction-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    customer = create_test_customer()

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        f"/api/v1/customers/{customer.id}/risk-predictions",
    )

    assert create_response.status_code == 201

    client.headers.pop("Authorization")

    authenticate_client(
        client,
        auditor,
    )

    response = client.get(
        f"/api/v1/customers/{customer.id}/risk-predictions/latest",
    )

    assert response.status_code == 200
