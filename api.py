"""
api.py — FastAPI server for Jack's Similar Song Search.

Endpoints:
    GET /search?q=<text>           Search indexed tracks by artist or title
    GET /tracks                    List all indexed tracks
    GET /similar/<id>?top=<n>      Similarity query against the full catalog
"""
from __future__ import annotations

import json
import logging
import os
import statistics
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from api_helpers import (
    get_connection,
    fetch_track_features,
    fetch_candidates_by_vector,
    similarity,
    tempo_penalty,
    vocal_class,
    TEMPO_PENALTY_SHARE,
)

log = logging.getLogger("similar_song_search")

app = FastAPI(title="Jack's Similar Song Search API")

_cors_env = os.getenv("CORS_ORIGINS", "")
_allowed_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _search_tracks(text: str) -> list[dict]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.id, t.artist, t.title "
            "FROM tracks t "
            "JOIN embeddings e ON e.track_id = t.id "
            "WHERE t.status = 'indexed' "
            "  AND (t.artist ILIKE %s OR t.title ILIKE %s) "
            "ORDER BY t.id",
            (f"%{text}%", f"%{text}%"),
        )
        rows = cur.fetchall()
    conn.close()
    return [{"id": int(r[0]), "artist": str(r[1]), "title": str(r[2])} for r in rows]


def _list_tracks() -> list[dict]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.id, t.artist, t.title "
            "FROM tracks t "
            "JOIN embeddings e ON e.track_id = t.id "
            "WHERE t.status = 'indexed' "
            "ORDER BY t.id"
        )
        rows = cur.fetchall()
    conn.close()
    return [{"id": int(r[0]), "artist": str(r[1]), "title": str(r[2])} for r in rows]


def _explore_styles() -> list[dict]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT style_tag, COUNT(*) AS cnt
            FROM tracks t
            JOIN embeddings e ON e.track_id = t.id,
            LATERAL jsonb_array_elements_text(e.top_styles) AS style_tag
            WHERE t.status = 'indexed' AND e.top_styles IS NOT NULL
            GROUP BY style_tag
            ORDER BY cnt DESC
            LIMIT 40
            """
        )
        rows = cur.fetchall()
    conn.close()
    return [{"style": str(r[0]), "count": int(r[1])} for r in rows]


def _explore_clusters() -> list[dict]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, track_count FROM clusters ORDER BY track_count DESC")
        rows = cur.fetchall()
    conn.close()
    return [{"id": int(r[0]), "name": str(r[1]), "count": int(r[2])} for r in rows]


def _explore_tracks(
    cluster_id: int | None,
    bpm_min: float | None,
    bpm_max: float | None,
    camelot_filter: str | None,
    vocal: str | None,
    limit: int,
    offset: int,
) -> dict:
    conn = get_connection()
    conditions: list[str] = ["t.status = 'indexed'"]
    params: list[Any] = []

    if cluster_id is not None:
        conditions.append("e.cluster_id = %s")
        params.append(cluster_id)
    if bpm_min is not None:
        conditions.append("e.bpm >= %s")
        params.append(bpm_min)
    if bpm_max is not None:
        conditions.append("e.bpm <= %s")
        params.append(bpm_max)
    if camelot_filter:
        conditions.append("e.camelot = %s")
        params.append(camelot_filter)
    if vocal == "instrumental":
        conditions.append("e.vocal_dominance < 0.10")
    elif vocal == "ambiguous":
        conditions.append("e.vocal_dominance >= 0.10 AND e.vocal_dominance <= 0.20")
    elif vocal == "vocal":
        conditions.append("e.vocal_dominance > 0.20")

    where = " AND ".join(conditions)

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM tracks t JOIN embeddings e ON e.track_id = t.id WHERE {where}",
            params,
        )
        total = int(cur.fetchone()[0])

        cur.execute(
            f"""
            SELECT t.id, t.artist, t.title, e.bpm, e.camelot, e.vocal_dominance, e.top_styles
            FROM tracks t JOIN embeddings e ON e.track_id = t.id
            WHERE {where}
            ORDER BY t.artist, t.title
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()
    conn.close()

    tracks = []
    for r in rows:
        tid, artist, title, bpm, cam, vd, styles = r
        tracks.append({
            "id": int(tid),
            "artist": str(artist),
            "title": str(title),
            "bpm": round(float(bpm), 1) if bpm is not None else None,
            "camelot": str(cam) if cam is not None else None,
            "vocal_class": vocal_class(float(vd)) if vd is not None else None,
            "styles": list(styles) if styles else [],
        })

    return {"tracks": tracks, "total": total}


def _tracks_by_key(
    camelot: str,
    bpm_min: float | None,
    bpm_max: float | None,
) -> list[dict]:
    conn = get_connection()
    conditions: list[str] = ["t.status = 'indexed'", "e.camelot = %s"]
    params: list[Any] = [camelot]
    if bpm_min is not None:
        conditions.append("e.bpm >= %s")
        params.append(bpm_min)
    if bpm_max is not None:
        conditions.append("e.bpm <= %s")
        params.append(bpm_max)
    where = " AND ".join(conditions)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT t.id, t.artist, t.title, e.bpm, e.camelot "
            f"FROM tracks t JOIN embeddings e ON e.track_id = t.id "
            f"WHERE {where} ORDER BY e.bpm",
            params,
        )
        rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": int(r[0]),
            "artist": str(r[1]),
            "title": str(r[2]),
            "bpm": round(float(r[3]), 1) if r[3] is not None else None,
            "camelot": str(r[4]) if r[4] is not None else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _track_meta(track_id: int, f: dict[str, Any]) -> dict:
    vd = f.get("vocal_dominance")
    styles = f.get("discogs_top5") or []
    return {
        "id":          track_id,
        "artist":      f.get("artist", ""),
        "title":       f.get("title", ""),
        "bpm":         round(f["bpm"], 1) if f.get("bpm") is not None else None,
        "camelot":     f.get("camelot"),
        "vocal_class": vocal_class(vd) if vd is not None else None,
        "styles":      styles,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/search")
def search(q: str = Query(..., min_length=1)) -> list[dict]:
    return _search_tracks(q)


@app.get("/tracks")
def list_tracks() -> list[dict]:
    return _list_tracks()


@app.get("/explore/styles")
def explore_styles() -> list[dict]:
    return _explore_styles()


@app.get("/explore/clusters")
def explore_clusters() -> list[dict]:
    return _explore_clusters()


@app.get("/explore/tracks")
def explore_tracks(
    cluster_id: int | None = Query(default=None),
    bpm_min: float | None = Query(default=None, ge=0),
    bpm_max: float | None = Query(default=None, ge=0),
    camelot: str | None = Query(default=None),
    vocal: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return _explore_tracks(cluster_id, bpm_min, bpm_max, camelot, vocal, limit, offset)


@app.get("/tracks/by-key")
def tracks_by_key(
    camelot: str = Query(..., min_length=2, max_length=3),
    bpm_min: float | None = Query(default=None, ge=0),
    bpm_max: float | None = Query(default=None, ge=0),
) -> list[dict]:
    return _tracks_by_key(camelot, bpm_min, bpm_max)


@app.get("/similar/{track_id}")
def get_similar(track_id: int, top: int = Query(default=15, ge=1, le=400)) -> dict:
    try:
        query = fetch_track_features(track_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Track {track_id} not found or not indexed.")

    candidates = fetch_candidates_by_vector(query["emb_full"], track_id, limit=400)
    if not candidates:
        raise HTTPException(status_code=404, detail="No other indexed tracks to compare against.")

    # Stage 1: how alike the two recordings sound. Untouched by tempo.
    #
    # Skipping a single unusable candidate is deliberate — one row with a
    # missing stem embedding should not sink the request. Skipping every
    # candidate is not a thin catalogue, it is the scoring being broken. This
    # has happened once already: a pgvector upgrade changed the column type,
    # every comparison raised, and the endpoint answered a confident 404 while
    # search and explore looked fine, which sent the search for a cause to the
    # database rather than the loop. So keep the first exception and report it
    # rather than reporting an empty ranking.
    sound_scored: list[tuple[float, int, dict]] = []
    first_error: Exception | None = None
    for tid, f in candidates:
        try:
            sound = similarity(query, f)
        except Exception as exc:
            if first_error is None:
                first_error = exc
                log.exception("similarity() failed for candidate %s", tid)
            continue
        sound_scored.append((sound, tid, f))

    if not sound_scored:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Scoring failed for all {len(candidates)} candidates: "
                f"{type(first_error).__name__}: {first_error}"
            ),
        )

    # Stage 2: demote tracks that could not be mixed with the query.
    #
    # The allowance is a share of this query's own spread rather than a fixed
    # number. Sound scores cluster in a narrow band, so a constant penalty big
    # enough to matter here would sort purely by BPM on a query whose candidates
    # happen to sit closer together. Tying it to the spread means tempo can only
    # ever separate near-ties — it can never outrank a clearly better match.
    sounds = [s for s, _, _ in sound_scored]
    allowance = (max(sounds) - min(sounds)) * TEMPO_PENALTY_SHARE

    scored: list[tuple[float, float, float, int, dict]] = []
    for sound, tid, f in sound_scored:
        penalty = tempo_penalty(query.get("bpm"), f.get("bpm"))
        scored.append((sound - penalty * allowance, sound, penalty, tid, f))

    scored.sort(key=lambda x: x[0], reverse=True)

    all_scores = [s for s, _, _, _, _ in scored]

    results = []
    for score, sound, penalty, tid, f in scored[:top]:
        entry = _track_meta(tid, f)
        entry["score"] = round(score, 4)
        # Both parts are returned so a surprising result can be explained:
        # a low score with a high penalty is a tempo clash, not a bad match.
        entry["sound_score"] = round(sound, 4)
        entry["tempo_penalty"] = round(penalty, 3)
        results.append(entry)

    return {
        "query":          _track_meta(track_id, query),
        "results":        results,
        "total_compared": len(all_scores),
        "highest":        round(max(all_scores), 4) if all_scores else None,
        "lowest":         round(min(all_scores), 4) if all_scores else None,
        "median":         round(statistics.median(all_scores), 4) if all_scores else None,
    }
