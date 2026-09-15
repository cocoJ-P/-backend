"""Reconcile one ServiceCase against its Feishu record. Backend wins."""

from __future__ import annotations

import sys
from uuid import UUID

from app.core.logging import setup_logging
from app.integrations.feishu.recovery import FeishuSyncRecoveryService


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python -m app.integrations.feishu.reconcile_service_case <SERVICE_CASE_ID>")
        return 2
    try:
        service_case_id = UUID(args[0])
    except ValueError:
        print("Invalid ServiceCase ID")
        return 2
    setup_logging()
    result = FeishuSyncRecoveryService().reconcile_service_case(service_case_id)
    print(f"ServiceCase: {result.service_case_id}")
    print(f"binding: {result.binding_status or '-'}")
    print(f"remote: {result.remote}")
    print(f"binding_status: {result.binding_status or '-'}")
    print(f"remote_status: {result.remote_status or '-'}")
    print(f"action: {result.action}")
    print(f"result: {result.result}")
    print(f"Record ID: {result.record_id or '-'}")
    if result.error_code:
        print(f"Error: {result.error_code}")
        if result.error_message:
            print(f"Provider message: {result.error_message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
