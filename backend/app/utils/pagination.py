from dataclasses import dataclass

from fastapi import HTTPException, status

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        """Return the total number of pages."""
        if self.total == 0:
            return 0

        return (self.total + self.page_size - 1) // self.page_size

    @property
    def offset(self) -> int:
        """Return the database offset."""
        return (self.page - 1) * self.page_size


def validate_pagination(
    page: int,
    page_size: int,
) -> None:
    """Validate pagination parameters."""
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page must be greater than or equal to 1",
        )

    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Page size must be between 1 and {MAX_PAGE_SIZE}",
        )
