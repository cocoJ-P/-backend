"""lark.ws.Client factory. Does not start the connection."""

from __future__ import annotations

import lark_oapi as lark

from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError
from app.integrations.feishu.events.dispatcher import create_event_dispatcher


def create_feishu_ws_client(
    event_handler: lark.EventDispatcherHandler | None = None,
    *,
    config: FeishuConfig | None = None,
    log_level: lark.LogLevel = lark.LogLevel.WARNING,
) -> lark.ws.Client:
    resolved = config or FeishuConfig.from_settings()
    if not resolved.is_auth_configured():
        raise FeishuIntegrationError(
            FeishuErrorCode.NOT_CONFIGURED,
            "Feishu is disabled or missing app credentials",
            retryable=False,
        )
    handler = event_handler or create_event_dispatcher()
    kwargs: dict = {
        "log_level": log_level,
        "event_handler": handler,
        "auto_reconnect": True,
    }
    if resolved.base_url:
        kwargs["domain"] = resolved.base_url
    return lark.ws.Client(resolved.app_id, resolved.app_secret, **kwargs)
