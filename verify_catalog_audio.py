"""verify_catalog_audio.py — audit indexed tracks against verified iTunes matches.

For every indexed track in the chosen source group, re-run the verified iTunes
lookup (search_itunes_preview) and record the outcome to a JSONL file. Purely
read-only: no DB writes, no audio downloads.

Outcomes per track:
    verified      — a match >= confidence threshold exists; itunes_id recorded
    no_match      — nothing passes verification; audio for this row is suspect
                    and the row cannot be re-ingested as-is
    rate_limited  — transient; rerun later (resumable, rows are skipped once done)

Usage:
    python verify_catalog_audio.py --group hot100 [--limit N] [--out FILE]

The scan is resumable: rerunning skips ids already present in the output file.
Expect ~4s per track (iTunes rate limits), so a full hot100 scan is ~10 hours.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.WARNING, force=True)

from track_ingestion import get_connection, search_itunes_preview  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="hot100", choices=["hot100", "beatport", "rekordbox", "all"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=str(ROOT / "catalog_audio_audit.jsonl"))
    parser.add_argument("--delay", type=float, default=3.5, help="seconds between iTunes lookups")
    args = parser.parse_args()

    group_where = {
        "hot100": "source_ref LIKE 'hot100%'",
        "beatport": "(source_ref LIKE 'http%' OR source_ref LIKE 'beatport%')",
        "rekordbox": "source_ref LIKE 'rekordbox%'",
        "all": "TRUE",
    }[args.group]

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id, artist, title FROM tracks "
            f"WHERE status = 'indexed' AND {group_where} ORDER BY id"
        )
        rows = cur.fetchall()
    conn.close()
    if args.limit:
        rows = rows[: args.limit]

    out = Path(args.out)
    done: set[int] = set()
    if out.exists():
        for line in out.read_text().splitlines():
            try:
                done.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                pass

    todo = [r for r in rows if r[0] not in done]
    print(f"{args.group}: {len(rows)} indexed, {len(done)} already audited, {len(todo)} to go")

    with out.open("a") as fh:
        for i, (tid, artist, title) in enumerate(todo, 1):
            rec: dict = {"id": tid, "artist": artist, "title": title}
            try:
                match = search_itunes_preview(artist, title)
                rec["outcome"] = "verified"
                rec["itunes_id"] = match["itunes_id"]
                rec["match_score"] = match["match_score"]
                rec["matched"] = f"{match['matched_artist']} - {match['matched_title']}"
            except ValueError as exc:
                rec["outcome"] = "no_match"
                rec["detail"] = str(exc)[:300]
            except Exception as exc:  # network blips: record and continue
                rec["outcome"] = "error"
                rec["detail"] = f"{type(exc).__name__}: {exc}"[:300]
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if i % 50 == 0:
                n_bad = sum(1 for _ in open(out) if '"no_match"' in _)
                print(f"[{i}/{len(todo)}] no_match so far: {n_bad}", flush=True)
            time.sleep(args.delay)

    print("DONE")


if __name__ == "__main__":
    main()
