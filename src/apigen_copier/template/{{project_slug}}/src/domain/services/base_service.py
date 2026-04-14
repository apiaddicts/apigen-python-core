from typing import Generic, TypeVar, List, Optional, Any
from src.domain.repository.base_repository import BaseRepository

T = TypeVar("T")

class BaseService(Generic[T]):
    def __init__(self, repository: BaseRepository[T]):
        self.repository = repository

    async def get_all(self) -> List[T]:
        return await self.repository.get_all()

    async def get_by_id(self, *ids: Any) -> Optional[T]:
        return await self.repository.get_by_id(*ids)

    async def create(self, entity: T) -> T:
        return await self.repository.create(entity)

    async def create_or_ignore(self, entity: T) -> T:
        return await self.repository.create_or_ignore(entity)

    async def update(self, entity: T) -> T:
        return await self.repository.update(entity)

    async def delete(self, entity: T) -> None:
        return await self.repository.delete(entity)

# ════════════════════════════════════════════════════════════════
# ✏️ CUSTOM CODE START
# Write your custom code below this line.
# You can add imports, override functions, add new methods, etc.
# ════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════
# ✏️ CUSTOM CODE END
# ════════════════════════════════════════════════════════════════
