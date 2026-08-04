from fastapi import FastAPI

from app.api.health import router as health_router

app = FastAPI(
    title="Backend API",
    version="0.1.0",
)

app.include_router(health_router)


@app.get("/")
async def root():
    return {"message": "Backend API is running"}