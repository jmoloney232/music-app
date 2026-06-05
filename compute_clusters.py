"""
compute_clusters.py — Cluster indexed tracks by their MuQ audio embeddings.

Groups tracks by audio similarity using k-means on muq_full (512-dim).
Each cluster is named by the dominant Discogs style tags present in that group
(majority vote, so a few mislabeled tracks don't corrupt the name).

Writes cluster_id back to the embeddings table and populates a `clusters` table
with names and track counts. The API's /explore/clusters endpoint reads that
table; the Explore page uses it for discovery chips.

Usage:
    python compute_clusters.py              # 25 clusters (default), writes to DB
    python compute_clusters.py --clusters 30
    python compute_clusters.py --dry-run    # compute but don't write
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from sklearn.cluster import KMeans

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def get_connection():
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def _parse_tag(label: str) -> str:
    """Return the most specific component of a Discogs label ('Electronic---House' → 'House')."""
    return label.split("---")[-1].strip()


def _name_cluster(track_styles: list[list[str]], cluster_idx: int) -> str:
    """Name a cluster from the most common style tags across its member tracks."""
    counts: Counter = Counter()
    for styles in track_styles:
        for tag in styles:
            counts[_parse_tag(tag)] += 1

    if not counts:
        return f"Sound Group {cluster_idx + 1}"

    top = [tag for tag, _ in counts.most_common(2)]
    return " / ".join(top)


def run(n_clusters: int, dry_run: bool) -> None:
    print("Connecting to DB…")
    conn = get_connection()

    print("Fetching embeddings for indexed tracks…")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.track_id, e.muq_full, e.top_styles
            FROM embeddings e
            JOIN tracks t ON t.id = e.track_id
            WHERE t.status = 'indexed' AND e.muq_full IS NOT NULL
            ORDER BY e.track_id
            """
        )
        rows = cur.fetchall()

    if not rows:
        print("No indexed tracks with embeddings found.")
        conn.close()
        return

    print(f"Loaded {len(rows)} tracks.")
    conn.close()  # close before the long CPU work so Neon doesn't time out

    track_ids = [int(r[0]) for r in rows]
    vectors = np.array([np.asarray(r[1], dtype=np.float32) for r in rows])

    raw_styles: list[list[str]] = []
    for r in rows:
        s = r[2]
        if s is None:
            raw_styles.append([])
        elif isinstance(s, str):
            raw_styles.append(json.loads(s))
        else:
            raw_styles.append(list(s))

    k = min(n_clusters, len(rows))
    print(f"Running k-means with {k} clusters (this may take a minute)…")
    km = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=300)
    labels = km.fit_predict(vectors)

    # Group per-cluster to derive names and counts
    cluster_styles: dict[int, list[list[str]]] = {i: [] for i in range(k)}
    cluster_count: dict[int, int] = {i: 0 for i in range(k)}
    for i, lbl in enumerate(labels):
        cluster_styles[lbl].append(raw_styles[i])
        cluster_count[lbl] += 1

    cluster_names: dict[int, str] = {
        cid: _name_cluster(cluster_styles[cid], cid) for cid in range(k)
    }

    # Print summary
    print("\nCluster summary:")
    for cid in sorted(range(k), key=lambda x: -cluster_count[x]):
        print(f"  [{cid:2d}] {cluster_names[cid]:<45s} {cluster_count[cid]:>4} tracks")

    if dry_run:
        print("\nDry run — nothing written. Re-run without --dry-run to apply.")
        return

    # Reconnect — the original connection may have timed out during k-means
    print("\nReconnecting to DB…")
    conn = get_connection()

    print("Applying schema changes…")
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS cluster_id SMALLINT"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS clusters (
                id SMALLINT PRIMARY KEY,
                name TEXT NOT NULL,
                track_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    conn.commit()

    print("Writing cluster assignments…")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM clusters")
        for cid in range(k):
            cur.execute(
                "INSERT INTO clusters (id, name, track_count) VALUES (%s, %s, %s)",
                (cid, cluster_names[cid], cluster_count[cid]),
            )
        for track_id, cluster_id in zip(track_ids, labels):
            cur.execute(
                "UPDATE embeddings SET cluster_id = %s WHERE track_id = %s",
                (int(cluster_id), track_id),
            )
    conn.commit()
    conn.close()

    print(f"\nDone — {k} clusters written.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cluster indexed tracks by MuQ audio embedding similarity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--clusters",
        type=int,
        default=25,
        metavar="N",
        help="Number of clusters (default: 25).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute clusters but do not write to DB.",
    )
    args = parser.parse_args()

    if args.clusters < 2:
        raise SystemExit("--clusters must be at least 2")

    run(args.clusters, args.dry_run)


if __name__ == "__main__":
    main()
