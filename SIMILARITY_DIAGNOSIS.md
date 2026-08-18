# Similarity Ranking — Diagnosis & Handoff

Written at the end of an investigation into "random, unrelated tracks appear in
similar-song results." Read this before changing anything in the ranking path —
most of the obvious theories were tested against the live catalogue and are
**dead**, and re-testing them wastes time.

Everything below was measured against the production database unless flagged
otherwise.

---

## 1. The reported symptom

> Searching a dance track (Gorgon City, John Summit) returns tracks that sound
> nothing like it.

## 2. Root cause (confirmed)

**Tempo was computed, stored, displayed and filterable — but contributed nothing
to ranking.**

Neither stage of `/similar/{id}` considered BPM. Candidates are retrieved by
full-mix embedding distance alone, then re-ranked by a blend that was 100%
embeddings. A 103 BPM ballad could — and did — outrank a 138 BPM club track for a
140 BPM query on timbre alone.

Confirmed by pulling the actual Hot 100 tracks reaching dance queries:

| Query | Result | BPM | Verdict |
|---|---|---|---|
| WILL CARRIGAN — Music Sounds Better With Groove (118) | Elton John & Dua Lipa — Cold Heart (PNAU Remix) | 116 | correct |
| " | Sophie Ellis-Bextor — Murder On The Dancefloor | 117 | correct |
| " | Dua Lipa — Houdini | 117 | correct |
| Shermanology — São Paulo (140) | Billie Eilish — No Time To Die | 103 | **wrong** |
| " | Lorde — Yellow Flicker Beat | 95 | **wrong** |
| 999999999 — Dancefloor Murderer (144) | The JaneDear Girls — Wildflower | 118 | **wrong** |

Results are good when the query sits near where pop lives (110–130 BPM) and
collapse above ~135. **Not** for lack of candidates — the Hot 100 set holds 1,457
tracks at 135–150 BPM and 1,023 at 150–165. The ranker simply had no notion that
two tempos cannot be played together.

## 3. Theories tested and ruled out — do not re-investigate

| Theory | Evidence against |
|---|---|
| Rows missing 4-stem embeddings get inflated scores via the fallback weights | `missing_4stem = 0`, `missing_vocals = 0`, `missing_full = 0` across all 16,402 rows. The fallback path never executes. |
| NaN from zero-norm vectors corrupts `sort()` | `0` rows where `muq_full <=> muq_full` is NaN. (The mechanism is real — NaN does strand entries in Python's sort — but no such vector exists.) |
| Hub tracks appear in everyone's results | 150-query × 6-neighbour sample: max appearances = 2, exactly what chance predicts (~25 tracks expected at ≥2). No concentration. |
| Whole sources point at the wrong genre | Objective audio measures match their source: `csv` 5.8% instrumental / tempo-varied (pop), `beatport` 59% instrumental / 62% in dance range. |
| Vocal-vs-instrumental weight profiles bias ranking | Real effect in principle — the weight table changes per pair — but the top-80 candidate pool for vocal queries contains **zero** instrumentals. It never fires. |
| Base rate: Hot 100 is 60% of the catalogue and drowns everything | Backwards. Rekordbox tracks are **5.8×  over**-represented in results, Hot 100 **3× under**-represented. Retrieval already favours the right material. |
| The Discogs classifier says Hot 100 audio is 79% "Electronic", so the audio is wrong | False alarm — only 1,228 of 16,402 rows have style data (7.5%, unrepresentative). Tempo and vocal-dominance contradict it. |

## 4. Confirmed but unresolved

> **Update 2026-08-17: §4a and §4b are now resolved in code — see §9.**

### 4a. Wrong audio from iTunes — real, ongoing (~10% of Hot 100, measured)

`track_ingestion.py` — the path commented `STRICT FIRST` returned **the first
iTunes search result that has a preview, with no verification of artist or
title**. The proper checker (`_score_match`) existed but only ran in the
*fallback* block, which executed only when the strict search returned nothing.
Since iTunes almost always returns something, **the verification was
effectively dead code**.

- **303 tracks** were rejected at ingest for producing an embedding identical to
  an existing track — the error message names the mechanism: *"iTunes likely
  matched the wrong audio (remix not on iTunes, fell back to original track)."*
- That is a **floor, not an estimate**. The guard only fires when the wrong
  answer already exists in the catalogue. Wrong audio landing on any of iTunes'
  other millions of tracks passes silently.
- The second-chance search used `media=all`, so it could return podcasts,
  audiobooks and interviews — all of which have preview URLs. (Measured: ~1% of
  picks were literally feature films.)

### 4b. No provenance is recorded

`tracks` has `itunes_id`, `itunes_preview_url`, `deezer_id`, `audio_r2_key` and
`isrc` columns. **Every one is NULL for every row** ingested before 2026-08-17.
Consequences:

- A wrongly-matched track is indistinguishable from a correct one in the database.
- No ISRC anywhere, so the exact-recording lookup path (ISRC → Deezer preview,
  which would eliminate fuzzy matching entirely) is unavailable from existing data.
- Correction from the original handoff: audio **is** partially retained locally —
  `audio_cache/` holds the ingested m4a for 54% of indexed Hot 100 and 66% of
  Beatport tracks on the dev machine.

### 4c. Score compression — probably the biggest remaining lever

Averaged over 8 random queries, top-100 candidates:

| Rank | 1 | 3 | 5 | 10 | 15 | 25 | 50 |
|---|---|---|---|---|---|---|---|
| Score | 0.9241 | 0.8956 | 0.8893 | 0.8799 | 0.8749 | 0.8662 | 0.8470 |

**Ranks 3–50 span 0.049.** Everything below the top result is effectively tied.
The UI renders these as "90%, 89%, 88%" — an ordering that reads as meaningful
but is mostly noise.

Likely cause is embedding anisotropy: audio embeddings cluster in a narrow cone,
so all pairwise cosines are high and similar. **Standard fix is mean-centering** —
subtract the dataset's mean vector before comparing. Cheap (one average vector,
no re-ingestion) and testable entirely in SQL before touching code.
**Untested. This is a hypothesis, not a finding.**

## 5. What was changed (tempo branch)

Branch `claude/tempo-aware-similarity` (based on `main`, 2 files, 86 lines).
**Merged to `main` 2026-08-18 (PR #2, commit 5392227) — but still unverified
against real result lists; `verify_tempo.sql` is now in the repo root.**

`api_helpers.py` gains `tempo_distance()` and `tempo_penalty()`:

- Octave-folded in log space, so 70 ≡ 140 ≡ 280 BPM read as identical. The BPM
  detector halves and doubles often enough that ignoring this would punish
  correct matches.
- No penalty below 6% apart (pitch-fader range); smoothstep ramp to 18%;
  saturated beyond. Saturation is deliberate — once two tracks cannot be mixed,
  pushing further would make this a tempo sorter.
- Missing BPM → penalty 0. An unknown tempo is not evidence of a bad match, and
  ~641 Hot 100 tracks have none.

`similarity()` is **unchanged** and still returns the pure sound score.

`api.py` `get_similar()` now scores in two stages. The penalty allowance is
**60% of that query's own score spread**, not a constant — given §4c, any fixed
value large enough to matter on one query would rank purely by BPM on another.
Tempo can only separate near-ties. Responses now include `sound_score` and
`tempo_penalty` alongside `score`.

Verified: octave folding exact; all identified bad pairs saturate at 1.0; all
good 118 BPM results stay at ~0.0.
**Not verified: whether result lists are actually better.** See §7.

## 6. Catalogue facts worth knowing

- **16,402 indexed** (+329 failed, 293 pending, 19 processing).
- `source` does **not** indicate genre. Multiple CSVs share `source='csv'` —
  segment on `source_ref`:

| `source_ref` | Tracks |
|---|---|
| `hot100_2007_unique_artist_title.csv` | 9,793 |
| `beatport_releases` (many URLs) | 6,142 |
| `rekordbox_artist_title.csv` | 877 — the owner's actual DJ library |
| `seed_tracks.csv` / `seed_tracks_sample.csv` | 227 |

- **The Hot 100 set is intentional and central to the project thesis**: a
  house-sounding pop record *should* surface next to a house track. Do not filter
  or delete it. The goal is that the *right* chart records surface, not none.
- Audio is 30-second iTunes previews, mean-pooled across the clip.
- Retrieval fetches 400 ANN candidates by `muq_full` only, so re-ranking can only
  reorder what that stage found. `total_compared` reports the surviving candidate
  count, **not** the catalogue size — the UI overstates the search.

## 7. Recommended next steps, in order

1. **Verify the tempo change.** `verify_tempo.sql` (in the diagnosis scratch
   files, or reconstruct from §5) reproduces the new scoring in SQL and prints
   `rank_before` beside `rank_after`. Nothing has confirmed the new lists are
   better — shipping unverified ranking changes is how the current hand-tuned
   weights got their values.
2. **Populate `ground_truth_pairs`** — 30–40 human-rated pairs. This table exists
   and is the bottleneck for everything else. Without it, no tuning decision can
   be evaluated. The existing model comparison scored **Spearman 0.63** on 25
   pairs, and even there a pair rated "very low" (0.456) outscored three rated
   "high" (0.198, 0.277, 0.431) — so some error is the model itself, not the
   plumbing.
3. **Test mean-centering** (§4c). Highest potential upside; do it *after* ground
   truth exists or the result cannot be judged.
4. ~~Fix iTunes matching~~ **Done 2026-08-17, see §9.** Remaining: repair the
   already-damaged rows (§9.4).
5. **Consider key/Camelot in ranking.** It is in the identical position tempo was:
   stored, displayed, filterable, ignored by ranking. Deliberately left out of the
   tempo change so its effect can be measured separately.
6. **Add a quality floor.** The API returns 15 results whether or not 15 good ones
   exist. Padding a thin list with near-tied filler is part of why results feel
   wrong.

## 8. Other known issues

- **Search-as-you-type had an unguarded response race** (`Home.jsx`, `Explore.jsx`,
  `DJMode.jsx`) and **`formatKey` was called but never imported in `DJMode.jsx`**.
  Both were fixed on the frontend redesign branch, which has since been merged to
  `main` (commit 96829e0).
- `npm run lint` reports 7 `react-hooks/set-state-in-effect` errors in the data
  fetching effects. Pre-existing.

---

## 9. Addendum 2026-08-17 — wrong-audio measured; ingestion fixed

### 9.1 How much audio is actually wrong (measured two ways)

**Metadata replay** (210 random indexed tracks; re-run the old first-preview-wins
lookup and score what it picks): ~37% of Hot 100 picks fail naive artist/title
verification, but two-thirds of those are the *correct* audio penalized by
chart-credit formatting ("Beyonce Featuring Kendrick Lamar" vs iTunes
"Beyoncé — Freedom (feat. Kendrick Lamar)"). Genuinely wrong picks:
**~11% Hot 100, ~7% Beatport**. 2/210 picks were feature films via `media=all`.

**Audio-level ground truth** (100 random indexed Hot 100 rows; download the
*verified* iTunes preview, MuQ-embed it, cosine against the stored `muq_full`):

| Verdict | n | Meaning |
|---|---|---|
| correct (cos ≥ 0.98) | 78 | stored audio is the verified recording |
| wrong (cos < 0.90) | 10 | stored audio is some other recording/excerpt¹ |
| gray (0.90–0.98) | 5 | almost certainly right song, different excerpt/encode |
| no verified match | 7 | not confidently on iTunes; unfixable by re-ingest² |

¹ ~6–7 are unambiguous (e.g. cos 0.07 for "Swae Lee — Guatemala"); the
0.77–0.86 band may partly be same-recording/different-preview-window.
² A few may be throttling artifacts; the full scan re-checks them.

**Bottom line: ~1 in 10 Hot 100 rows carries wrong audio. Real and worth a
targeted repair; NOT the cause of "every search looks wrong" — that is §2/§4c,
and the §5 tempo fix, merged 2026-08-18, is still unverified.** Full
catalogue re-ingestion is not
justified (2–4 weeks of compute, ~89% of it reproducing identical embeddings).

### 9.2 Ingestion fix (in `track_ingestion.py`, replaces §4a's dead code)

- `search_itunes_preview()` now verifies **every** result with `_score_match`;
  first-preview-wins and `media=all` are gone; no verified match ⇒ loud
  `ValueError`, never a substitute. Returns match metadata, not a bare URL.
- `_score_match` is credit-aware, calibrated on real failures:
  - feat/ft/featuring credits stripped from both sides ("(feat. X)" titles);
  - bracketed album tags dropped, but bracketed **version markers kept**
    ("[NASHUP Remix]" must mismatch);
  - a version marker (remix/live/acoustic/edit/…) present on the result but
    absent from the request halves the score → "American Boy (TS7 Remix)"
    rejected at 0.40;
  - artist floor raised 0.45 → 0.60 (coincidences measure 0.48–0.56; legitimate
    renderings 0.86+).
- `_itunes_candidates` adds a primary-artist candidate ("A Featuring B",
  "A, B & C", "A x B" → "A") — rescues chart credits iTunes indexes under the
  primary artist; several previously-failed tracks (e.g. Meek Mill — Froze) now
  resolve.
- Provenance recorded: `itunes_id`, `itunes_preview_url`, `audio_fetched_at`
  written on every new ingest (`save_track_features`). Cache-hit ingests leave
  them NULL — origin unknown by definition.
- `muq`/torch import made lazy (metadata-only scripts no longer pay a
  minutes-long `torch._dynamo` import).
- Validated: 7-case block/keep unit suite green; 210-row offline regression
  keeps all 38 legitimate cures and all true rejections.

### 9.3 New tool: `verify_catalog_audio.py`

Read-only, resumable full-catalogue audit (`--group hot100|beatport|rekordbox|all`).
Re-resolves each indexed track through the verified lookup and writes
verified/no_match per row to JSONL. ~3.5 s/track (iTunes rate limits) ⇒ ~10 h
for Hot 100. Its output is the repair worklist.

### 9.4 Remaining repair plan

1. Run the full Hot 100 audit overnight (or `caffeinate -i` in a terminal).
2. For flagged rows: **delete their `audio_cache`/`stems_cache`/
   `embedding_cache`/`feature_cache` entries** (the pipeline trusts caches
   blindly — stale wrong audio would be silently reused), set status
   `pending`, re-run `ingestion_worker.py`. Unverifiable rows fail loudly and
   drop out of the index.
3. Verify the §5 tempo change with `verify_tempo.sql` (merged 2026-08-18,
   still unverified) — the actual "every search" lever.

### 9.5 Corrections to this document

- §4a "small" → measured at ~10% of Hot 100 (§9.1).
- §4b "audio is not retained" → partially retained locally (54% Hot 100 / 66%
  Beatport in `audio_cache/`).
- §8 frontend fixes are merged to `main`; that bullet is resolved.
