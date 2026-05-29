"""
query_similar.py — CLI inspection tool for the similarity engine.

Find and rank the most similar tracks to a query track in the catalog.

Usage:
    python query_similar.py --list
    python query_similar.py --id 3
    python query_similar.py --search "bonobo"
    python query_similar.py --id 3 --top 20
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from track_ingestion import (  # noqa: E402
    get_connection,
    fetch_track_features,
    similarity,
    stable_track_key,
    vocal_class,
)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _list_indexed() -> list[tuple[int, str, str]]:
    """Return [(id, artist, title), ...] for all indexed tracks, ordered by id."""
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
    return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]


def _search_tracks(text: str) -> list[tuple[int, str, str]]:
    """ILIKE search on artist or title among indexed tracks."""
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
    return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]


def _fetch_all_indexed_except(exclude_id: int) -> list[tuple[int, dict[str, Any]]]:
    """Fetch all indexed tracks with embeddings except exclude_id, in one query."""
    conn = get_connection()
    with conn.cursor() as cur:
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
            ORDER BY t.id
            """,
            (exclude_id,),
        )
        rows = cur.fetchall()
    conn.close()

    result: list[tuple[int, dict[str, Any]]] = []
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
        result.append((int(tid), f))
    return result


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _fmt_bpm(bpm: float | None) -> str:
    return f"{bpm:.1f}" if bpm is not None else "n/a"


def _vclass(vd: float | None) -> str:
    if vd is None:
        return "n/a"
    return vocal_class(vd)


_VCLASS_SHORT = {"vocal": "vocal", "instrumental": "instr", "ambiguous": "ambig"}


def _why_notes(query: dict[str, Any], candidate: dict[str, Any]) -> str:
    parts: list[str] = []

    q_styles = query.get("discogs_top5") or []
    c_styles = candidate.get("discogs_top5") or []
    if q_styles and c_styles:
        shared = sorted(set(q_styles) & set(c_styles))
        if shared:
            parts.append("styles: " + ", ".join(shared))
        else:
            parts.append("styles: (no overlap)")

    qc = _VCLASS_SHORT.get(_vclass(query.get("vocal_dominance")), "?")
    cc = _VCLASS_SHORT.get(_vclass(candidate.get("vocal_dominance")), "?")
    parts.append(f"voc: {qc}↔{cc}")

    parts.append(f"BPM: {_fmt_bpm(query.get('bpm'))}↔{_fmt_bpm(candidate.get('bpm'))}")

    return "  |  ".join(parts)


def _score_color(score: float) -> str:
    if score >= 0.75:
        return "green"
    if score >= 0.50:
        return "yellow"
    return "red"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(console: Any) -> None:
    from rich.table import Table

    tracks = _list_indexed()
    if not tracks:
        console.print("[yellow]No indexed tracks found in the catalog.[/yellow]")
        return

    tbl = Table(title=f"Indexed catalog — {len(tracks)} track(s)", show_lines=False)
    tbl.add_column("ID", style="bold cyan", justify="right", no_wrap=True)
    tbl.add_column("Artist", style="bold white")
    tbl.add_column("Title")

    for tid, artist, title in tracks:
        tbl.add_row(str(tid), artist, title)

    console.print(tbl)


def _resolve_track_id(args: argparse.Namespace, console: Any) -> int | None:
    """Return a track id from --id or interactively from --search. None on failure."""
    if args.id is not None:
        return args.id

    matches = _search_tracks(args.search)
    if not matches:
        console.print(
            f"[red]No indexed tracks matching [bold]{args.search!r}[/bold].[/red]"
        )
        return None

    if len(matches) == 1:
        tid, artist, title = matches[0]
        console.print(f"[dim]Matched: [{tid}] {artist} — {title}[/dim]\n")
        return tid

    from rich.table import Table

    tbl = Table(title=f"{len(matches)} matches for {args.search!r} — pick one")
    tbl.add_column("ID", style="bold cyan", justify="right")
    tbl.add_column("Artist", style="bold white")
    tbl.add_column("Title")
    for tid, artist, title in matches:
        tbl.add_row(str(tid), artist, title)
    console.print(tbl)

    try:
        raw = input("\nEnter track ID: ").strip()
        chosen = int(raw)
    except (ValueError, EOFError):
        console.print("[red]Invalid id — aborting.[/red]")
        return None

    if chosen not in {r[0] for r in matches}:
        console.print(f"[red]{chosen} is not in the match list — aborting.[/red]")
        return None

    return chosen


def cmd_query(track_id: int, top_n: int, console: Any) -> None:
    from rich.panel import Panel
    from rich.table import Table

    # Load query track
    try:
        query = fetch_track_features(track_id)
    except Exception:
        console.print(
            f"[red]Track id={track_id} is not indexed or has no embeddings row.[/red]"
        )
        return

    # Load all other indexed tracks in one query
    candidates = _fetch_all_indexed_except(track_id)

    if not candidates:
        console.print("[yellow]No other indexed tracks to compare against.[/yellow]")
        return

    total_catalog = len(candidates) + 1
    if total_catalog < 5:
        console.print(
            f"[yellow]Warning: only {total_catalog} indexed track(s) in the catalog — "
            "too small for a meaningful test.[/yellow]\n"
        )

    # Compute similarity scores
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for tid, f in candidates:
        try:
            score = similarity(query, f)
        except Exception:
            continue
        scored.append((score, tid, f))

    scored.sort(key=lambda x: x[0], reverse=True)

    # ---- Query track header ----
    q_styles = ", ".join(query.get("discogs_top5") or []) or "n/a"
    header = (
        f"[bold white][{track_id}]  {query['artist']} — {query['title']}[/bold white]\n"
        f"[dim]BPM: {_fmt_bpm(query.get('bpm'))}  |  "
        f"Camelot: {query.get('camelot') or 'n/a'}  |  "
        f"vocal: {_vclass(query.get('vocal_dominance'))}  |  "
        f"styles: {q_styles}[/dim]"
    )
    console.print(Panel(header, title="[bold cyan]Query track[/bold cyan]", expand=False))

    # ---- Results table ----
    show = scored[:top_n]
    tbl = Table(
        title=f"Top {len(show)} of {len(scored)} similar tracks",
        show_lines=True,
    )
    tbl.add_column("#", style="bold", justify="right", no_wrap=True)
    tbl.add_column("Score", justify="right", no_wrap=True)
    tbl.add_column("Artist", style="bold white")
    tbl.add_column("Title")
    tbl.add_column("Why", style="dim")

    for rank, (score, _tid, f) in enumerate(show, start=1):
        col = _score_color(score)
        tbl.add_row(
            str(rank),
            f"[{col}]{score:.4f}[/{col}]",
            f["artist"],
            f["title"],
            _why_notes(query, f),
        )

    console.print(tbl)

    # ---- Distribution summary ----
    all_scores = [s for s, _, _ in scored]
    above_half = sum(1 for s in all_scores if s > 0.50)

    dist = Table(title="Score distribution", show_header=False, box=None)
    dist.add_column("Label", style="bold")
    dist.add_column("Value")
    dist.add_row("Tracks compared", str(len(all_scores)))
    dist.add_row("Highest", f"{max(all_scores):.4f}")
    dist.add_row("Lowest", f"{min(all_scores):.4f}")
    dist.add_row("Median", f"{statistics.median(all_scores):.4f}")
    dist.add_row("Above 0.50", f"{above_half} / {len(all_scores)}")
    console.print(dist)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test the similarity engine: rank catalog tracks by similarity to a query track."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="Print all indexed tracks.")
    mode.add_argument("--id", type=int, metavar="N", help="Query track by tracks.id.")
    mode.add_argument("--search", metavar="TEXT", help="Find a track by artist or title (ILIKE).")
    parser.add_argument(
        "--top", type=int, default=15, metavar="N",
        help="Number of results to show (default: 15).",
    )
    return parser.parse_args()


def main() -> None:
    from rich.console import Console

    console = Console()
    args = _parse_args()

    if args.list:
        cmd_list(console)
        return

    track_id = _resolve_track_id(args, console)
    if track_id is None:
        sys.exit(1)

    cmd_query(track_id, args.top, console)


if __name__ == "__main__":
    main()
