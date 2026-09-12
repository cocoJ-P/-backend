"""Seed the Demo Enterprise used by 筑脉查查."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.domains.enterprise.seed import DEMO_ENTERPRISE_ID, seed_demo_enterprise


def main() -> None:
    db = SessionLocal()
    try:
        enterprise = seed_demo_enterprise(db)
        print(
            f"Demo enterprise ready: {enterprise.name} ({DEMO_ENTERPRISE_ID})"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
