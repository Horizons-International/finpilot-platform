from abc import ABC, abstractmethod


class BaseStorage(ABC):
    @abstractmethod
    def save(
        self,
        file_content: bytes,
        filename: str,
        folder: str,
    ) -> str:
        """Save a file and return its storage path."""
        raise NotImplementedError

    @abstractmethod
    def read(
        self,
        storage_path: str,
    ) -> bytes:
        """Retrieve a file."""
        raise NotImplementedError

    @abstractmethod
    def delete(
        self,
        storage_path: str,
    ) -> None:
        """Delete a file."""
        raise NotImplementedError

    @abstractmethod
    def exists(
        self,
        storage_path: str,
    ) -> bool:
        """Check whether a file exists."""
        raise NotImplementedError
