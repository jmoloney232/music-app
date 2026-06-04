"""
api.py — FastAPI server for Jack's Similar Song Search.

Endpoints:
    GET /search?q=<text>           Search indexed tracks by artist or title
    GET /tracks                    List all indexed tracks
    GET /similar/<id>?top=<n>      Similarity query against the full catalog
"""
from __future__ import annotations

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
    vocal_class,
)

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


@app.get("/similar/{track_id}")
def get_similar(track_id: int, top: int = Query(default=15, ge=1, le=100)) -> dict:
    try:
        query = fetch_track_features(track_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Track {track_id} not found or not indexed.")

    candidates = fetch_candidates_by_vector(query["emb_full"], track_id, limit=100)
    if not candidates:
        raise HTTPException(status_code=404, detail="No other indexed tracks to compare against.")

    scored: list[tuple[float, int, dict]] = []
    for tid, f in candidates:
        try:
            score = similarity(query, f)
        except Exception:
            continue
        scored.append((score, tid, f))

    scored.sort(key=lambda x: x[0], reverse=True)

    all_scores = [s for s, _, _ in scored]

    results = []
    for score, tid, f in scored[:top]:
        entry = _track_meta(tid, f)
        entry["score"] = round(score, 4)
        results.append(entry)

    return {
        "query":          _track_meta(track_id, query),
        "results":        results,
        "total_compared": len(all_scores),
        "highest":        round(max(all_scores), 4) if all_scores else None,
        "lowest":         round(min(all_scores), 4) if all_scores else None,
        "median":         round(statistics.median(all_scores), 4) if all_scores else None,
    }
