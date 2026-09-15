"""Development Feishu WebSocket smoke. Ctrl+C to stop. No business event handlers."""

from __future__ import annotations

import lark_oapi as lark

from app.integrations.feishu.errors import FeishuIntegrationError, format_safe_feishu_error
from app.integrations.feishu.events.runner import start_feishu_ws_client
from app.integrations.feishu.events.ws import create_feishu_ws_client


def main() -> int:
    try:
        client = create_feishu_ws_client(log_level=lark.LogLevel.INFO)
    except FeishuIntegrationError as exc:
        print(format_safe_feishu_error(exc))
        return 1
    print("Connecting Feishu WebSocket. Press Ctrl+C to stop.")
    try:
        start_feishu_ws_client(client)
    except KeyboardInterrupt:
        print("Feishu WebSocket stopped")
        return 0
    except Exception as exc:
        print(f"Error: FEISHU_REQUEST_FAILED")
        print(f"Provider message: {exc.__class__.__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
