from typing import Generic, TypeVar

from app.core.database import Base
from app.repositories.base_repository import BaseRepository

ModelType = TypeVar("ModelType", bound=Base)


class BaseService(Generic[ModelType]):
    def __init__(self, repository: BaseRepository[ModelType]):
        self.repository = repository
