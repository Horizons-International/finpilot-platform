from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.file import File
from app.services.file_service import FileService
from app.storages.local_storage import LocalStorage


def test_read_file_returns_file_content_metadata(
    db_session,
    tmp_path: Path,
):
    storage = LocalStorage(str(tmp_path))
    service = FileService(
        db=db_session,
        storage=storage,
    )

    user_id = uuid4()
    file_content = b"knowledge base document"

    storage_path = storage.save(
        file_content=file_content,
        filename="policy.txt",
        folder="knowledge-base/documents",
    )

    file_record = File(
        original_filename="policy.txt",
        stored_filename="policy.txt",
        storage_path=storage_path,
        folder="documents",
        module="knowledge-base",
        content_type="text/plain",
        file_size=len(file_content),
        uploaded_by=user_id,
    )

    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    result = service.read_file(
        file_id=file_record.id,
    )

    assert result == (
        file_content,
        "policy.txt",
        "text/plain",
    )

    assert file_record.id is not None

    storage.delete(storage_path)
    db_session.delete(file_record)
    db_session.commit()


def test_read_file_raises_404_for_missing_file(
    db_session,
    tmp_path: Path,
):
    storage = LocalStorage(str(tmp_path))

    service = FileService(
        db=db_session,
        storage=storage,
    )

    missing_file_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        service.read_file(
            file_id=missing_file_id,
        )

    assert "File" in str(exc_info.value)
    assert exc_info.value.status_code == 404


def test_read_file_raises_404_when_physical_file_is_missing(
    db_session,
    tmp_path: Path,
):
    storage = LocalStorage(str(tmp_path))

    service = FileService(
        db=db_session,
        storage=storage,
    )

    file_record = File(
        original_filename="missing.txt",
        stored_filename="missing.txt",
        storage_path="knowledge-base/missing.txt",
        folder="documents",
        module="knowledge-base",
        content_type="text/plain",
        file_size=10,
        uploaded_by=uuid4(),
    )

    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    with pytest.raises(HTTPException) as exc_info:
        service.read_file(
            file_id=file_record.id,
        )

    assert "Stored file" in str(exc_info.value)
    assert exc_info.value.status_code == 404

    db_session.delete(file_record)
    db_session.commit()
