"""
test_spotify.py — Dry-run validation of the Spotify API connection and
playlist/track discovery. Reads from the DB to count overlap; writes nothing.

First run: opens a browser for Spotify login. After authorising, the token is
cached in .spotify_cache — subsequent runs skip the browser entirely.

Usage:
    python test_spotify.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# ---------------------------------------------------------------------------
# Step 1 — Check spotipy, then authenticate via OAuth
# ---------------------------------------------------------------------------

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("ERROR: spotipy is not installed.")
    print("Install it with:  pip install spotipy")
    sys.exit(1)

FALLBACK_PLAYLIST_IDS = [
    ("Mint",              "37i9dQZF1DX4dyzvuaRJ0n"),
    ("Dance Rising",      "37i9dQZF1DX8tZsk68tuDw"),
    ("Electronic Rising", "37i9dQZF1DX8AliSIsGeKd"),
    ("Trance Mission",    "37i9dQZF1DX91oIci4su1D"),
    ("Techno Bunker",     "37i9dQZF1DX6J5NfMJS675"),
    ("Housewerk",         "37i9dQZF1DXa8NOEUWPn9W"),
]

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES       = "playlist-read-private playlist-read-collaborative"

print("=" * 60)
print("STEP 1 — Spotify authentication (OAuth)")
print("=" * 60)

client_id     = os.getenv("SPOTIFY_CLIENT_ID")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

if not client_id or not client_secret:
    print("ERROR: SPOTIFY_CLIENT_ID and/or SPOTIFY_CLIENT_SECRET not set in .env")
    sys.exit(1)

cached = ROOT / ".spotify_cache"
if cached.exists():
    print("Found cached token — skipping browser login.")
else:
    print("No cached token found.")
    print("A browser window will open. Log in to Spotify and click Agree.")
    print("The script will continue automatically once you authorise.")
    print()

try:
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        cache_path=str(cached),
        open_browser=True,
    )
    sp = spotipy.Spotify(auth_manager=auth_manager)
    me = sp.current_user()
    name = me.get("display_name") or me.get("id") or "unknown"
    print(f"✓ Authenticated as: {name}")
except Exception as exc:
    print(f"ERROR: Authentication failed — {exc}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 2 — Verify confirmed playlist IDs are reachable
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("STEP 2 — Verifying confirmed playlist IDs")
print("=" * 60)

discovered: list[tuple[str, str]] = []

for name, pid in FALLBACK_PLAYLIST_IDS:
    try:
        info = sp.playlist(pid, fields="id,name")
        resolved_name = info.get("name") or name
        discovered.append((name, pid))
        print(f"  ✓  {pid}  {resolved_name}")
    except Exception as exc:
        print(f"  ✗  {pid}  {name}  ({exc})")

# ---------------------------------------------------------------------------
# Step 3 — Report discovery result
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("STEP 3 — Discovery result")
print("=" * 60)
if discovered:
    print(f"{len(discovered)} of {len(FALLBACK_PLAYLIST_IDS)} playlist IDs verified and reachable.")
else:
    print("No playlist IDs could be verified. Check IDs or Spotify app permissions.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 4 — Dry-run track extraction (first 3 playlists, up to 50 tracks each)
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("STEP 4 — Dry-run track extraction (first 3 playlists, ≤50 tracks each)")
print("=" * 60)

playlists_used: list[str] = []
all_tracks: list[tuple[str, str]] = []

for name, pid in discovered[:3]:
    print(f"\nPlaylist: {name}  [{pid}]")
    try:
        result = sp.playlist_items(
            pid,
            limit=50,
            fields="items(track(name,is_local,type,artists(name))),total",
            additional_types=["track"],
            market="US",
        )
    except Exception as exc:
        print(f"  ERROR: {exc}")
        continue

    items = (result or {}).get("items") or []
    playlist_tracks: list[tuple[str, str]] = []

    for item in items:
        track = (item or {}).get("track")
        if not track:
            continue
        if track.get("is_local") or track.get("type") != "track":
            continue
        title   = (track.get("name") or "").strip()
        artists = track.get("artists") or []
        artist  = ", ".join(
            (a.get("name") or "").strip()
            for a in artists
            if (a.get("name") or "").strip()
        )
        if artist and title:
            playlist_tracks.append((artist, title))

    print(f"  Tracks fetched: {len(playlist_tracks)}")
    print("  First 10:")
    for artist, title in playlist_tracks[:10]:
        print(f"    {artist} — {title}")

    playlists_used.append(name)
    all_tracks.extend(playlist_tracks)

# Deduplicate across playlists (case-insensitive)
seen: set[tuple[str, str]] = set()
unique_tracks: list[tuple[str, str]] = []
for artist, title in all_tracks:
    key = (artist.lower(), title.lower())
    if key not in seen:
        seen.add(key)
        unique_tracks.append((artist, title))

# ---------------------------------------------------------------------------
# DB overlap check — read-only
# ---------------------------------------------------------------------------

already_in_db = 0
new_tracks    = 0

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("\nWARNING: DATABASE_URL not set — skipping DB overlap check.")
    new_tracks = len(unique_tracks)
else:
    try:
        import psycopg
        conn = psycopg.connect(database_url)
        with conn.cursor() as cur:
            for artist, title in unique_tracks:
                cur.execute(
                    "SELECT 1 FROM tracks WHERE artist ILIKE %s AND title ILIKE %s LIMIT 1",
                    (artist, title),
                )
                if cur.fetchone():
                    already_in_db += 1
                else:
                    new_tracks += 1
        conn.close()
        print(f"\nDB overlap check: {already_in_db} already indexed, {new_tracks} new.")
    except Exception as exc:
        print(f"\nWARNING: DB check failed — {exc}")
        new_tracks = len(unique_tracks)

# ---------------------------------------------------------------------------
# Step 5 — Summary
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("STEP 5 — Summary")
print("=" * 60)
print(f"  Playlists discovered : {len(discovered)}")
print(f"  Playlists sampled    : {len(playlists_used)}")
print(f"  Total tracks found   : {len(all_tracks)}  ({len(unique_tracks)} unique)")
print(f"  Already in database  : {already_in_db}")
print(f"  New tracks to seed   : {new_tracks}")
print()
print("Dry run complete — nothing was written to the database.")
