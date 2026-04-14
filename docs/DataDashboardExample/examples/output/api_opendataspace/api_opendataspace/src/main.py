from fastapi import FastAPI
from .routers import router

app = FastAPI(
    title="api-opendataspace",
    description="OpenDataSpace project backend API.",
    version="1.0.5"
)

app.include_router(router)
