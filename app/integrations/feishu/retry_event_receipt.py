"""Explicit inbound EventReceipt retry CLI."""

from __future__ import annotations

import sys
from uuid import UUID

from app.core.logging import setup_logging
from app.integrations.feishu.recovery import FeishuSyncRecoveryService


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python -m app.integrations.feishu.retry_event_receipt <RECEIPT_ID>")
        return 2
    try:
        receipt_id = UUID(args[0])
    except ValueError:
        print("Invalid EventReceipt ID")
        return 2
    setup_logging()
    result = FeishuSyncRecoveryService().retry_event_receipt(receipt_id)
    print(f"Receipt: {result.receipt_id}")
    print(f"Status: {result.receipt_status}")
    print(f"Retry count: {result.retry_count}")
    print(f"Case ID: {result.case_id or '-'}")
    print(f"Result: {result.result}")
    if result.error_code:
        print(f"Error: {result.error_code}")
        if result.error_message:
            print(f"Provider message: {result.error_message}")
    if result.result in {"processed", "skipped"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
