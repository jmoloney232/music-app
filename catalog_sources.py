"""Catalog track-list sources for seeding the music similarity database."""

from __future__ import annotations

import csv
import logging
import os
import random
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

log = logging.getLogger(__name__)


TrackSeed = dict[str, str | None]


class CatalogSource(ABC):
    """Base class for any source that yields artist/title seed rows."""

    @abstractmethod
    def fetch_tracks(self) -> Iterator[TrackSeed]:
        """Yield track dictionaries suitable for catalog seeding."""


class SpotifyPlaylistSource(CatalogSource):
    """Fetch tracks from one or more Spotify playlists using app-only auth."""

    TOKEN_URL = "https://accounts.spotify.com/api/token"
    PLAYLIST_ITEMS_URL = "https://api.spotify.com/v1/playlists/{playlist_id}/tracks"

    def __init__(self, playlist_ids: list[str], limit: int = 100) -> None:
        self.playlist_ids = playlist_ids
        self.limit = limit
        self._access_token: str | None = None

    def fetch_tracks(self) -> Iterator[TrackSeed]:
        if not self.playlist_ids:
            return

        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        for playlist_id in self.playlist_ids:
            fetched = 0
            offset = 0
            log.info("Fetching Spotify playlist %s", playlist_id)
            while True:
                payload = self._get_with_rate_limit(
                    self.PLAYLIST_ITEMS_URL.format(playlist_id=playlist_id),
                    headers=headers,
                    params={
                        "limit": self.limit,
                        "offset": offset,
                        "fields": (
                            "items(track(id,type,name,is_local,artists(name),"
                            "external_ids(isrc))),next"
                        ),
                    },
                )
                items = payload.get("items", [])
                if not items:
                    break

                for item in items:
                    track = item.get("track")
                    parsed = self._parse_track(track, playlist_id)
                    if parsed is None:
                        continue
                    fetched += 1
                    yield parsed

                if not payload.get("next"):
                    break
                offset += self.limit

            log.info("Fetched %s usable tracks from Spotify playlist %s", fetched, playlist_id)

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError(
                "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are required only "
                "when using SpotifyPlaylistSource."
            )

        log.info("Requesting Spotify client-credentials token")
        response = self._request_with_rate_limit(
            "post",
            self.TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
        )
        self._access_token = response.json()["access_token"]
        return self._access_token

    def _get_with_rate_limit(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, str | int],
    ) -> dict:
        response = self._request_with_rate_limit(
            "get",
            url,
            headers=headers,
            params=params,
        )
        return response.json()

    @staticmethod
    def _request_with_rate_limit(method: str, url: str, **kwargs: object) -> requests.Response:
        for attempt in range(6):
            response = requests.request(method, url, timeout=30, **kwargs)
            if response.status_code != 429:
                response.raise_for_status()
                return response

            retry_after = response.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
            log.warning("Spotify rate limited request; retrying in %ss", delay)
            time.sleep(delay)

        response.raise_for_status()
        return response

    @staticmethod
    def _parse_track(track: dict | None, playlist_id: str) -> TrackSeed | None:
        if not track:
            return None
        if track.get("is_local"):
            return None
        if track.get("type") != "track":
            return None

        title = (track.get("name") or "").strip()
        artists = track.get("artists") or []
        artist = ", ".join(
            name for name in ((a or {}).get("name", "").strip() for a in artists) if name
        )
        if not artist or not title:
            return None

        external_ids = track.get("external_ids") or {}
        return {
            "artist": artist,
            "title": title,
            "source": "spotify_playlist",
            "source_ref": playlist_id,
            "isrc": external_ids.get("isrc"),
        }


class CSVSource(CatalogSource):
    """Read seed tracks from a CSV with artist and title columns."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch_tracks(self) -> Iterator[TrackSeed]:
        log.info("Fetching tracks from CSV %s", self.path)
        with self.path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                raise ValueError(f"{self.path} is empty or missing a header row")

            columns = {name.lower().strip(): name for name in reader.fieldnames}
            if "artist" not in columns or "title" not in columns:
                raise ValueError(f"{self.path} must include artist and title columns")

            isrc_column = columns.get("isrc")
            count = 0
            for row in reader:
                artist = (row.get(columns["artist"]) or "").strip()
                title = (row.get(columns["title"]) or "").strip()
                if not artist or not title:
                    continue

                count += 1
                yield {
                    "artist": artist,
                    "title": title,
                    "source": "csv",
                    "source_ref": self.path.name,
                    "isrc": (row.get(isrc_column) or "").strip() if isrc_column else None,
                }

        log.info("Fetched %s usable tracks from CSV %s", count, self.path)


# ---------------------------------------------------------------------------
# Scraped sources — shared Playwright infrastructure
# ---------------------------------------------------------------------------

class ScrapedSource(CatalogSource, ABC):
    """Abstract base for JavaScript-heavy scraped sources that need a real browser.

    Handles: Playwright browser lifecycle, polite rate limiting, realistic
    user-agent, and retry on transient page-load failures.

    Subclasses (e.g. BeatportChartSource, future 1001tracklists) only need to
    define `_wait_selector` and `_parse_page` — all browser plumbing lives here.
    """

    _USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    _MAX_RETRIES = 3

    def __init__(self, urls: list[str], page_delay: float = 2.0) -> None:
        self.urls = urls
        self.page_delay = page_delay  # seconds between successive page loads

    @property
    @abstractmethod
    def _wait_selector(self) -> str:
        """CSS selector whose presence confirms the JS content has fully loaded."""

    @abstractmethod
    def _parse_page(self, page: Any, source_url: str) -> list[TrackSeed]:
        """Extract track seeds from the fully-rendered page.

        Must raise a descriptive RuntimeError if the page layout is
        unrecognised — do not return empty silently.
        """

    @staticmethod
    def _new_context(browser: Any) -> Any:
        """Create a browser context with standard UA and viewport."""
        return browser.new_context(
            user_agent=ScrapedSource._USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )

    @staticmethod
    def _new_browser_context(pw: Any) -> tuple[Any, Any]:
        """Launch headless Chromium and return (browser, context)."""
        browser = pw.chromium.launch(headless=True)
        ctx = ScrapedSource._new_context(browser)
        return browser, ctx

    @staticmethod
    def _new_stealthy_page(ctx: Any) -> Any:
        """Create a page and apply playwright-stealth to hide headless indicators.

        Stealth is best-effort: if playwright-stealth is not installed the page
        is returned unpatched with a warning logged once.
        """
        page = ctx.new_page()
        try:
            from playwright_stealth import Stealth
            # navigator_user_agent=False: keep our custom UA, patch everything else
            Stealth(navigator_user_agent=False).apply_stealth_sync(page)
        except ImportError:
            log.warning(
                "playwright-stealth not installed; scraping may be blocked. "
                "Run: pip install playwright-stealth"
            )
        return page

    def fetch_tracks(self) -> Iterator[TrackSeed]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            ) from exc

        with sync_playwright() as pw:
            browser, ctx = self._new_browser_context(pw)
            try:
                for i, url in enumerate(self.urls):
                    if i > 0:
                        time.sleep(self.page_delay)
                    try:
                        tracks = self._load_and_parse(ctx, url)
                        log.info("Scraped %d track(s) from %s", len(tracks), url)
                        yield from tracks
                    except Exception as exc:
                        log.error("Failed to scrape %s — skipping: %s", url, exc)
            finally:
                ctx.close()
                browser.close()

    def _load_and_parse(self, ctx: Any, url: str) -> list[TrackSeed]:
        """Navigate to url (with retries), wait for content, parse, and return seeds."""
        page = self._new_stealthy_page(ctx)
        try:
            for attempt in range(self._MAX_RETRIES):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_selector(self._wait_selector, timeout=20_000)
                    # Brief pause for any deferred JS rendering after the selector appears
                    page.wait_for_timeout(800)
                    return self._parse_page(page, url)
                except Exception as exc:
                    if attempt < self._MAX_RETRIES - 1:
                        delay = 5 * (attempt + 1)
                        log.warning(
                            "Attempt %d/%d failed for %s: %s — retrying in %ds",
                            attempt + 1, self._MAX_RETRIES, url, exc, delay,
                        )
                        time.sleep(delay)
                    else:
                        raise RuntimeError(
                            f"Could not load {url} after {self._MAX_RETRIES} attempts"
                        ) from exc
        finally:
            page.close()
        return []  # unreachable; satisfies type checker


# ---------------------------------------------------------------------------
# Beatport chart scraper
# ---------------------------------------------------------------------------

# JavaScript executed inside the browser to extract track data.
# Two strategies tried in order:
#   1. window.__NEXT_DATA__ — the Next.js server-side page props (most reliable;
#      stable across visual redesigns as long as the API shape holds).
#   2. DOM extraction via href patterns — fallback if __NEXT_DATA__ is absent or
#      doesn't carry the track list (e.g. client-side-only data fetching).
#
# To update for a Beatport layout change: adjust the JS below.  The Python
# side of _parse_page only processes the dict this function returns.
_BEATPORT_EXTRACT_JS = """
() => {
    function mapTrack(t) {
        return {
            name:      (t.name      || '').trim(),
            mix_name:  (t.mix_name  || '').trim(),
            artists:   (t.artists        || []).map(function(a) { return (a.name || '').trim(); }).filter(Boolean),
            // bsrc_remixer is the field name in the catalog API; remixers in older paths
            remixers:  (t.remixers || t.bsrc_remixer || []).map(function(r) { return (r.name || '').trim(); }).filter(Boolean),
        };
    }

    // ── Strategy 1a: Next.js page props (chart / top-100 pages) ────────────
    const nd = window.__NEXT_DATA__;
    if (nd) {
        const pp = nd.props && nd.props.pageProps ? nd.props.pageProps : {};
        // Beatport embeds the track list under different keys depending on page type.
        // NOTE: pp.release.tracks exists on release pages but contains placeholder
        // objects with no data — use the dehydratedState cache instead (strategy 1b).
        const list = (
            pp.tracks ||
            (pp.chart && pp.chart.tracks) ||
            pp.topTracks ||
            (pp.data && pp.data.tracks) ||
            null
        );
        if (Array.isArray(list) && list.length > 0) {
            return { strategy: 'nextData', tracks: list.map(mapTrack) };
        }

        // ── Strategy 1b: dehydratedState React Query cache (release detail pages) ──
        // Release pages don't embed full track objects in pageProps; they're in the
        // prefetched React Query cache under the ["tracks", {release_id: N}] query.
        const ds = pp.dehydratedState;
        if (ds) {
            var queries = ds.queries || [];
            for (var qi = 0; qi < queries.length; qi++) {
                var q = queries[qi];
                if (Array.isArray(q.queryKey) && q.queryKey[0] === 'tracks'
                        && q.queryKey[1] && typeof q.queryKey[1].release_id !== 'undefined') {
                    var results = q.state && q.state.data && q.state.data.results;
                    if (Array.isArray(results) && results.length > 0) {
                        return { strategy: 'dehydratedState', tracks: results.map(mapTrack) };
                    }
                    break;
                }
            }
        }
    }

    // ── Strategy 2: DOM extraction via stable href patterns ─────────────────
    // Beatport URLs: /track/<slug>/<id>  and  /artist/<slug>/<id>
    // These href patterns remain stable even when class names change.

    // innerText respects CSS visibility and avoids picking up hidden clone
    // elements that Beatport renders for mobile/desktop layout toggling.
    function getText(el) {
        return ((el.innerText !== undefined ? el.innerText : el.textContent) || '').trim();
    }

    var rows = [];
    var seenHrefs = {};

    var trackLinks = document.querySelectorAll('a[href*="/track/"]');
    for (var i = 0; i < trackLinks.length; i++) {
        var tLink = trackLinks[i];
        var href = tLink.getAttribute('href');
        if (!href || seenHrefs[href]) continue;
        seenHrefs[href] = true;

        // Climb the DOM to find the tightest row container that also holds
        // artist links.  Stop early at natural row boundaries (LI, ARTICLE)
        // to avoid climbing into a wider section that repeats artist names.
        var container = tLink.parentElement;
        for (var depth = 0; depth < 10; depth++) {
            if (!container || container === document.body) { container = null; break; }
            var tag = container.tagName;
            if (tag === 'LI' || tag === 'ARTICLE' || tag === 'TR') {
                // If this boundary already has artist links, use it; else keep climbing.
                if (container.querySelectorAll('a[href*="/artist/"]').length > 0) break;
                // Natural boundary but no artists yet — keep climbing one more level.
            } else if (container.querySelectorAll('a[href*="/artist/"]').length > 0) {
                break;
            }
            container = container.parentElement;
        }
        if (!container) continue;

        // Deduplicate artists by lowercased name to avoid double-counting when
        // Beatport renders the same artist link in multiple layout variants.
        var artistNodes = container.querySelectorAll('a[href*="/artist/"]');
        var seenArtists = {};
        var artists = [];
        for (var j = 0; j < artistNodes.length; j++) {
            var aName = getText(artistNodes[j]);
            var lower = aName.toLowerCase();
            if (aName && !seenArtists[lower]) {
                seenArtists[lower] = true;
                artists.push(aName);
            }
        }
        if (!artists.length) continue;

        // Mix name: look for a non-anchor element immediately after the track
        // title link inside its parent.  Beatport puts "Original Mix" /
        // "Extended Mix" in a sibling span or p.
        var mixName = '';
        var next = tLink.nextElementSibling;
        if (next && next.tagName !== 'A' && !next.querySelector('a')) {
            var candidate = getText(next);
            if (candidate.length < 80) mixName = candidate;
        }

        rows.push({
            name:     getText(tLink),
            mix_name: mixName,
            artists:  artists,
            remixers: [],
        });
    }

    return { strategy: 'dom', tracks: rows };
}
"""


class BeatportChartSource(ScrapedSource):
    """Scrape track listings from one or more Beatport chart / genre-top-100 pages.

    Constructor
    -----------
    urls       : list of Beatport chart URLs, e.g.
                 ["https://www.beatport.com/genre/drum-and-bass/1/top-100"]
    page_delay : seconds to wait between consecutive page loads (default 2)
    """

    @property
    def _wait_selector(self) -> str:
        # Beatport renders track rows as links to /track/<slug>/<id>
        return 'a[href*="/track/"]'

    def _parse_page(self, page: Any, source_url: str) -> list[TrackSeed]:
        result: dict[str, Any] = page.evaluate(_BEATPORT_EXTRACT_JS)
        strategy = result.get("strategy", "unknown")
        raw: list[dict] = result.get("tracks") or []

        if not raw:
            raise RuntimeError(
                f"Beatport parser found NO tracks on {source_url} "
                f"(strategy tried: {strategy!r}). "
                "The page selectors likely need updating — edit _BEATPORT_EXTRACT_JS "
                "in catalog_sources.py to match the current Beatport DOM."
            )

        seeds: list[TrackSeed] = []
        for t in raw:
            name = (t.get("name") or "").strip()
            mix_name = (t.get("mix_name") or "").strip()
            artists: list[str] = [a for a in (t.get("artists") or []) if a]
            remixers: list[str] = [r for r in (t.get("remixers") or []) if r]

            if not name:
                continue

            # Append mix name unless it is the unremarkable "Original Mix"
            title = name
            if mix_name and mix_name.lower() != "original mix":
                title = f"{name} ({mix_name})"

            all_artists = artists + remixers
            artist_str = ", ".join(all_artists)
            if not artist_str:
                continue

            seeds.append({
                "artist": artist_str,
                "title": title,
                "source": "beatport",
                "source_ref": source_url,
                "isrc": None,
            })

        log.info(
            "Parsed %d track(s) from %s (strategy=%s)", len(seeds), source_url, strategy
        )
        return seeds


# ---------------------------------------------------------------------------
# Beatport releases scraper
# ---------------------------------------------------------------------------

# JavaScript to extract release links and pagination from a genre releases
# listing page.  Two strategies tried in order (same rationale as chart scraper):
#   1. window.__NEXT_DATA__ — most reliable if Beatport SSR-renders the list.
#   2. DOM — find a[href*="/release/{slug}/{id}"] links + max page= number.
_BEATPORT_LISTING_JS = """
() => {
    // ── Strategy 1a: Next.js page props (legacy path) ────────────────────────
    const nd = window.__NEXT_DATA__;
    if (nd) {
        const pp = nd.props && nd.props.pageProps ? nd.props.pageProps : {};
        const releases = pp.releases || (pp.data && pp.data.releases) || null;
        const totalCount = (
            pp.totalCount || pp.total ||
            (pp.data && (pp.data.count || pp.data.total)) ||
            null
        );
        const perPage = pp.perPage || (pp.data && pp.data.perPage) || 25;
        if (Array.isArray(releases) && releases.length > 0) {
            return {
                strategy: 'nextData',
                release_urls: releases.map(function(r) {
                    return r.url || (r.slug && r.id ? '/release/' + r.slug + '/' + r.id : null);
                }).filter(Boolean),
                total_count: typeof totalCount === 'number' ? totalCount : null,
                per_page:    typeof perPage    === 'number' ? perPage    : 25,
            };
        }

        // ── Strategy 1b: dehydratedState React Query cache (current Beatport layout) ──
        // Genre release listing pages store results under a query whose key starts with
        // "releases-" (a URL-param string), not a structured array key.
        const ds = pp.dehydratedState;
        if (ds) {
            var queries = ds.queries || [];
            for (var qi = 0; qi < queries.length; qi++) {
                var q = queries[qi];
                var qk = q.queryKey;
                // queryKey is a 1-element array whose value starts with "releases-"
                var key0 = Array.isArray(qk) ? qk[0] : qk;
                if (typeof key0 === 'string' && key0.indexOf('releases-') === 0) {
                    var data = q.state && q.state.data;
                    if (data && Array.isArray(data.results) && data.results.length > 0) {
                        return {
                            strategy: 'dehydratedState',
                            release_urls: data.results.map(function(r) {
                                // r.url is an internal API URL (api-internal.beatportprod.com) —
                                // always construct the web URL from slug + id instead.
                                return (r.slug && r.id) ? '/release/' + r.slug + '/' + r.id : null;
                            }).filter(Boolean),
                            total_count: typeof data.count  === 'number' ? data.count   : null,
                            per_page:    typeof data.per_page === 'number' ? data.per_page : 25,
                        };
                    }
                    break;
                }
            }
        }
    }

    // ── Strategy 2: DOM ──────────────────────────────────────────────────────
    var seenHrefs = {};
    var releaseUrls = [];
    var links = document.querySelectorAll('a[href*="/release/"]');
    for (var i = 0; i < links.length; i++) {
        var href = links[i].getAttribute('href');
        // /release/{slug}/{numeric-id}  — exclude broader paths like /releases
        if (href && !seenHrefs[href] && /\\/release\\/[^\\/]+\\/\\d+/.test(href)) {
            seenHrefs[href] = true;
            releaseUrls.push(href);
        }
    }

    // Highest page= value found in pagination anchors → total page count
    var totalPages = null;
    var pageLinks = document.querySelectorAll('a[href*="page="]');
    for (var j = 0; j < pageLinks.length; j++) {
        var m = (pageLinks[j].getAttribute('href') || '').match(/[?&]page=(\\d+)/);
        if (m) {
            var n = parseInt(m[1], 10);
            if (!totalPages || n > totalPages) totalPages = n;
        }
    }

    return { strategy: 'dom', release_urls: releaseUrls, total_pages: totalPages };
}
"""


class BeatportReleasesSource(ScrapedSource):
    """Sample random pages from Beatport genre release listings and extract all tracks.

    Constructor
    -----------
    genre_slugs     : list of genre path segments as they appear in Beatport URLs,
                      e.g. ["house/5", "drum-and-bass/1", "techno/6"]
    pages_per_genre : number of random release-listing pages to sample per genre
    seed            : optional integer for reproducible page selection
    page_delay      : seconds between consecutive page loads (default 2)
    max_releases    : if set, cap the number of releases processed per listing page
                      (useful for quick tests — leave None for full scrapes)
    """

    _BASE = "https://www.beatport.com"

    def __init__(
        self,
        genre_slugs: list[str],
        pages_per_genre: int = 3,
        seed: int | None = None,
        page_delay: float = 2.0,
        max_releases: int | None = None,
    ) -> None:
        super().__init__(urls=[], page_delay=page_delay)
        self.genre_slugs = genre_slugs
        self.pages_per_genre = pages_per_genre
        self.rng = random.Random(seed)
        self.max_releases = max_releases

    # ------------------------------------------------------------------
    # ScrapedSource abstract interface (fetch_tracks is overridden below)
    # ------------------------------------------------------------------

    @property
    def _wait_selector(self) -> str:
        return 'a[href*="/release/"]'

    def _parse_page(self, _page: Any, _source_url: str) -> list[TrackSeed]:
        # Not called — fetch_tracks is fully overridden.
        return []

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def fetch_tracks(self) -> Iterator[TrackSeed]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            ) from exc

        seen_keys: set[tuple[str, str]] = set()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                first = True
                for slug in self.genre_slugs:
                    if not first:
                        time.sleep(self.page_delay)
                    first = False
                    yield from self._scrape_genre(browser, slug, seen_keys)
            finally:
                browser.close()

    # ------------------------------------------------------------------
    # Per-genre scraping
    # ------------------------------------------------------------------

    def _scrape_genre(
        self, browser: Any, slug: str, seen_keys: set[tuple[str, str]]
    ) -> Iterator[TrackSeed]:
        base_url = f"{self._BASE}/genre/{slug}/releases"
        log.info("Releases scraper: fetching page 1 for genre %s to determine page count", slug)

        listing_ctx = self._new_context(browser)
        try:
            page1_data = self._load_listing_page(listing_ctx, f"{base_url}?page=1")
        except Exception as exc:
            log.error("Could not load releases listing for genre %s: %s — skipping", slug, exc)
            return
        finally:
            listing_ctx.close()

        total_pages = self._extract_total_pages(page1_data)
        if not total_pages or total_pages < 1:
            log.warning("Could not determine page count for %s; assuming 1", slug)
            total_pages = 1

        log.info("Genre %s: %d total page(s)", slug, total_pages)

        available = list(range(1, total_pages + 1))
        n = min(self.pages_per_genre, len(available))
        picked = sorted(self.rng.sample(available, n))
        log.info("Genre %s: sampled pages %s of %d", slug, picked, total_pages)

        for page_num in picked:
            if page_num == 1:
                listing_data = page1_data
            else:
                time.sleep(self.page_delay)
                listing_ctx = self._new_context(browser)
                try:
                    listing_data = self._load_listing_page(listing_ctx, f"{base_url}?page={page_num}")
                except Exception as exc:
                    log.error(
                        "Failed to load listing page %d for genre %s: %s — skipping",
                        page_num, slug, exc,
                    )
                    continue
                finally:
                    listing_ctx.close()

            release_paths: list[str] = listing_data.get("release_urls") or []
            if self.max_releases is not None:
                release_paths = release_paths[: self.max_releases]
            log.info(
                "Genre %s page %d: %d release(s) found%s",
                slug, page_num, len(listing_data.get("release_urls") or []),
                f" (limited to first {self.max_releases})" if self.max_releases else "",
            )

            for release_path in release_paths:
                time.sleep(self.page_delay)
                release_url = (
                    release_path
                    if release_path.startswith("http")
                    else f"{self._BASE}{release_path}"
                )
                # Fresh browser context per release — Cloudflare tracks state within a
                # context across navigations; a clean context avoids the block.
                release_ctx = self._new_context(browser)
                try:
                    seeds = self._load_release_page(release_ctx, release_url)
                except Exception as exc:
                    log.error("Failed to scrape release %s: %s — skipping", release_url, exc)
                    continue
                finally:
                    release_ctx.close()

                for seed in seeds:
                    key = (
                        (seed.get("artist") or "").lower().strip(),
                        (seed.get("title") or "").lower().strip(),
                    )
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    yield seed

    # ------------------------------------------------------------------
    # Page helpers
    # ------------------------------------------------------------------

    def _extract_total_pages(self, listing_data: dict) -> int | None:
        total_count = listing_data.get("total_count")
        per_page = listing_data.get("per_page") or 150
        if isinstance(total_count, int) and total_count > 0:
            return (total_count + per_page - 1) // per_page
        total_pages = listing_data.get("total_pages")
        if isinstance(total_pages, int) and total_pages > 0:
            return total_pages
        return None

    def _load_listing_page(self, ctx: Any, url: str) -> dict:
        # settle_ms=0: Beatport SPA navigates ~400ms after selector appears, destroying
        # __NEXT_DATA__; extract immediately to avoid the race.
        return self._fetch_url(
            ctx, url,
            'a[href*="/release/"]',
            lambda p: p.evaluate(_BEATPORT_LISTING_JS),
            settle_ms=0,
        )

    def _load_release_page(self, ctx: Any, url: str) -> list[TrackSeed]:
        """Load one release page and extract all tracks.

        Two-strategy approach:
        1. __NEXT_DATA__ dehydratedState (immediate, works when Beatport SSR-inlines data)
        2. XHR interception of api.beatport.com/v4/catalog/releases/{id}/tracks/
           (works when Beatport renders client-side — XHR fires after SPA navigation)
        Retries up to _MAX_RETRIES on transient failures.
        """
        for attempt in range(self._MAX_RETRIES):
            captured: dict = {}  # filled by XHR response listener

            def _on_response(resp: Any) -> None:
                if (
                    "api.beatport.com/v4/catalog/releases/" in resp.url
                    and "/tracks/" in resp.url
                    and "result" not in captured
                ):
                    try:
                        captured["result"] = resp.json()
                    except Exception:
                        pass

            page = self._new_stealthy_page(ctx)
            page.on("response", _on_response)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_selector('h1', timeout=20_000)

                # Phase 1: immediate extraction from __NEXT_DATA__ (0ms settle avoids
                # race with the SPA navigation that fires ~500ms after h1).
                raw = page.evaluate(_BEATPORT_EXTRACT_JS)
                tracks_raw = raw.get("tracks") or []
                strategy = raw.get("strategy", "unknown")

                if not tracks_raw:
                    # Phase 2: wait for the tracks XHR (up to 8 s) then parse.
                    waited = 0
                    while waited < 8_000 and "result" not in captured:
                        page.wait_for_timeout(200)
                        waited += 200
                    if "result" in captured:
                        strategy = "api_intercept"
                        tracks_raw = [
                            {
                                "name": (t.get("name") or "").strip(),
                                "mix_name": (t.get("mix_name") or "").strip(),
                                "artists": [
                                    (a.get("name") or "").strip()
                                    for a in (t.get("artists") or [])
                                ],
                                "remixers": [
                                    (r.get("name") or "").strip()
                                    for r in (t.get("remixers") or t.get("bsrc_remixer") or [])
                                ],
                            }
                            for t in (captured["result"].get("results") or [])
                        ]

                seeds = self._parse_raw_tracks(tracks_raw, url, strategy)
                return seeds

            except Exception as exc:
                if attempt < self._MAX_RETRIES - 1:
                    delay = 5 * (attempt + 1)
                    log.warning(
                        "Attempt %d/%d failed for %s: %s — retrying in %ds",
                        attempt + 1, self._MAX_RETRIES, url, exc, delay,
                    )
                    time.sleep(delay)
                else:
                    raise RuntimeError(
                        f"Could not load release {url} after {self._MAX_RETRIES} attempts"
                    ) from exc
            finally:
                page.close()
        return []  # unreachable; satisfies type checker

    def _parse_raw_tracks(
        self, tracks_raw: list[dict], source_ref: str, strategy: str
    ) -> list[TrackSeed]:
        seeds: list[TrackSeed] = []
        for t in tracks_raw:
            name = (t.get("name") or "").strip()
            mix_name = (t.get("mix_name") or "").strip()
            artists_raw = t.get("artists") or []
            remixers_raw = t.get("remixers") or []
            # artists may be strings (api_intercept pre-processed) or dicts
            artists = [
                a if isinstance(a, str) else (a.get("name") or "")
                for a in artists_raw
            ]
            remixers = [
                r if isinstance(r, str) else (r.get("name") or "")
                for r in remixers_raw
            ]
            artists = [a.strip() for a in artists if a.strip()]
            remixers = [r.strip() for r in remixers if r.strip()]

            if not name:
                continue

            title = name
            if mix_name and mix_name.lower() != "original mix":
                title = f"{name} ({mix_name})"

            artist_str = ", ".join(artists + remixers)
            if not artist_str:
                continue

            seeds.append({
                "artist": artist_str,
                "title": title,
                "source": "beatport_releases",
                "source_ref": source_ref,
                "isrc": None,
            })

        log.info(
            "Parsed %d track(s) from release %s (strategy=%s)",
            len(seeds), source_ref, strategy,
        )
        return seeds

    def _fetch_url(
        self, ctx: Any, url: str, wait_selector: str, parse_fn: Any, settle_ms: int = 800
    ) -> Any:
        """Navigate to url with retry/backoff, call parse_fn(page), return result.

        settle_ms: extra pause after wait_selector appears before calling parse_fn.
        Use 0 for release detail pages — Beatport SPA navigates away ~500 ms after h1,
        which destroys __NEXT_DATA__; extracting immediately avoids the race.
        """
        page = self._new_stealthy_page(ctx)
        try:
            for attempt in range(self._MAX_RETRIES):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_selector(wait_selector, timeout=20_000)
                    if settle_ms > 0:
                        page.wait_for_timeout(settle_ms)
                    return parse_fn(page)
                except Exception as exc:
                    if attempt < self._MAX_RETRIES - 1:
                        delay = 5 * (attempt + 1)
                        log.warning(
                            "Attempt %d/%d failed for %s: %s — retrying in %ds",
                            attempt + 1, self._MAX_RETRIES, url, exc, delay,
                        )
                        time.sleep(delay)
                    else:
                        raise RuntimeError(
                            f"Could not load {url} after {self._MAX_RETRIES} attempts"
                        ) from exc
        finally:
            page.close()
        return None  # unreachable; satisfies type checker
