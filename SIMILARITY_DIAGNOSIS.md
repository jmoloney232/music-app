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
| Base rate: Hot 100 is 60% of the catalogue and drowns everything | Backwards. Rekordbox tracks are **5.8× over**-represented in results, Hot 100 **3× under**-represented. Retrieval already favours the right material. |
| The Discogs classifier says Hot 100 audio is 79% "Electronic", so the audio is wrong | False alarm — only 1,228 of 16,402 rows have style data (7.5%, unrepresentative). Tempo and vocal-dominance contradict it. |

## 4. Confirmed but unresolved

### 4a. Wrong audio from iTunes — real, small, ongoing

`track_ingestion.py:238` — the path commented `STRICT FIRST` returns **the first
iTunes search result that has a preview, with no verification of artist or
title**. The proper checker (`_score_match`, 0.45 artist floor, 0.72 confidence
threshold) exists but only runs in the *fallback* block, which executes only when
the strict search returns nothing. Since iTunes almost always returns something,
**the verification is effectively dead code**.

- **303 tracks** were rejected at ingest for producing an embedding identical to
  an existing track — the error message names the mechanism: *"iTunes likely
  matched the wrong audio (remix not on iTunes, fell back to original track)."*
- That is a **floor, not an estimate**. The guard only fires when the wrong
  answer already exists in the catalogue. Wrong audio landing on any of iTunes'
  other millions of tracks passes silently.
- The second-chance search uses `media=all`, so it can return podcasts,
  audiobooks and interviews — all of which have preview URLs.
- **This path is still live.** Every newly ingested track can get wrong audio.

### 4b. No provenance is recorded

`tracks` has `itunes_id`, `itunes_preview_url`, `deezer_id`, `audio_r2_key` and
`isrc` columns. **Every one is NULL for every row.** The schema was added; the
ingestion never writes to it. Consequences:

- A wrongly-matched track is indistinguishable from a correct one in the database.
- Audio is not retained, so after-the-fact listening checks are impossible.
- No ISRC anywhere, so the exact-recording lookup path (ISRC → Deezer preview,
  which would eliminate fuzzy matching entirely) is unavailable from existing data.

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

## 5. What was changed

Branch `claude/tempo-aware-similarity` (based on `main`, 2 files, 86 lines).

`api_helpers.py` gains `tempo_distance()` and `tempo_penalty()`:

- Octave-folded in log space, so 70 ↔ 140 ↔ 280 BPM read as identical. The BPM
  detector halves and doubles often enough that ignoring this would punish
  correct matches.
- No penalty below 6% apart (pitch-fader range); smoothstep ramp to 18%;
  saturated beyond. Saturation is deliberate — once two tracks cannot be mixed,
  pushing further would make this a tempo sorter.
- Missing BPM ⇒ penalty 0. An unknown tempo is not evidence of a bad match, and
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
4. **Fix iTunes matching** (§4a): move `_score_match` onto the main path, drop the
   `media=all` fallback, fail loudly instead of substituting, and populate the
   provenance columns. Stops the problem growing.
5. **Consider key/Camelot in ranking.** It is in the identical position tempo was:
   stored, displayed, filterable, ignored by ranking. Deliberately left out of the
   tempo change so its effect can be measured separately.
6. **Add a quality floor.** The API returns 15 results whether or not 15 good ones
   exist. Padding a thin list with near-tied filler is part of why results feel
   wrong.

## 8. Other known issues

- **Search-as-you-type had an unguarded response race** (`Home.jsx`, `Explore.jsx`,
  `DJMode.jsx`): the timer was debounced but not the response, so a slow early
  fetch could land after a newer one and show stale results. Fixed on the frontend
  redesign branch only — **still present on `main`.**
- **`formatKey` was called but never imported in `DJMode.jsx`**, throwing a
  `ReferenceError` on both branches of the key-selection path. Fixed on the
  redesign branch only — **still present on `main`.**
- `npm run lint` reports 7 `react-hooks/set-state-in-effect` errors in the data
  fetching effects. Pre-existing, present on `main`.
- Branch `claude/frontend-redesign-tan-grey-nkf4y2` holds a full light-theme
  rebuild (26 files). Rendered and contrast-audited against fixture data only —
  **never run against the real API.**
