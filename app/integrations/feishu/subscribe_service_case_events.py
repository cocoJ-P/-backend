"""Subscribe the Service Case Bitable to drive record-changed events."""

from __future__ import annotations

from lark_oapi.api.drive.v1 import SubscribeFileRequest

from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError, format_safe_feishu_error
from app.integrations.feishu.sdk import invoke_sdk
from app.integrations.feishu.service import create_feishu_integration


def subscribe_service_case_events(*, config: FeishuConfig | None = None, sdk_client=None) -> None:
    resolved = config or FeishuConfig.from_settings()
    if not resolved.is_bitable_configured():
        raise FeishuIntegrationError(
            FeishuErrorCode.NOT_CONFIGURED,
            "Feishu is disabled or missing Bitable configuration",
            retryable=False,
        )
    integration = create_feishu_integration(config=resolved, sdk_client=sdk_client)
    if integration.sdk_client is None:
        raise FeishuIntegrationError(
            FeishuErrorCode.NOT_CONFIGURED,
            "Feishu is disabled or missing Bitable configuration",
            retryable=False,
        )
    request = (
        SubscribeFileRequest.builder()
        .file_token(resolved.bitable_app_token)
        .file_type("bitable")
        .build()
    )
    try:
        invoke_sdk(
            lambda: integration.sdk_client.drive.v1.file.subscribe(request),
            secrets=tuple(item for item in (resolved.app_secret,) if item),
        )
    except FeishuIntegrationError as exc:
        if _already_subscribed(exc):
            return
        raise


def _already_subscribed(error: FeishuIntegrationError) -> bool:
    message = (error.message or "").lower()
    return "already subscribe" in message or "已订阅" in (error.message or "")


def main() -> int:
    try:
        subscribe_service_case_events()
    except FeishuIntegrationError as exc:
        print(format_safe_feishu_error(exc))
        return 1
    print("Feishu service-case document event subscription OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
