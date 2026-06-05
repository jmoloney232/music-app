"""
compute_clusters.py — Cluster indexed tracks by their MuQ audio embeddings.

Groups tracks by audio similarity using k-means on muq_full (512-dim).
Each cluster is named from measured audio features — median BPM and majority
vocal type — so labels are always accurate regardless of genre classifier
quality.

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


def _vocal_label(vocal_dominance: float | None) -> str:
    if vocal_dominance is None:
        return "Mixed"
    if vocal_dominance < 0.10:
        return "Instrumental"
    if vocal_dominance <= 0.20:
        return "Mixed"
    return "Vocal"


def _tempo_label(bpm: float) -> str:
    if bpm < 85:
        return "Slow"
    if bpm < 105:
        return "Mid-tempo"
    if bpm < 125:
        return "Upbeat"
    if bpm < 145:
        return "Fast"
    return "Very Fast"


def _name_cluster(
    bpms: list[float | None],
    vocal_dominances: list[float | None],
    camelots: list[str | None],
) -> str:
    valid_bpms = [b for b in bpms if b is not None]
    if valid_bpms:
        median_bpm = float(np.median(valid_bpms))
        tempo = _tempo_label(median_bpm)
        bpm_str = f" · {int(round(median_bpm))} BPM"
    else:
        tempo = "Unknown Tempo"
        bpm_str = ""

    vocal_counts: Counter = Counter(
        _vocal_label(vd) for vd in vocal_dominances if vd is not None
    )
    vocal = vocal_counts.most_common(1)[0][0] if vocal_counts else "Mixed"

    # Minor (A) vs Major (B) from Camelot key — add when one dominates
    minor = sum(1 for c in camelots if c and c.endswith("A"))
    major = sum(1 for c in camelots if c and c.endswith("B"))
    total_keyed = minor + major
    if total_keyed > 0:
        if minor / total_keyed >= 0.65:
            key_str = " · Minor"
        elif major / total_keyed >= 0.65:
            key_str = " · Major"
        else:
            key_str = ""
    else:
        key_str = ""

    return f"{tempo} {vocal}{bpm_str}{key_str}"


def run(n_clusters: int, dry_run: bool) -> None:
    print("Connecting to DB…")
    conn = get_connection()

    print("Fetching embeddings for indexed tracks…")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.track_id, e.muq_full, e.bpm, e.vocal_dominance, e.camelot
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
    conn.close()  # close before long CPU work so Neon doesn't time out

    track_ids = [int(r[0]) for r in rows]
    vectors = np.array([np.asarray(r[1], dtype=np.float32) for r in rows])
    track_bpms: list[float | None] = [
        float(r[2]) if r[2] is not None else None for r in rows
    ]
    track_vds: list[float | None] = [
        float(r[3]) if r[3] is not None else None for r in rows
    ]
    track_camelots: list[str | None] = [
        str(r[4]) if r[4] is not None else None for r in rows
    ]

    k = min(n_clusters, len(rows))
    print(f"Running k-means with {k} clusters (this may take a minute)…")
    km = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=300)
    labels = km.fit_predict(vectors)

    # Accumulate per-cluster audio features for naming
    cluster_bpms: dict[int, list[float | None]] = {i: [] for i in range(k)}
    cluster_vds: dict[int, list[float | None]] = {i: [] for i in range(k)}
    cluster_camelots: dict[int, list[str | None]] = {i: [] for i in range(k)}
    cluster_count: dict[int, int] = {i: 0 for i in range(k)}

    for i, lbl in enumerate(labels):
        cluster_bpms[lbl].append(track_bpms[i])
        cluster_vds[lbl].append(track_vds[i])
        cluster_camelots[lbl].append(track_camelots[i])
        cluster_count[lbl] += 1

    cluster_names: dict[int, str] = {
        cid: _name_cluster(cluster_bpms[cid], cluster_vds[cid], cluster_camelots[cid])
        for cid in range(k)
    }

    # Print summary
    print("\nCluster summary:")
    for cid in sorted(range(k), key=lambda x: -cluster_count[x]):
        print(f"  [{cid:2d}] {cluster_names[cid]:<40s} {cluster_count[cid]:>4} tracks")

    if dry_run:
        print("\nDry run — nothing written. Re-run without --dry-run to apply.")
        return

    # Reconnect — original connection may have timed out during k-means
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
