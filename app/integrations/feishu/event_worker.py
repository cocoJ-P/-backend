"""Independent Feishu long-connection event worker. Not started by FastAPI."""

from __future__ import annotations

import lark_oapi as lark

from app.core.logging import get_logger, setup_logging
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.events.dispatcher import create_event_dispatcher
from app.integrations.feishu.events.runner import start_feishu_ws_client
from app.integrations.feishu.events.ws import create_feishu_ws_client

logger = get_logger(__name__)


def main() -> int:
    setup_logging()
    config = FeishuConfig.from_settings()
    if not config.enabled:
        print("Feishu disabled", flush=True)
        return 0
    if not (config.service_case_status_field_id or "").strip():
        print("Feishu service-case status field id is not configured", flush=True)
        return 1
    if not config.is_bitable_configured():
        print("Error: FEISHU_NOT_CONFIGURED", flush=True)
        return 1
    dispatcher = create_event_dispatcher()
    client = create_feishu_ws_client(
        dispatcher,
        config=config,
        log_level=lark.LogLevel.WARNING,
    )
    print("Feishu event worker starting", flush=True)
    logger.info("feishu event worker starting")
    try:
        start_feishu_ws_client(client)
    except KeyboardInterrupt:
        print("Feishu event worker stopped", flush=True)
        return 0
    except Exception:
        logger.exception("feishu event worker stopped unexpectedly")
        print("Error: FEISHU_REQUEST_FAILED", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
