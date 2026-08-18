"""
Lightweight helpers for api.py — no heavy ML imports.
Extracted from track_ingestion.py so the API server stays within free-tier memory.
"""
from __future__ import annotations

import hashlib
import math
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


def _as_array(value: Any) -> Any:
    """Normalise an embedding column to a NumPy array.

    pgvector hands back a NumPy array for `vector` columns up to 0.4.x and a
    `Vector` object from 0.5.0 on. The scoring code multiplies these directly,
    and a `Vector` has no arithmetic, so every comparison raised TypeError and
    the whole candidate list was silently dropped. Coerce at the fetch boundary
    so the rest of the module sees one shape whichever version is installed.
    """
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return value
    to_numpy = getattr(value, "to_numpy", None)
    if to_numpy is not None:
        return to_numpy()
    return np.asarray(value, dtype=np.float32)


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
        "emb_full":    _as_array(muq_full),
        "emb_vocals":  _as_array(muq_vocals),
        "emb_backing": _as_array(muq_backing),
        "emb_drums":   _as_array(muq_drums),
        "emb_bass":    _as_array(muq_bass),
        "emb_other":   _as_array(muq_other),
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
            "emb_full":    _as_array(muq_full),
            "emb_vocals":  _as_array(muq_vocals),
            "emb_backing": _as_array(muq_backing),
            "emb_drums":   _as_array(muq_drums),
            "emb_bass":    _as_array(muq_bass),
            "emb_other":   _as_array(muq_other),
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


# ---------------------------------------------------------------------------
# Tempo compatibility
# ---------------------------------------------------------------------------

# Two tracks within this much of each other sit inside normal pitch-fader range
# and count as an exact tempo match.
TEMPO_FREE_RATIO = 0.06

# Past this the penalty saturates. Once two tracks cannot be mixed at all,
# being further apart should not keep pushing one down the list — that is what
# would turn the ranking into a tempo sort.
#
# 0.18 rather than something tighter so the 10-13% band stays competitive. Those
# pairs need real work to mix but are often the most interesting cross-genre
# finds, which is the reason chart records and club tracks share this catalogue
# at all. Anything past roughly 20% saturates either way.
TEMPO_CEILING_RATIO = 0.18

# Share of a query's own score spread that tempo is allowed to move a track.
# Derived per query rather than fixed: the blended scores sit in a very narrow
# band (~0.05 across fifty ranks), so any constant large enough to matter on one
# query would rank purely by BPM on another.
TEMPO_PENALTY_SHARE = 0.60


def tempo_distance(bpm_a: float | None, bpm_b: float | None) -> float:
    """Relative tempo difference, octave-folded. 0.10 means 10% apart.

    70 and 140 BPM are the same tempo to a DJ, and the BPM detector halves or
    doubles often enough that ignoring that would punish correct matches.
    Folding in log space collapses every octave without special-casing each one.
    """
    if not bpm_a or not bpm_b or bpm_a <= 0 or bpm_b <= 0:
        return 0.0
    octaves = math.log2(bpm_a / bpm_b)
    folded = octaves - round(octaves)
    return abs(2.0 ** folded - 1.0)


def tempo_penalty(bpm_a: float | None, bpm_b: float | None) -> float:
    """0.0 for a mixable pair up to 1.0 for an unmixable one.

    A missing BPM scores 0 — an unknown tempo is not evidence of a bad match,
    and several hundred catalogue tracks have none.
    """
    distance = tempo_distance(bpm_a, bpm_b)
    if distance <= TEMPO_FREE_RATIO:
        return 0.0
    if distance >= TEMPO_CEILING_RATIO:
        return 1.0
    x = (distance - TEMPO_FREE_RATIO) / (TEMPO_CEILING_RATIO - TEMPO_FREE_RATIO)
    # Smoothstep so the ramp has no corner where tracks would jump ranks.
    return x * x * (3.0 - 2.0 * x)


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
