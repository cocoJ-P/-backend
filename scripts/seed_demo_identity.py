"""Seed Demo User and membership for Development Identity."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.domains.enterprise.seed import DEMO_ENTERPRISE_ID
from app.domains.identity.seed import DEMO_USER_ID, seed_demo_identity


def main() -> None:
    db = SessionLocal()
    try:
        user = seed_demo_identity(db)
        print(
            f"Demo identity ready: {user.display_name} ({DEMO_USER_ID}) "
            f"-> enterprise {DEMO_ENTERPRISE_ID}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
