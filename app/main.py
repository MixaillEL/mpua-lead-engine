from fastapi import FastAPI

from app.api.health import router as health_router

app = FastAPI(title="MPUA Lead Engine")

app.include_router(health_router)
