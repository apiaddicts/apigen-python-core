from fastapi import FastAPI
from .routers import router

app = FastAPI(
    title="api-apigen-python",
    description="API para validar especificaciones (OpenAPI, AsyncAPI y GraphQL) y generar arquetipos Python comprimidos en un ZIP.",
    version="2.0.1"
)

app.include_router(router)
