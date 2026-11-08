from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from backend.app.api.v1.api import api_router
from backend.app.core.config import settings
from backend.app.core.database import engine, Base
from backend.app.core.logging import logger
from backend.app.core.redis import redis_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist if not migrated
    logger.info("Initializing Autonomous Inventory Management System backend...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Test Redis connectivity
    await redis_manager.get_client()
    logger.info("System ready.")
    
    yield
    
    # Shutdown
    logger.info("Shutting down backend services...")
    await redis_manager.close()
    await engine.dispose()
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Pure Software-based Autonomous Inventory Management System API with Event-Sourced Ledger, ML Demand Forecasting & Stochastic Replenishment.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        return response
    except Exception as exc:
        logger.exception(f"Unhandled exception processing {request.method} {request.url}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error occurred.", "type": type(exc).__name__}
        )


@app.get("/health", tags=["Health"])
async def root_health_check():
    """System health and connectivity check."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "redis_connected": redis_manager.is_connected,
    }


# Include API v1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)

