from pathlib import Path
from uuid import uuid4

from app.storages.base_storage import BaseStorage


class LocalStorage(BaseStorage):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(
            parents=True,
            exist_ok=True,
        )

    def save(
        self,
        file_content: bytes,
        filename: str,
        folder: str,
    ) -> str:
        folder_path = self.base_path / folder
        folder_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        unique_filename = f"{uuid4()}_{filename}"

        file_path = folder_path / unique_filename

        file_path.write_bytes(file_content)

        return str(file_path)

    def read(
        self,
        storage_path: str,
    ) -> bytes:
        return Path(storage_path).read_bytes()

    def delete(
        self,
        storage_path: str,
    ) -> None:
        path = Path(storage_path)

        if path.exists():
            path.unlink()

    def exists(
        self,
        storage_path: str,
    ) -> bool:
        return Path(storage_path).exists()
