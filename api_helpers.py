"""
Lightweight helpers for api.py — no heavy ML imports.
Extracted from track_ingestion.py so the API server stays within free-tier memory.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import numpy as np


def slugify(value: str, max_len: int = 90) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:max_len] or "unknown"


def stable_track_key(artist: str, title: str) -> str:
    raw = f"{artist}::{title}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:10]
    return f"{slugify(artist)}_{slugify(title)}_{digest}"


def get_connection() -> Any:
    import psycopg
    from pgvector.psycopg import register_vector
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def fetch_track_features(track_id: int) -> dict[str, Any]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.artist, t.title,
                   e.muq_full, e.muq_vocals, e.muq_backing,
                   e.muq_drums, e.muq_bass, e.muq_other,
                   e.vocal_dominance, e.bpm, e.key, e.camelot, e.danceability,
                   e.mfcc_mean, e.top_styles
            FROM tracks t
            JOIN embeddings e ON e.track_id = t.id
            WHERE t.id = %s
            """,
            (track_id,),
        )
        row = cur.fetchone()
    conn.close()

    (
        artist, title,
        muq_full, muq_vocals, muq_backing,
        muq_drums, muq_bass, muq_other,
        vocal_dominance, bpm, key, camelot, danceability,
        mfcc, top_styles,
    ) = row

    return {
        "artist": artist,
        "title": title,
        "track_key": stable_track_key(artist, title),
        "emb_full":    muq_full,
        "emb_vocals":  muq_vocals,
        "emb_backing": muq_backing,
        "emb_drums":   muq_drums,
        "emb_bass":    muq_bass,
        "emb_other":   muq_other,
        "vocal_dominance": vocal_dominance,
        "bpm":         bpm,
        "key":         key,
        "camelot":     camelot,
        "danceability": danceability,
        "mfcc_mean":   list(mfcc) if mfcc is not None else None,
        "discogs_top5": top_styles,
    }


def fetch_candidates_by_vector(
    query_embedding: np.ndarray,
    exclude_id: int,
    limit: int = 100,
) -> list[tuple[int, dict[str, Any]]]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(f"SET hnsw.ef_search = {max(int(limit), 200)}")
        cur.execute(
            """
            SELECT t.id, t.artist, t.title,
                   e.muq_full, e.muq_vocals, e.muq_backing,
                   e.muq_drums, e.muq_bass, e.muq_other,
                   e.vocal_dominance, e.bpm, e.key, e.camelot, e.danceability,
                   e.mfcc_mean, e.top_styles
            FROM tracks t
            JOIN embeddings e ON e.track_id = t.id
            WHERE t.status = 'indexed' AND t.id != %s
            ORDER BY e.muq_full <=> %s
            LIMIT %s
            """,
            (exclude_id, query_embedding, limit),
        )
        rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        (
            tid, artist, title,
            muq_full, muq_vocals, muq_backing,
            muq_drums, muq_bass, muq_other,
            vocal_dominance, bpm, key, camelot, danceability,
            mfcc, top_styles,
        ) = row
        f: dict[str, Any] = {
            "artist": artist,
            "title": title,
            "emb_full":    muq_full,
            "emb_vocals":  muq_vocals,
            "emb_backing": muq_backing,
            "emb_drums":   muq_drums,
            "emb_bass":    muq_bass,
            "emb_other":   muq_other,
            "vocal_dominance": vocal_dominance,
            "bpm":         bpm,
            "key":         key,
            "camelot":     camelot,
            "danceability": danceability,
            "mfcc_mean":   list(mfcc) if mfcc is not None else None,
            "discogs_top5": top_styles,
        }
        result.append((int(tid), f))
    return result


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return float("nan")
    return float(np.dot(a, b) / denom)


def vocal_class(vd: float) -> str:
    if vd < 0.10:
        return "instrumental"
    if vd > 0.20:
        return "vocal"
    return "ambiguous"


def similarity(f_a: dict[str, Any], f_b: dict[str, Any]) -> float:
    full_sim    = cosine_similarity(f_a["emb_full"],    f_b["emb_full"])
    vocal_sim   = cosine_similarity(f_a["emb_vocals"],  f_b["emb_vocals"])
    backing_sim = cosine_similarity(f_a["emb_backing"], f_b["emb_backing"])
    has_4stem = all(
        f_a.get(key) is not None and f_b.get(key) is not None
        for key in ("emb_drums", "emb_bass", "emb_other")
    )

    ca = vocal_class(f_a["vocal_dominance"])
    cb = vocal_class(f_b["vocal_dominance"])

    if has_4stem:
        drums_sim = cosine_similarity(f_a["emb_drums"], f_b["emb_drums"])
        bass_sim  = cosine_similarity(f_a["emb_bass"],  f_b["emb_bass"])
        other_sim = cosine_similarity(f_a["emb_other"], f_b["emb_other"])

        if ca == "vocal" and cb == "vocal":
            w_full, w_vocal, w_drums, w_bass, w_other = 0.40, 0.25, 0.15, 0.10, 0.10
        elif ca == "instrumental" and cb == "instrumental":
            w_full, w_vocal, w_drums, w_bass, w_other = 0.50, 0.00, 0.20, 0.15, 0.15
        else:
            w_full, w_vocal, w_drums, w_bass, w_other = 0.55, 0.00, 0.15, 0.10, 0.20

        return (
            w_full  * full_sim +
            w_vocal * vocal_sim +
            w_drums * drums_sim +
            w_bass  * bass_sim +
            w_other * other_sim
        )

    w_full, w_vocal, w_backing = 0.50, 0.30, 0.20
    return w_full * full_sim + w_vocal * vocal_sim + w_backing * backing_sim
