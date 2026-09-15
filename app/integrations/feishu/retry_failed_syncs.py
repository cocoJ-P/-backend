"""One-shot batch retry for failed/stale Feishu syncs. Not a durable worker."""

from __future__ import annotations

import argparse
import sys

from app.core.logging import setup_logging
from app.integrations.feishu.recovery import FeishuSyncRecoveryService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.integrations.feishu.retry_failed_syncs",
        description="One-shot Feishu retry. No queue. Sequential. Oldest first.",
    )
    parser.add_argument(
        "--direction",
        choices=("outbound", "inbound", "all"),
        default="all",
    )
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.limit < 0:
        print("Limit must be >= 0")
        return 2
    setup_logging()
    summary = FeishuSyncRecoveryService().retry_failed_syncs(
        direction=args.direction,
        limit=args.limit,
    )
    print(f"Direction: {args.direction}")
    print(f"Limit: {args.limit}")
    print(f"Attempted: {summary.attempted}")
    print(f"Succeeded: {summary.succeeded}")
    print(f"Failed: {summary.failed}")
    print(f"Skipped: {summary.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
