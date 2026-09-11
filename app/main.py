from fastapi import FastAPI

from app.api.dev import router as dev_router
from app.api.health import router as health_router

app = FastAPI(title="MPUA Lead Engine")

app.include_router(health_router)
app.include_router(dev_router)
