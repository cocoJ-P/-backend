"""One-shot reconcile of existing Feishu bindings. Does not backfill history."""

from __future__ import annotations

import argparse
import sys

from app.core.logging import setup_logging
from app.integrations.feishu.recovery import FeishuSyncRecoveryService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.integrations.feishu.reconcile_service_cases",
        description="Reconcile existing ServiceCase Feishu bindings. Backend wins.",
    )
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.limit < 0:
        print("Limit must be >= 0")
        return 2
    setup_logging()
    summary = FeishuSyncRecoveryService().reconcile_existing_bindings(limit=args.limit)
    print(f"Limit: {args.limit}")
    print(f"Attempted: {summary.attempted}")
    print(f"Succeeded: {summary.succeeded}")
    print(f"Failed: {summary.failed}")
    print(f"Skipped: {summary.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
