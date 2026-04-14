from fastapi import FastAPI
from .routers import router
from .database import engine, Base

app = FastAPI(
    title="{{ cookiecutter.project_name }}",
    description="{{ cookiecutter.description }}",
    version="1.0.0",
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Welcome to {{ cookiecutter.project_name }}"}
