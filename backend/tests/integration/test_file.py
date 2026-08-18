from app.core.config import settings
from app.models.user import UserRole


def authenticate_client(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    access_token = response.json()["data"]["access_token"]

    client.headers.update({"Authorization": f"Bearer {access_token}"})


def test_upload_file(client, create_test_user, cleanup_test_files):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="file-upload@example.com",
    )

    authenticate_client(client, user)

    file_content = b"Hello, FinPilot!"

    response = client.post(
        "/api/v1/files",
        files={
            "file": (
                "test.txt",
                file_content,
                "text/plain",
            )
        },
    )

    assert response.status_code == 201

    body = response.json()

    cleanup_test_files(body["data"]["id"])

    assert body["success"] is True
    assert body["data"]["original_filename"] == "test.txt"
    assert body["data"]["file_size"] == len(file_content)
    assert body["data"]["content_type"] == "text/plain"


def test_upload_rejects_invalid_file_type(client, create_test_user):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="file-invalid-type@example.com",
    )

    authenticate_client(client, user)

    response = client.post(
        "/api/v1/files",
        files={
            "file": (
                "malware.exe",
                b"fake executable",
                "application/x-msdownload",
            )
        },
    )

    assert response.status_code == 400

    body = response.json()

    assert body["success"] is False


def test_upload_duplicate_filenames(client, create_test_user, cleanup_test_files):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="file-duplicate@example.com",
    )

    authenticate_client(client, user)

    response_1 = client.post(
        "/api/v1/files",
        files={
            "file": (
                "duplicate.txt",
                b"First file",
                "text/plain",
            )
        },
    )

    response_2 = client.post(
        "/api/v1/files",
        files={
            "file": (
                "duplicate.txt",
                b"Second file",
                "text/plain",
            )
        },
    )

    assert response_1.status_code == 201
    assert response_2.status_code == 201

    file_1 = response_1.json()["data"]
    file_2 = response_2.json()["data"]

    cleanup_test_files(file_1["id"])
    cleanup_test_files(file_2["id"])

    assert file_1["original_filename"] == "duplicate.txt"
    assert file_2["original_filename"] == "duplicate.txt"

    assert file_1["stored_filename"] != file_2["stored_filename"]


def test_download_file(client, create_test_user, cleanup_test_files):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="file-download@example.com",
    )

    authenticate_client(client, user)

    file_content = b"Download test content"

    upload_response = client.post(
        "/api/v1/files",
        files={
            "file": (
                "download.txt",
                file_content,
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 201

    file_id = upload_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/files/{file_id}",
    )

    cleanup_test_files(file_id)

    assert response.status_code == 200
    assert response.content == file_content


def test_delete_file(client, create_test_user, cleanup_test_files):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="file-delete@example.com",
    )

    authenticate_client(client, admin)

    file_content = b"Delete me"

    upload_response = client.post(
        "/api/v1/files",
        files={
            "file": (
                "delete.txt",
                file_content,
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 201

    file_id = upload_response.json()["data"]["id"]

    delete_response = client.delete(
        f"/api/v1/files/{file_id}",
    )

    cleanup_test_files(file_id)

    assert delete_response.status_code == 200


def test_upload_rejects_large_file(client, create_test_user):
    _, user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="file-large@example.com",
    )

    authenticate_client(client, user)

    file_content = b"x" * (settings.MAX_FILE_SIZE + 1)

    response = client.post(
        "/api/v1/files",
        files={
            "file": (
                "large.txt",
                file_content,
                "text/plain",
            )
        },
    )

    assert response.status_code == 400


def test_delete_file_requires_admin(client, create_test_user, cleanup_test_files):
    _, user = create_test_user(
        role=UserRole.AUDITOR,
        email="file-non-admin-delete@example.com",
    )

    authenticate_client(client, user)

    upload_response = client.post(
        "/api/v1/files",
        files={
            "file": (
                "protected.txt",
                b"Protected file",
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 201

    file_id = upload_response.json()["data"]["id"]

    response = client.delete(
        f"/api/v1/files/{file_id}",
    )

    cleanup_test_files(file_id)

    assert response.status_code == 403
