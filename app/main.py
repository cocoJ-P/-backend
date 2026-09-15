"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.enterprises import router as enterprises_router
from app.api.health import router as health_router
from app.api.identity import router as identity_router
from app.api.ingestion import router as ingestion_router
from app.api.intelligence import router as intelligence_router
from app.api.opportunities import router as opportunities_router
from app.api.opportunities import source_router as opportunity_sources_router
from app.api.discoveries import router as discoveries_router
from app.api.discovery_user_states import router as discovery_user_states_router
from app.api.submissions import router as submissions_router
from app.api.service_cases import router as service_cases_router
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
    description="筑脉企服统一业务后端。当前阶段为 D6.6 Feishu → Backend Status Sync。",
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Health", "description": "服务健康检查"},
        {"name": "Enterprises", "description": "企业身份与当前成长状态"},
        {"name": "Opportunities", "description": "真实机会、来源与资格条件"},
        {"name": "Opportunity Sources", "description": "尚未映射或独立创建的机会来源"},
        {"name": "Content Ingestion", "description": "将 URL 或正文转换为统一内容对象"},
        {"name": "Opportunity Intelligence", "description": "分析来源内容声称的机会信息，不是真实性验证"},
        {"name": "Identity", "description": "开发环境身份上下文。X-Dev-User-Id 不是正式认证"},
        {"name": "User Submissions", "description": "用户主动提交的查查记录。GET /user-submissions 是企业库存；GET /user-submissions/mine 是当前用户工作列表。需要 X-Dev-User-Id"},
        {
            "name": "Discoveries",
            "description": "企业级发现 / 推荐业务对象。GET /discoveries 是企业库存；GET /discoveries/feed 是当前用户 Feed；GET /discoveries/saved 是当前用户 saved collection；POST /discoveries/{id}/accept 将 Discovery 接入 UserSubmission 工作流。需要 X-Dev-User-Id",
        },
        {
            "name": "Discovery User States",
            "description": "当前企业对 Discovery 的用户反馈列表。DiscoveryUserState 是反馈事实；linked_submission 是该 Discovery 是否已进入 UserSubmission 工作流的只读摘要。需要 X-Dev-User-Id",
        },
        {
            "name": "Service Cases",
            "description": "用户明确开始推进的服务事项。UserSubmission 是内容理解 / 解析；ServiceCase 是继续办理。飞书 Adapter 是内部 Integration，不在本模块暴露。需要 X-Dev-User-Id",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,
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
app.include_router(identity_router, prefix=settings.API_PREFIX)
app.include_router(submissions_router, prefix=settings.API_PREFIX)
app.include_router(service_cases_router, prefix=settings.API_PREFIX)
app.include_router(discoveries_router, prefix=settings.API_PREFIX)
app.include_router(discovery_user_states_router, prefix=settings.API_PREFIX)
