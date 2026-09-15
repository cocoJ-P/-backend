"""Read-only Feishu SDK Bitable smoke. Lists fields; does not create records."""

from __future__ import annotations

from app.integrations.feishu.errors import FeishuIntegrationError, format_safe_feishu_error
from app.integrations.feishu.service import create_feishu_integration


def main() -> int:
    integration = create_feishu_integration()
    if not integration.config.enabled:
        print("Feishu disabled")
        return 0
    try:
        fields = integration.bitable.list_fields()
        integration.bitable.search_records(page_size=1)
    except FeishuIntegrationError as exc:
        print(format_safe_feishu_error(exc))
        return 1
    print("Feishu SDK Bitable connection OK")
    print(f"field_count={len(fields)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
