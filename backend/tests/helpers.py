from io import BytesIO
from uuid import uuid4

from app.schemas.rag import RetrievalResult
from app.utils.enums import KnowledgeDocumentCategory


def authenticate_client(client, user) -> None:
    """Log in as `user` and attach the resulting bearer token to `client`."""
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


def create_customer_with_data(client, **overrides):
    """POST a new customer, merging `overrides` onto a valid default payload."""
    data = {
        "first_name": "John",
        "middle_name": "Michael",
        "last_name": "Smith",
        "date_of_birth": "1990-05-15",
        "nationality": "US",
        "country_of_residence": "US",
        "email": "john.smith@example.com",
        "phone_number": "+249912345678",
        "status": "new",
    }

    data.update(overrides)

    return client.post(
        "/api/v1/customers",
        json=data,
    )


def create_verification_case(client, customer_id):
    """
    Create a verification case directly via
    POST /customers/{customer_id}/verification-cases.

    Asserts creation succeeded and returns the parsed case data.
    """
    response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert response.status_code == 201

    return response.json()["data"]


def initiate_verification(client, customer_id):
    """
    Trigger the provider-initiated verification flow via
    POST /customers/{customer_id}/verification.
    """
    response = client.post(
        f"/api/v1/customers/{customer_id}/verification",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert response.status_code in {200, 201}

    return response.json()["data"]


def get_passport_document_type(db_session):
    """Fetch the active 'Passport' VerificationDocumentType seed row."""
    from app.models.verification_document_type import VerificationDocumentType

    document_type = (
        db_session.query(VerificationDocumentType)
        .filter(
            VerificationDocumentType.name == "Passport",
            VerificationDocumentType.is_active.is_(True),
        )
        .first()
    )

    assert document_type is not None

    return document_type


def upload_document(
    client,
    customer_id,
    verification_case_id,
    document_type_id,
    filename: str = "passport.pdf",
    content_type: str = "application/pdf",
    content: bytes = b"%PDF-1.4 test document",
):
    """POST a file to the document upload endpoint for a verification case."""
    return client.post(
        (
            f"/api/v1/customers/{customer_id}"
            f"/verification-cases/{verification_case_id}"
            "/documents"
        ),
        data={
            "document_type_id": str(document_type_id),
        },
        files={
            "file": (
                filename,
                BytesIO(content),
                content_type,
            ),
        },
    )


class FakeRetrievalService:
    def __init__(
        self,
        results: list[RetrievalResult] | None = None,
    ) -> None:
        self.results = results or []

        self.last_query: str | None = None
        self.last_limit: int | None = None
        self.last_category = None

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        category=None,
    ) -> list[RetrievalResult]:
        self.last_query = query
        self.last_limit = limit
        self.last_category = category

        return self.results


def create_fake_retrieval_result(
    *,
    content: str = (
        "Customers must provide a valid identity document for verification."
    ),
    similarity: float = 0.92,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_name="Customer Verification Policy",
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY,
        version=1,
        content=content,
        similarity=similarity,
    )
