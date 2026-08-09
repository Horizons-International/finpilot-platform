from fastapi import Depends, FastAPI

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.core.dependencies import get_current_user
from app.models.user import User

app = FastAPI(
    title="FinPilot API",
)

app.include_router(auth_router)
app.include_router(users_router)


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/v1/me")
def get_me(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": str(current_user.id),
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "email": current_user.email,
        "role": current_user.role,
    }
