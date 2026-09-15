"""List current Bitable field_name and field_id via official SDK. No secrets."""

from __future__ import annotations

from app.integrations.feishu.errors import FeishuIntegrationError, format_safe_feishu_error
from app.integrations.feishu.service import create_feishu_integration


def main() -> int:
    integration = create_feishu_integration()
    if not integration.config.is_bitable_configured():
        print("Error: FEISHU_NOT_CONFIGURED")
        return 1
    try:
        fields = integration.bitable.list_fields()
    except FeishuIntegrationError as exc:
        print(format_safe_feishu_error(exc))
        return 1
    print(f"table_id={integration.config.service_case_table_id}")
    print(f"field_count={len(fields)}")
    print("field_name\tfield_id\ttype")
    for item in fields:
        print(f"{item.get('field_name')}\t{item.get('field_id')}\t{item.get('type')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
