"""
test_itunes_search.py — verify the rebuilt search_itunes_preview.

Usage:
    python test_itunes_search.py

PART 1  Regression: 8 indexed tracks from DB must still resolve (strict path).
PART 2  Recovery:   all failed tracks in DB — check which now resolve via fallback.
PART 2b Specific:   hardcoded spec test cases including the bootleg that must fail.
"""
from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
    force=True,
)

from track_ingestion import get_connection, search_itunes_preview  # noqa: E402


def _run(label: str, artist: str, title: str) -> None:
    try:
        url = search_itunes_preview(artist, title)
        print(f"  OK    [{label}]  {artist} - {title}")
        print(f"         {url[:100]}")
    except ValueError as exc:
        print(f"  FAIL  [{label}]  {artist} - {title}")
        print(f"         {str(exc)[:220]}")


# ---------------------------------------------------------------------------
# PART 1 — Regression
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("PART 1 — Regression (8 indexed tracks; all must return a URL)")
print("=" * 70 + "\n")

conn = get_connection()
with conn.cursor() as cur:
    cur.execute(
        "SELECT t.artist, t.title FROM tracks t "
        "JOIN embeddings e ON e.track_id = t.id "
        "WHERE t.status = 'indexed' ORDER BY t.id LIMIT 8"
    )
    indexed = cur.fetchall()
conn.close()

for artist, title in indexed:
    _run("regression", artist, title)

# ---------------------------------------------------------------------------
# PART 2 — Recovery (all currently failed tracks)
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("PART 2 — Recovery (failed tracks)")
print("=" * 70 + "\n")

conn = get_connection()
with conn.cursor() as cur:
    cur.execute("SELECT id, artist, title, error_msg FROM tracks WHERE status = 'failed' ORDER BY id")
    failed = cur.fetchall()
conn.close()

if not failed:
    print("  No failed tracks in DB.\n")
else:
    for track_id, artist, title, _err in failed:
        _run(f"id={track_id}", artist, title)

# ---------------------------------------------------------------------------
# PART 2b — Specific spec test cases
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("PART 2b — Specific spec cases")
print("=" * 70 + "\n")

# (artist, title) as stored in DB; combined label shown in comment.
# Exact stored values depend on how rekordbox exported the CSV.
# PART 2 above will catch the real values; these exercise parsing logic directly.
SPEC_TESTS: list[tuple[str, str, str]] = [
    # Layout A — label prefixed
    ("layout-A-1", "Wakaan - PEEKABOO", "Maniac [UKF Premiere]"),
    ("layout-A-2", "Wakaan - LSDREAM", "ILY"),
    # Encoding fix
    ("mojibake", "Noizu", "Mi CorazÃ³n"),
    # Clean track — should succeed on strict path
    ("clean", "MARAUDA", "TRASH"),
    # Bootleg — no iTunes match, must fail cleanly
    ("bootleg-should-fail", "Trott", "Excision & Zeds Dead - Bounce x Bumpy Teeth"),
]

for tag, artist, title in SPEC_TESTS:
    _run(tag, artist, title)

print()
