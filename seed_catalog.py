"""Seed the tracks table from pluggable catalog sources."""

from __future__ import annotations

import argparse
import logging
import os
import re
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

from catalog_sources import (
    BeatportChartSource,
    BeatportReleasesSource,
    CSVSource,
    CatalogSource,
    SpotifyPlaylistSource,
    TrackSeed,
)


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BATCH_SIZE = 500


def normalize_track_key(artist: str, title: str) -> tuple[str, str]:
    return (_normalize_text(artist), _normalize_text(title))


def seed_catalog(sources: list[CatalogSource], dry_run: bool = False) -> dict[str, int]:
    fetched = 0
    deduped_tracks: dict[tuple[str, str], TrackSeed] = {}

    for source in sources:
        source_count = 0
        for track in source.fetch_tracks():
            fetched += 1
            source_count += 1
            artist = (track.get("artist") or "").strip()
            title = (track.get("title") or "").strip()
            if not artist or not title:
                continue
            key = normalize_track_key(artist, title)
            deduped_tracks.setdefault(
                key,
                {
                    "artist": artist,
                    "title": title,
                    "source": track.get("source") or "unknown",
                    "source_ref": track.get("source_ref") or "",
                    "isrc": track.get("isrc") or None,
                },
            )
        log.info("Collected %s tracks from %s", source_count, source.__class__.__name__)

    rows = list(deduped_tracks.values())
    deduped = len(rows)
    log.info("Fetched %s rows; %s remain after batch dedupe", fetched, deduped)

    if dry_run:
        print(f"Dry run: would insert up to {deduped} unique tracks.")
        for track in rows:
            print(
                f"- {track['artist']} - {track['title']} "
                f"({track['source']}:{track['source_ref']})"
            )
        return {
            "fetched": fetched,
            "deduped": deduped,
            "inserted": 0,
            "skipped_existing": 0,
        }

    inserted = _insert_tracks(rows)
    skipped_existing = deduped - inserted
    summary = {
        "fetched": fetched,
        "deduped": deduped,
        "inserted": inserted,
        "skipped_existing": skipped_existing,
    }
    log.info("Seed summary: %s", summary)
    return summary


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().strip())


def _get_connection() -> Any:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required for non-dry-run catalog seeding")
    return psycopg.connect(url)


def _insert_tracks(rows: list[TrackSeed]) -> int:
    if not rows:
        return 0

    inserted = 0
    with _get_connection() as conn:
        with conn.cursor() as cur:
            for start in range(0, len(rows), BATCH_SIZE):
                batch = rows[start:start + BATCH_SIZE]
                placeholders = ", ".join(["(%s, %s, %s, 'pending', %s, %s, NOW())"] * len(batch))
                params: list[str | None] = []
                for row in batch:
                    params.extend([
                        row["artist"],
                        row["title"],
                        row.get("isrc"),
                        row.get("source"),
                        row.get("source_ref"),
                    ])

                cur.execute(
                    f"""
                    INSERT INTO tracks
                        (artist, title, isrc, status, source, source_ref, created_at)
                    VALUES {placeholders}
                    ON CONFLICT (artist, title) DO NOTHING
                    RETURNING id
                    """,
                    params,
                )
                inserted += len(cur.fetchall())

    return inserted


def build_sources(args: argparse.Namespace) -> list[CatalogSource]:
    sources: list[CatalogSource] = []
    if args.csv:
        sources.extend(CSVSource(path) for path in args.csv)
    if args.spotify:
        sources.append(SpotifyPlaylistSource(args.spotify))
    if args.beatport_file:
        urls = [
            line.strip()
            for line in Path(args.beatport_file).read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if urls:
            sources.append(BeatportChartSource(urls))
    if args.beatport_releases:
        sources.append(
            BeatportReleasesSource(
                genre_slugs=args.beatport_releases,
                pages_per_genre=args.pages_per_genre,
                seed=args.seed,
                max_releases=args.max_releases,
            )
        )
    return sources


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed pending tracks from catalog sources.")
    parser.add_argument("--csv", nargs="+", help="CSV file(s) with artist and title columns")
    parser.add_argument("--spotify", nargs="+", help="Spotify playlist ID(s)")
    parser.add_argument(
        "--beatport-file",
        metavar="FILE",
        help="Text file with one Beatport chart URL per line (# comments ignored)",
    )
    parser.add_argument(
        "--beatport-releases",
        nargs="+",
        metavar="GENRE",
        help="Genre path segments for releases scraping, e.g. house/5 drum-and-bass/1",
    )
    parser.add_argument(
        "--pages-per-genre",
        type=int,
        default=3,
        metavar="N",
        help="Random release-listing pages to sample per genre (default: 3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="N",
        help="Random seed for reproducible page selection",
    )
    parser.add_argument(
        "--max-releases",
        type=int,
        default=None,
        metavar="N",
        help="Cap releases processed per listing page (useful for quick tests)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print tracks without writing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = build_sources(args)
    if not sources:
        raise SystemExit("Provide at least one source: --csv path.csv or --spotify PLAYLIST_ID")

    summary = seed_catalog(sources, dry_run=args.dry_run)
    print(summary)


if __name__ == "__main__":
    main()
