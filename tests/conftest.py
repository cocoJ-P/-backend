"""Test configuration.

Tests use an in-memory SQLite database and must not touch
`data/zumaix_enterprise_service.db`.
"""

import os

os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["LLM_PROVIDER"] = "fake"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = "fake-model"
os.environ["DEV_IDENTITY_ENABLED"] = "true"
os.environ["FEISHU_ENABLED"] = "false"
os.environ["FEISHU_APP_ID"] = ""
os.environ["FEISHU_APP_SECRET"] = ""
os.environ["FEISHU_BITABLE_APP_TOKEN"] = ""
os.environ["FEISHU_SERVICE_CASE_TABLE_ID"] = ""

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.domains.enterprise import models as enterprise_models  # noqa: F401
from app.domains.identity import models as identity_models  # noqa: F401
from app.domains.intelligence import models as intelligence_models  # noqa: F401
from app.domains.opportunity import models as opportunity_models  # noqa: F401
from app.domains.discovery import models as discovery_models  # noqa: F401
from app.domains.discovery import user_state_models as discovery_user_state_models  # noqa: F401
from app.domains.submission import models as submission_models  # noqa: F401
from app.domains.service_case import models as service_case_models  # noqa: F401
from app.integrations.feishu import models as feishu_binding_models  # noqa: F401
from app.integrations.content import models as ingested_content_models  # noqa: F401
from app.main import app


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
