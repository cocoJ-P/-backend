"""Seed Demo Opportunities used by 筑脉企服 Backend."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.domains.opportunity.seed import (
    DEMO_POLICY_ID,
    DEMO_UNMAPPED_SOURCE_ID,
    seed_demo_opportunities,
)


def main() -> None:
    db = SessionLocal()
    try:
        opportunities = seed_demo_opportunities(db)
        print(f"Demo opportunities ready: {len(opportunities)}")
        print(f"Multi-source policy id: {DEMO_POLICY_ID}")
        print(f"Unmapped source id: {DEMO_UNMAPPED_SOURCE_ID}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
