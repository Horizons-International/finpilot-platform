from fastapi import APIRouter

from app.core.responses import APIResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=APIResponse[dict[str, str]],
)
async def health_check():
    return APIResponse(
        success=True,
        message="Service is healthy.",
        data={"status": "healthy"},
    )
