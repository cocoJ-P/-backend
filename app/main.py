"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.enterprises import router as enterprises_router
from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router
from app.api.intelligence import router as intelligence_router
from app.api.opportunities import router as opportunities_router
from app.api.opportunities import source_router as opportunity_sources_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.info(
        "Starting %s (env=%s debug=%s)",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.DEBUG,
    )
    yield
    logger.info("Stopped %s", settings.APP_NAME)


app = FastAPI(
    title="筑脉企服 Backend",
    description="筑脉企服统一业务后端。当前阶段为 Backend B4.4 Opportunity Intelligence Orchestrator。",
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Health", "description": "服务健康检查"},
        {"name": "Enterprises", "description": "企业身份与当前成长状态"},
        {"name": "Opportunities", "description": "真实机会、来源与资格条件"},
        {"name": "Opportunity Sources", "description": "尚未映射或独立创建的机会来源"},
        {"name": "Content Ingestion", "description": "将 URL 或正文转换为统一内容对象"},
        {"name": "Opportunity Intelligence", "description": "分析来源内容声称的机会信息，不是真实性验证"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": settings.APP_NAME,
        "docs": "/docs",
    }


app.include_router(health_router, prefix=settings.API_PREFIX)
app.include_router(enterprises_router, prefix=settings.API_PREFIX)
app.include_router(opportunities_router, prefix=settings.API_PREFIX)
app.include_router(opportunity_sources_router, prefix=settings.API_PREFIX)
app.include_router(ingestion_router, prefix=settings.API_PREFIX)
app.include_router(intelligence_router, prefix=settings.API_PREFIX)
