import uuid

from app.models.verification_case import IdentityVerificationCase
from app.models.verification_review import VerificationReview
from app.utils.enums import ReviewDecision, UserRole, VerificationStatus


def authenticate_client(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )
    assert response.status_code == 200

    token = response.json()["data"]["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


def create_customer(client):
    response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "John",
            "middle_name": "Michael",
            "last_name": "Smith",
            "date_of_birth": "1990-05-15",
            "nationality": "US",
            "country_of_residence": "US",
            "email": f"customer-{uuid.uuid4()}@example.com",
            "phone_number": "+249912345678",
            "status": "new",
        },
    )

    assert response.status_code in {200, 201}

    return response.json()["data"]["id"]


def create_verification_case(client, customer_id):
    response = client.post(
        f"/api/v1/customers/{customer_id}/verification",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert response.status_code in {200, 201}

    return response.json()["data"]["id"]


def start_verification_review(
    client,
    customer_id,
    verification_case_id,
):
    response = client.post(
        f"/api/v1/customers/{customer_id}"
        f"/verification-cases/{verification_case_id}/reviews/start"
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    return response


def assign_reviewer(db_session, case_id, reviewer):
    case = (
        db_session.query(IdentityVerificationCase)
        .filter(IdentityVerificationCase.id == case_id)
        .first()
    )

    assert case is not None

    case.assigned_to = reviewer.id

    db_session.commit()
    db_session.refresh(case)

    return case


def create_assigned_review_case(
    client,
    db_session,
    create_test_user,
):
    # Create administrator.
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"admin-{uuid.uuid4()}@example.com",
    )

    # Authenticate as administrator.
    authenticate_client(client, admin)

    # Administrator creates the customer.
    customer_id = create_customer(client)

    # Administrator creates the verification case.
    case_id = create_verification_case(
        client,
        customer_id,
    )

    # Create reviewer.
    _, reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email=f"reviewer-{uuid.uuid4()}@example.com",
    )

    # Assign the case to the reviewer.
    case = assign_reviewer(
        db_session,
        case_id,
        reviewer,
    )

    assert case.status == VerificationStatus.PENDING
    assert case.assigned_to == reviewer.id

    # Authenticate as reviewer for the actual review action.
    authenticate_client(client, reviewer)

    return customer_id, case_id, reviewer


def test_assigned_reviewer_can_approve_verification_case(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    customer_id, case_id, reviewer = create_assigned_review_case(
        client,
        db_session,
        create_test_user,
    )

    start_verification_review(
        client,
        customer_id=customer_id,
        verification_case_id=case_id,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews",
        json={
            "decision": ReviewDecision.APPROVE.value,
            "notes": "Documents verified.",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["verification_case_id"] == case_id
    assert data["reviewer_id"] == str(reviewer.id)
    assert data["decision"] == ReviewDecision.APPROVE.value
    assert data["notes"] == "Documents verified."

    case = (
        db_session.query(IdentityVerificationCase)
        .filter(IdentityVerificationCase.id == case_id)
        .first()
    )

    assert case is not None
    assert case.status == VerificationStatus.APPROVED
    assert case.completed_at is not None


def test_assigned_reviewer_can_reject_verification_case(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    customer_id, case_id, reviewer = create_assigned_review_case(
        client,
        db_session,
        create_test_user,
    )

    start_verification_review(
        client,
        customer_id=customer_id,
        verification_case_id=case_id,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews",
        json={
            "decision": ReviewDecision.REJECT.value,
            "notes": "Submitted identity document could not be verified.",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["verification_case_id"] == case_id
    assert data["reviewer_id"] == str(reviewer.id)
    assert data["decision"] == ReviewDecision.REJECT.value
    assert data["notes"] == ("Submitted identity document could not be verified.")

    case = (
        db_session.query(IdentityVerificationCase)
        .filter(IdentityVerificationCase.id == case_id)
        .first()
    )

    assert case is not None
    assert case.status == VerificationStatus.REJECTED
    assert case.completed_at is not None


def test_assigned_reviewer_can_request_more_information(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    customer_id, case_id, reviewer = create_assigned_review_case(
        client,
        db_session,
        create_test_user,
    )

    start_verification_review(
        client,
        customer_id=customer_id,
        verification_case_id=case_id,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews",
        json={
            "decision": ReviewDecision.REQUEST_MORE_INFORMATION.value,
            "notes": "Please provide a clearer identity document.",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["verification_case_id"] == case_id
    assert data["reviewer_id"] == str(reviewer.id)
    assert data["decision"] == (ReviewDecision.REQUEST_MORE_INFORMATION.value)
    assert data["notes"] == "Please provide a clearer identity document."

    case = (
        db_session.query(IdentityVerificationCase)
        .filter(IdentityVerificationCase.id == case_id)
        .first()
    )

    assert case is not None
    assert case.status == VerificationStatus.PENDING
    assert case.completed_at is None


def test_reviewer_cannot_review_case_assigned_to_another_reviewer(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    # Admin creates customer and case.
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"admin-{uuid.uuid4()}@example.com",
    )

    authenticate_client(client, admin)

    customer_id = create_customer(client)
    case_id = create_verification_case(client, customer_id)

    # Create two reviewers.
    _, assigned_reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email=f"assigned-{uuid.uuid4()}@example.com",
    )

    _, reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email=f"reviewer-{uuid.uuid4()}@example.com",
    )

    # Assign the case to reviewer B.
    assign_reviewer(
        db_session,
        case_id,
        assigned_reviewer,
    )

    # Authenticate as reviewer A.
    authenticate_client(client, reviewer)

    start_response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews/start"
    )

    assert start_response.status_code == 404

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews",
        json={
            "decision": ReviewDecision.APPROVE.value,
            "notes": "Should not be allowed.",
        },
    )

    assert response.status_code == 404


def test_unassigned_reviewer_cannot_review_case(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    # Admin creates customer and case.
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"admin-{uuid.uuid4()}@example.com",
    )

    authenticate_client(client, admin)

    customer_id = create_customer(client)
    case_id = create_verification_case(client, customer_id)

    # Create reviewer but do not assign the case.
    _, reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email=f"reviewer-{uuid.uuid4()}@example.com",
    )

    authenticate_client(client, reviewer)

    start_response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews/start"
    )

    assert start_response.status_code == 404

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews",
        json={
            "decision": ReviewDecision.APPROVE.value,
            "notes": "Should not be allowed.",
        },
    )

    assert response.status_code == 404


def test_review_notes_are_stored(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    customer_id, case_id, reviewer = create_assigned_review_case(
        client,
        db_session,
        create_test_user,
    )

    start_verification_review(
        client,
        customer_id=customer_id,
        verification_case_id=case_id,
    )

    notes = "Passport name and date of birth match customer information."

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews",
        json={
            "decision": ReviewDecision.APPROVE.value,
            "notes": notes,
        },
    )

    assert response.status_code in {200, 201}

    review = (
        db_session.query(VerificationReview)
        .filter(VerificationReview.verification_case_id == case_id)
        .first()
    )

    assert review is not None
    assert review.reviewer_id == reviewer.id
    assert review.decision == ReviewDecision.APPROVE
    assert review.notes == notes


def test_cannot_review_completed_case(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    customer_id, case_id, reviewer = create_assigned_review_case(
        client,
        db_session,
        create_test_user,
    )

    start_verification_review(
        client,
        customer_id=customer_id,
        verification_case_id=case_id,
    )

    case = (
        db_session.query(IdentityVerificationCase)
        .filter(IdentityVerificationCase.id == case_id)
        .first()
    )
    assert case is not None

    case.status = VerificationStatus.APPROVED
    db_session.commit()

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews",
        json={
            "decision": ReviewDecision.APPROVE.value,
            "notes": "Should not be allowed.",
        },
    )

    assert response.status_code == 400


def test_auditor_cannot_create_verification_review(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"admin-{uuid.uuid4()}@example.com",
    )

    authenticate_client(client, admin)

    customer_id = create_customer(client)
    case_id = create_verification_case(client, customer_id)

    _, user = create_test_user(
        role=UserRole.AUDITOR,
        email=f"auditor-{uuid.uuid4()}@example.com",
    )

    authenticate_client(client, user)

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews",
        json={
            "decision": ReviewDecision.APPROVE.value,
            "notes": "Should not be allowed.",
        },
    )

    assert response.status_code == 403


def test_reviewer_can_start_verification_review(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    customer_id, case_id, reviewer = create_assigned_review_case(
        client,
        db_session,
        create_test_user,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews/start"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert data["data"] is None

    case = (
        db_session.query(IdentityVerificationCase)
        .filter(IdentityVerificationCase.id == case_id)
        .first()
    )

    assert case is not None
    assert case.status == VerificationStatus.UNDER_REVIEW


def test_reviewer_cannot_start_review_when_already_under_review(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
):
    customer_id, case_id, reviewer = create_assigned_review_case(
        client,
        db_session,
        create_test_user,
    )

    start_verification_review(
        client,
        customer_id=customer_id,
        verification_case_id=case_id,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews/start"
    )

    assert response.status_code == 400
    assert response.json()["message"] == (
        "Verification case cannot be started for review in its current status."
    )
