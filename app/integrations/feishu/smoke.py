"""Non-destructive Feishu connection smoke.

Only requests a tenant_access_token. Does not create, update, or delete
Bitable records. Never prints credentials or tokens.
"""

from __future__ import annotations

from app.integrations.feishu.errors import FeishuIntegrationError
from app.integrations.feishu.service import create_feishu_integration


def main() -> int:
    integration = create_feishu_integration()
    if not integration.config.enabled:
        print("Feishu disabled")
        return 0
    try:
        integration.token_provider.get_token()
    except FeishuIntegrationError as exc:
        print(f"Feishu connection failed: {exc.code}")
        return 1
    print("Feishu connection OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
