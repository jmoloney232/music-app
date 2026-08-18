# Product Brief — Similar Song Search (design-blind)

This brief describes **what the product does**, deliberately omitting every
visual/design decision of the current implementation. It exists so a designer
can propose directions without being anchored.

## What it is

A personal music-similarity engine for a DJ. A catalogue of ~16,000 tracks
(Billboard Hot 100 entries 2007–present, Beatport dance releases, and the
owner's own DJ library) where every track has been analyzed from a 30-second
audio clip. Tracks are compared **by how they sound** — audio embeddings of the
full mix and of separated stems (vocals/drums/bass/other) — not by genre tags.
The core promise: pick any track and see what else in the catalogue *actually
sounds like it*, with the data a DJ needs to decide whether two records can be
mixed (tempo and musical key).

Users: the owner and friends — music-literate, DJ-adjacent. Used on desktop and
phone. Backend is a REST API; frontend is a single-page app. The server sleeps
when idle (free tier), so a first request can take up to ~30 s — the UI must
have an honest "waking up" state.

## Domain concepts the design must serve

- **Similarity score** (0–1, shown as %): how alike two tracks sound. Scores
  compress toward the top (a #3 result at 89% and a #40 at 85% are nearly
  tied) — the design should not oversell precision; relative order and tiers
  matter more than exact digits.
- **BPM (tempo)**: two tracks are realistically mixable within about ±6% of
  each other.
- **Musical key, Camelot notation**: 24 keys arranged on a wheel — positions
  1–12, each with an "A" (minor) and "B" (major) variant, e.g. `8A` = A minor.
  **Compatible keys** for harmonic mixing = same key, the A/B partner (relative
  major/minor), and ±1 position on the wheel (e.g. 8A → 8A, 8B, 7A, 9A).
  Tracks in compatible keys are the ones a DJ can mix into.
- **Vocal class**: each track is Vocal, Instrumental, or Mixed (from measured
  vocal dominance).
- **Style tags**: 0–5 genre/style labels per track (e.g. "House", "Trance",
  "Pop Rock"), machine-derived, present on most but not all tracks.
- **No artwork**: the catalogue has no album art today. Designs must stand on
  typography/data alone (a direction may propose artwork as a future
  enhancement, but must degrade gracefully without it).

## Screens & features (complete)

### 1. Search (landing)
- One search field: find a track in the catalogue by artist or title.
  Search-as-you-type (debounced ~300 ms), results as a simple list of
  artist + title; clicking one goes to Similar Results for that track.
- Before first input: a handful of example artist chips to seed exploration.
- States: searching spinner; "no matches" with a pointer to the catalogue
  browser; network-error message; slow-server ("waking up, can take 30 s").

### 2. Similar Results (the core screen)
- Shows the **query track** ("matching against …"): title, artist, BPM, key
  (Camelot + traditional, e.g. "8A / A minor"), vocal class, style tags, and a
  link to open the track on Spotify.
- Summary stats for the comparison: number of candidates compared
  (~hundreds), best / median / lowest similarity %.
- **Ranked result list** (15 at a time, "show 15 more" up to 100): rank,
  title, artist, similarity score (bar + %), BPM, key, optional style tag,
  Spotify link. Every result is clickable and becomes the new query —
  chained exploration is a primary behavior.
- Rows whose key is harmonically compatible with the query are visibly
  marked, without requiring any filter to be on.
- **Filters**: key = All / Compatible keys / Exact key; BPM ±6% toggle
  (only when the query has a BPM). Active filters show "N of M" and a
  zero-results state offers one-tap clear.

### 3. Catalogue browser ("Explore")
- Browse/filter the whole indexed catalogue, 50 rows a page with a running
  total ("N tracks match").
- Filters, combinable: **sound cluster** chips (machine-found groupings with
  names and track counts), **BPM range** (double-ended slider ~60–220),
  **key** (dropdown of all 24 Camelot keys), **vocal type** (vocal /
  instrumental / mixed).
- Rows show rank, title/artist, BPM, key, vocal class, style tags; click →
  Similar Results. Skeleton rows while loading.

### 4. Browse by key ("DJ mode")
- An **interactive Camelot wheel**: 24 clickable segments — inner ring the 12
  minor ("A") keys, outer ring the 12 major ("B") keys — each labeled with
  Camelot code and short key name. Selecting a segment shows every catalogue
  track in that key, sorted by BPM; selecting again deselects. Center of the
  wheel shows the current selection ("8A — A minor") or a prompt.
- Optional BPM-range filter (toggle + double slider) narrows the list.
- Purpose: answer "I'm in 8A at 128 — what can I play next?"

### 5. Collections
- Hand-curated playlists, separate from what the algorithm finds: name,
  description, track count, and a small strip visualizing the keys present in
  the collection. Grid of collection cards → detail page listing tracks
  (each row → Similar Results).
- Currently scaffolded with six named-but-empty collections ("Late Night
  Drive", "Peak Time", …) — the empty state matters.

### Global
- Persistent navigation among: Search, Explore, Browse-by-key, Collections.
- A footer exists. Mobile layouts for everything; track rows must survive
  long titles/artist names by truncation.
- Every track row anywhere links out to Spotify (opens a search for
  artist + title).

## API surface (for realistic mocking)

- `GET /search?q=` → `[{id, artist, title}]`
- `GET /similar/{id}?top=100` → `{query: {id, artist, title, bpm, camelot,
  vocal_class, styles[]}, results: [{…same fields, score}], total_compared,
  highest, median, lowest}`
- `GET /explore/clusters` → `[{id, name, count}]`
- `GET /explore/tracks?cluster_id&bpm_min&bpm_max&camelot&vocal&limit&offset`
  → `{tracks: […], total}`
- `GET /tracks/by-key?camelot&bpm_min&bpm_max` → `[…]` sorted by BPM

## Fixture data (use for mockups)

Query: **Gorgon City — Imagination** · 124.0 BPM · 7A / D minor · Vocal ·
House. Compared 387 · best 92% · median 84% · lowest 71%.

| # | Title | Artist | % | BPM | Key | Class | Style |
|---|---|---|---|---|---|---|---|
| 1 | Losing It | FISHER | 92 | 125.0 | 7A | Instrumental | Tech House |
| 2 | Cola | CamelPhat & Elderbrook | 91 | 122.0 | 12A | Vocal | House |
| 3 | Murder On The Dancefloor | Sophie Ellis-Bextor | 89 | 117.0 | 8A | Vocal | Disco |
| 4 | On My Mind | Diplo & SIDEPIECE | 89 | 124.0 | 7B | Vocal | Tech House |
| 5 | Cold Heart (PNAU Remix) | Elton John & Dua Lipa | 88 | 116.0 | 6A | Vocal | Dance-pop |
| 6 | Rumble | Skrillex, Fred again.. & Flowdan | 87 | 140.0 | 2A | Vocal | UK Garage |
| 7 | Houdini | Dua Lipa | 87 | 117.0 | 3A | Vocal | Dance-pop |
| 8 | Baby again.. | Fred again.., Skrillex & Four Tet | 86 | 130.0 | 7A | Instrumental | House |

(7A-compatible keys here: 7A, 7B, 6A, 8A — rows 1, 3, 4, 5, 8.)

Clusters for Explore chips: "Peak-time techno" (412) · "Vocal house" (388) ·
"Chart pop" (2,051) · "Melodic/deep" (623) · "Hip-hop adjacent" (940) ·
"Ballads & downtempo" (1,204).
