"""
rethreshold_styles.py — Re-derive top_styles from stored discogs_styles vectors
using a minimum probability threshold, dropping weak / spurious genre tags.

The original ingestion blindly kept the top-5 labels by rank with no minimum
confidence. This script re-reads the raw 400-dim probability vectors already
stored in the DB and re-selects labels above a threshold, so low-confidence
tags like "Pop---K-pop" on an EDM track get dropped.

Usage:
    python rethreshold_styles.py                 # preview with default threshold
    python rethreshold_styles.py --threshold 0.10
    python rethreshold_styles.py --apply         # write changes to DB
    python rethreshold_styles.py --threshold 0.10 --apply
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

LABELS_FILE = ROOT / "essentia_models" / "discogs400_labels.json"


def get_connection():
    import psycopg
    from pgvector.psycopg import register_vector
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def rethreshold(threshold: float, apply: bool) -> None:
    if not LABELS_FILE.exists():
        raise SystemExit(f"Labels file not found: {LABELS_FILE}")

    labels: list[str] = json.loads(LABELS_FILE.read_text())
    if len(labels) != 400:
        raise SystemExit(f"Expected 400 labels, got {len(labels)}")

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.track_id, t.artist, t.title,
                   e.discogs_styles, e.top_styles
            FROM embeddings e
            JOIN tracks t ON t.id = e.track_id
            WHERE t.status = 'indexed'
              AND e.discogs_styles IS NOT NULL
            ORDER BY t.artist, t.title
            """
        )
        rows = cur.fetchall()
    conn.close()

    print(f"Loaded {len(rows)} indexed tracks.")
    print(f"Threshold: {threshold}  ({'applying changes' if apply else 'dry run — pass --apply to write'})\n")

    to_update: list[tuple[int, list[str], list[str]]] = []  # (track_id, old, new)
    unchanged = 0

    for track_id, artist, title, discogs_vec, raw_styles in rows:
        probs = np.asarray(discogs_vec, dtype=np.float32)

        # Indices above threshold, sorted by probability descending, capped at 5
        above = np.where(probs >= threshold)[0]
        if len(above) == 0:
            # Nothing clears the bar — fall back to the single top label
            top_idx = [int(np.argmax(probs))]
        else:
            top_idx = above[np.argsort(probs[above])[::-1]][:5].tolist()

        new_styles = [labels[i] for i in top_idx]

        # Normalise current styles (could be a string or already a list)
        if isinstance(raw_styles, str):
            old_styles = json.loads(raw_styles)
        elif raw_styles is None:
            old_styles = []
        else:
            old_styles = list(raw_styles)

        if new_styles == old_styles:
            unchanged += 1
            continue

        to_update.append((track_id, old_styles, new_styles))

        removed = [s for s in old_styles if s not in new_styles]
        added   = [s for s in new_styles  if s not in old_styles]
        print(f"[{track_id}] {artist} — {title}")
        if removed:
            print(f"  - drop : {', '.join(removed)}")
        if added:
            print(f"  + keep : {', '.join(added)}")
        print()

    print("─" * 60)
    print(f"  Will change : {len(to_update)} tracks")
    print(f"  Unchanged   : {unchanged} tracks")
    print("─" * 60)

    if not apply:
        print("\nDry run complete. Run with --apply to write changes.")
        return

    if not to_update:
        print("\nNothing to update.")
        return

    conn = get_connection()
    with conn:
        with conn.cursor() as cur:
            for track_id, _, new_styles in to_update:
                cur.execute(
                    "UPDATE embeddings SET top_styles = %s WHERE track_id = %s",
                    (json.dumps(new_styles), track_id),
                )
    conn.close()
    print(f"\nDone — updated {len(to_update)} tracks.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-derive top_styles from stored 400-dim probability vectors.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--threshold", type=float, default=0.08, metavar="P",
        help="Min probability for a label to be kept (default: 0.08). "
             "Try 0.05 (lenient) → 0.15 (strict).",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write changes to the DB. Without this flag the script is a dry run.",
    )
    args = parser.parse_args()

    if not 0 < args.threshold < 1:
        raise SystemExit("--threshold must be between 0 and 1")

    rethreshold(args.threshold, args.apply)


if __name__ == "__main__":
    main()
