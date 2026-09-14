"""Explicit ServiceCase → Feishu outbound sync CLI.

Does not scan historical cases. Prints only safe identifiers, sync status,
and sanitized provider diagnostics. Never prints APP_SECRET,
tenant_access_token, or Authorization.
"""

from __future__ import annotations

import sys
from uuid import UUID

from app.integrations.feishu.errors import FeishuIntegrationError, format_safe_feishu_error
from app.integrations.feishu.outbound import ServiceCaseFeishuSyncService


def _print_safe_error(error: FeishuIntegrationError) -> None:
    print(format_safe_feishu_error(error))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python -m app.integrations.feishu.sync_service_case <SERVICE_CASE_ID>")
        return 2
    try:
        service_case_id = UUID(args[0])
    except ValueError:
        print("Invalid ServiceCase ID")
        return 2
    service = ServiceCaseFeishuSyncService()
    try:
        binding = service.ensure_outbound_sync(service_case_id)
    except FeishuIntegrationError as exc:
        print(f"ServiceCase: {service_case_id}")
        print("Binding: failed")
        _print_safe_error(exc)
        return 1
    print(f"ServiceCase: {service_case_id}")
    print(f"Binding: {binding.sync_status}")
    print(f"Record ID: {binding.record_id or '-'}")
    if binding.sync_status == "synced":
        return 0
    if service.last_error is not None:
        _print_safe_error(service.last_error)
    elif binding.last_error_code:
        print(f"Error: {binding.last_error_code}")
        if binding.last_error_message:
            print(f"Provider message: {binding.last_error_message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
