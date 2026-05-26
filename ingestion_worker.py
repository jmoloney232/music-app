"""
ingestion_worker.py — run-once worker that pulls pending tracks from the DB
and pushes them through the track_ingestion pipeline.

Usage:
    python ingestion_worker.py               # process all pending tracks
    python ingestion_worker.py --limit 5     # process first N pending tracks
    python ingestion_worker.py --dry-run     # list pending without processing
    python ingestion_worker.py --reset-stuck # reset processing -> pending, then exit
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Import after dotenv so DATABASE_URL is available
from track_ingestion import get_connection, ingest_one_track, save_track_features  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
    force=True,
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB helpers (thin wrappers — each opens/closes its own connection)
# ---------------------------------------------------------------------------

def _fetch_tracks(
    limit: int | None,
    *,
    reprocess_all: bool = False,
    from_id: int = 1,
) -> list[tuple[int, str, str]]:
    """Return [(id, artist, title), ...] ordered by id."""
    conn = get_connection()
    with conn.cursor() as cur:
        where_sql = "id >= %s" if reprocess_all else "status='pending' AND id >= %s"
        if limit is not None:
            cur.execute(
                f"SELECT id, artist, title FROM tracks WHERE {where_sql} ORDER BY id LIMIT %s",
                (from_id, limit),
            )
        else:
            cur.execute(
                f"SELECT id, artist, title FROM tracks WHERE {where_sql} ORDER BY id",
                (from_id,),
            )
        rows = cur.fetchall()
    conn.close()
    return [(int(row[0]), str(row[1]), str(row[2])) for row in rows]


def _fetch_pending(limit: int | None) -> list[tuple[int, str, str]]:
    """Return pending tracks, ordered by id."""
    return _fetch_tracks(limit, reprocess_all=False, from_id=1)


def _count_pending() -> int:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM tracks WHERE status='pending'")
        count = int(cur.fetchone()[0])
    conn.close()
    return count


def _count_tracks_from(from_id: int) -> int:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM tracks WHERE id >= %s", (from_id,))
        count = int(cur.fetchone()[0])
    conn.close()
    return count


def _mark_status(track_id: int, status: str, error_msg: str | None = None) -> None:
    conn = get_connection()
    with conn:
        with conn.cursor() as cur:
            if error_msg is not None:
                cur.execute(
                    "UPDATE tracks SET status=%s, error_msg=%s WHERE id=%s",
                    (status, error_msg[:500], track_id),
                )
            else:
                cur.execute(
                    "UPDATE tracks SET status=%s WHERE id=%s",
                    (status, track_id),
                )
    conn.close()


def _reset_stuck() -> int:
    """Reset all status='processing' rows back to 'pending'. Returns count reset."""
    conn = get_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tracks SET status='pending', error_msg=NULL "
                "WHERE status='processing' RETURNING id"
            )
            count = len(cur.fetchall())
    conn.close()
    return count


# ---------------------------------------------------------------------------
# Dry-run display
# ---------------------------------------------------------------------------

def _run_dry(tracks: list[tuple[int, str, str]]) -> None:
    print(f"Dry run — {len(tracks)} track(s) would be processed:\n")
    for track_id, artist, title in tracks:
        print(f"  [{track_id:>6}]  {artist} - {title}")


# ---------------------------------------------------------------------------
# Main ingestion loop
# ---------------------------------------------------------------------------

def _run_ingestion(tracks: list[tuple[int, str, str]]) -> None:
    total = len(tracks)
    indexed_count = 0
    failed_count = 0
    failures: list[tuple[int, str, str, str]] = []  # (id, artist, title, short_err)
    start_time = time.time()

    try:
        for i, (track_id, artist, title) in enumerate(tracks, start=1):
            label = f"{artist} - {title}"
            print(f"[{i}/{total}] Processing: {label} ...", end=" ", flush=True)

            _mark_status(track_id, "processing")

            try:
                features = ingest_one_track(artist, title)
                # save_track_features upserts the embeddings row and sets
                # status='indexed' on the tracks row in one transaction.
                save_track_features(features)
                print("OK")
                indexed_count += 1
            except Exception as exc:
                short_err = str(exc)[:500]
                _mark_status(track_id, "failed", short_err)
                print(f"FAILED: {str(exc)[:120]}")
                log.error("Track %d (%s) failed: %s", track_id, label, exc, exc_info=False)
                failures.append((track_id, artist, title, str(exc)[:200]))
                failed_count += 1

    except KeyboardInterrupt:
        print("\n\nInterrupted — printing summary so far.")

    _print_summary(
        total=total,
        indexed=indexed_count,
        failed=failed_count,
        elapsed=time.time() - start_time,
        failures=failures,
    )


def _print_summary(
    total: int,
    indexed: int,
    failed: int,
    elapsed: float,
    failures: list[tuple[int, str, str, str]],
) -> None:
    processed = indexed + failed
    print()
    print("=" * 60)
    print("Run summary")
    print(f"  Processed : {processed} / {total}")
    print(f"  Indexed   : {indexed}")
    print(f"  Failed    : {failed}")
    print(f"  Elapsed   : {elapsed:.1f}s")
    if failures:
        print(f"\nFailed tracks:")
        for track_id, artist, title, err in failures:
            print(f"  [{track_id}] {artist} - {title}")
            print(f"       {err[:160]}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process pending tracks from the DB through the ingestion pipeline."
    )
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Process only the first N pending tracks (useful for testing).",
    )
    parser.add_argument(
        "--reprocess-all", action="store_true",
        help="Process tracks regardless of status, ordered by id. Useful for refreshing embeddings after pipeline changes.",
    )
    parser.add_argument(
        "--from-id", type=int, default=1, metavar="ID",
        help="Start processing at this track id. Defaults to 1.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List which tracks would be processed without doing any work.",
    )
    parser.add_argument(
        "--reset-stuck", action="store_true",
        help="Reset all status='processing' rows back to 'pending' and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.reset_stuck:
        n = _reset_stuck()
        print(f"Reset {n} stuck track(s) from 'processing' back to 'pending'.")
        return

    if args.reprocess_all:
        total_available = _count_tracks_from(args.from_id)
        scope = f"all tracks with id >= {args.from_id}"
    else:
        total_available = _count_pending()
        scope = "pending tracks"

    will_process = min(args.limit, total_available) if args.limit is not None else total_available

    print(f"Selection scope      : {scope}")
    print(f"Available in scope   : {total_available}")
    print(f"Will process this run: {will_process}")

    tracks = _fetch_tracks(
        args.limit,
        reprocess_all=args.reprocess_all,
        from_id=args.from_id,
    )

    if not tracks:
        print("No pending tracks found. Nothing to do.")
        return

    if args.dry_run:
        print()
        _run_dry(tracks)
        return

    print()
    _run_ingestion(tracks)


if __name__ == "__main__":
    main()
