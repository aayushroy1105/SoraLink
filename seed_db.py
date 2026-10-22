
"""Initialize and seed SoraLink demo data.

Run:
    python seed_db.py

Demo passenger invitations are intended only for local development.
Set SORALINK_DEMO_SEED=0 to disable demo invitation creation.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

from database import get_db, init_db, transaction


BASE_DIR = Path(__file__).resolve().parent

# Demo-only invitation codes. Never use these for a public deployment.
DEMO_INVITES = {
    "12A": "DEMO-12A",
    "12B": "DEMO-12B",
    "12C": "DEMO-12C",
    "14A": "DEMO-14A",
    "14B": "DEMO-14B",
}

def hash_invite_code(code: str) -> str:
    """Match the SHA-256 hashing method used by auth.py."""
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def now_ms() -> int:
    """Return UTC Unix time in milliseconds."""
    return time.time_ns() // 1_000_000


def seed_seat_invites() -> int:
    """Insert or reactivate demo seat invitations without duplicating rows."""
    if os.environ.get("SORALINK_DEMO_SEED", "1").strip() == "0":
        print("Demo invitation seeding is disabled.")
        return 0

    timestamp = now_ms()
    inserted_or_updated = 0

    with get_db() as connection:
        with transaction(connection):
            for seat_label, invite_code in DEMO_INVITES.items():
                connection.execute(
                    """
                    INSERT INTO seat_invites (
                        seat_label, invite_code_hash, is_active, created_at_ms
                    )
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(seat_label) DO UPDATE SET
                        invite_code_hash = excluded.invite_code_hash,
                        is_active = 1
                    """,
                    (
                        seat_label,
                        hash_invite_code(invite_code),
                        timestamp,
                    ),
                )
                inserted_or_updated += 1

    return inserted_or_updated


def main() -> int:
    """Initialize the schema and seed local demo invitations."""
    try:
        init_db()
        count = seed_seat_invites()
    except Exception as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1

    print("SoraLink database initialized successfully.")
    print(f"Demo seat invitations prepared: {count}")

    if count:
        print("\nLocal demo passenger login codes:")
        for seat_label, invite_code in DEMO_INVITES.items():
            print(f"  Seat {seat_label}: {invite_code}")

    if os.environ.get("SORALINK_CREW_CODE"):
        print("\nCrew login is configured through SORALINK_CREW_CODE.")
    else:
        print(
            "\nCrew login is not configured. Set SORALINK_CREW_CODE "
            "in the server environment before testing crew authentication."
        )

    print("\nThese demo credentials are for local testing only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
