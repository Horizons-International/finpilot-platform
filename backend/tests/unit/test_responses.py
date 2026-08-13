from app.core.responses import APIResponse, ErrorDetail


def test_success_response():
    response = APIResponse(
        success=True,
        message="User created successfully.",
        data={"id": "123"},
    )

    assert response.success is True
    assert response.message == "User created successfully."
    assert response.data == {"id": "123"}
    assert response.errors is None


def test_error_response():
    response = APIResponse(
        success=False,
        message="Validation failed.",
        errors=[
            ErrorDetail(
                field="email",
                message="Email already exists.",
            )
        ],
    )

    assert response.success is False
    assert response.message == "Validation failed."
    assert response.data is None
    assert len(response.errors) == 1
    assert response.errors[0].field == "email"


def test_empty_response():
    response = APIResponse(
        success=True,
        message="User deleted successfully.",
    )

    assert response.success is True
    assert response.data is None
    assert response.errors is None
