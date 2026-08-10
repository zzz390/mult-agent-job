"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from job_agent_os.api.middleware import setup_middleware
from job_agent_os.api.response import success_response
from job_agent_os.api.v1.router import api_router
from job_agent_os.db.redis import close_redis, init_redis
from job_agent_os.db.session import close_db, init_db
from job_agent_os.memory.embeddings import get_embedding_service
from job_agent_os.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    settings = get_settings()
    print(f"Starting {settings.app_name} v{settings.version} ({settings.env})")

    await init_db()
    await init_redis()

    yield

    # Shutdown
    await close_redis()
    await close_db()
    # Close the embedding service HTTP client to release resources
    embedding_service = get_embedding_service()
    await embedding_service.close()
    print("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Multi-Agent Job Hunting System for Fall Recruitment",
        lifespan=lifespan,
    )

    # Setup middleware
    setup_middleware(app)

    # Register routers
    app.include_router(api_router)

    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        return {"status": "ok", "version": settings.version}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("job_agent_os.main:app", reload=True, host="0.0.0.0", port=8000)
