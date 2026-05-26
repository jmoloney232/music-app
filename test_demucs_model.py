"""
Sandbox experiment: compare htdemucs against production htdemucs_ft embeddings.

This script is read-only with respect to the database and does not modify the
production ingestion pipeline. It reuses cached audio only and writes only
isolated experiment MuQ caches under embedding_cache/.

Usage:
    python test_demucs_model.py --limit 30
    python test_demucs_model.py --limit 10 --measure-ft-runtime --ft-runtime-limit 3
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from track_ingestion import (
    AUDIO_CACHE,
    cosine_similarity,
    get_connection,
    get_muq_embedding,
    load_audio_librosa,
    stable_track_key,
)


SAMPLE_BANDS = (
    ("low", 0.0, 0.20),
    ("mid", 0.20, 0.55),
    ("high", 0.55, float("inf")),
)


@dataclass
class TrackBaseline:
    track_id: int
    artist: str
    title: str
    vocal_dominance: float | None
    emb_full: np.ndarray
    emb_vocals: np.ndarray
    emb_backing: np.ndarray

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.title}"

    @property
    def track_key(self) -> str:
        return stable_track_key(self.artist, self.title)

    @property
    def audio_path(self) -> Path:
        return AUDIO_CACHE / f"{self.track_key}.m4a"


@dataclass
class TrackResult:
    track: TrackBaseline
    status: str
    full_cosine: float | None = None
    vocal_cosine: float | None = None
    backing_cosine: float | None = None
    htdemucs_seconds: float | None = None
    note: str = ""


def fetch_indexed_tracks() -> list[TrackBaseline]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(
            """
            SELECT t.id, t.artist, t.title,
                   e.vocal_dominance,
                   e.muq_full, e.muq_vocals, e.muq_backing
            FROM tracks t
            JOIN embeddings e ON e.track_id = t.id
            WHERE t.status = 'indexed'
              AND e.muq_full IS NOT NULL
              AND e.muq_vocals IS NOT NULL
              AND e.muq_backing IS NOT NULL
            ORDER BY t.id
            """
        )
        rows = cur.fetchall()
    conn.close()

    return [
        TrackBaseline(
            track_id=int(row[0]),
            artist=str(row[1]),
            title=str(row[2]),
            vocal_dominance=float(row[3]) if row[3] is not None else None,
            emb_full=_to_float_array(row[4]),
            emb_vocals=_to_float_array(row[5]),
            emb_backing=_to_float_array(row[6]),
        )
        for row in rows
    ]


def choose_varied_tracks(tracks: list[TrackBaseline], limit: int) -> list[TrackBaseline]:
    bands: dict[str, list[TrackBaseline]] = {name: [] for name, _, _ in SAMPLE_BANDS}
    unknown: list[TrackBaseline] = []

    for track in tracks:
        vd = track.vocal_dominance
        if vd is None:
            unknown.append(track)
            continue
        for name, lo, hi in SAMPLE_BANDS:
            if lo <= vd < hi:
                bands[name].append(track)
                break

    selected: list[TrackBaseline] = []
    seen: set[int] = set()
    while len(selected) < limit:
        added = False
        for name, _, _ in SAMPLE_BANDS:
            if bands[name]:
                track = bands[name].pop(0)
                if track.track_id not in seen:
                    selected.append(track)
                    seen.add(track.track_id)
                    added = True
                if len(selected) >= limit:
                    break
        if not added:
            break

    for track in tracks + unknown:
        if len(selected) >= limit:
            break
        if track.track_id not in seen:
            selected.append(track)
            seen.add(track.track_id)

    return selected


def run_demucs_two_stem(audio_path: Path, model_name: str) -> tuple[Path, Path, float, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    start = time.perf_counter()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "demucs",
            "--two-stems=vocals",
            "-n",
            model_name,
            "--out",
            tmp.name,
            str(audio_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )
    seconds = time.perf_counter() - start
    if result.returncode != 0:
        tmp.cleanup()
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{model_name} failed for {audio_path.name}: {detail[-800:]}")

    stem_dir = Path(tmp.name) / model_name / audio_path.stem
    vocals_path = stem_dir / "vocals.wav"
    backing_path = stem_dir / "no_vocals.wav"
    if not vocals_path.exists() or not backing_path.exists():
        tmp.cleanup()
        raise RuntimeError(f"{model_name} did not produce expected two-stem files")
    return vocals_path, backing_path, seconds, tmp


def process_track(track: TrackBaseline) -> TrackResult:
    if not track.audio_path.exists() or track.audio_path.stat().st_size == 0:
        return TrackResult(track=track, status="skipped", note="missing cached audio")

    tmp: tempfile.TemporaryDirectory | None = None
    try:
        full_mix = load_audio_librosa(track.audio_path, 44_100)
        vocals_path, backing_path, seconds, tmp = run_demucs_two_stem(
            track.audio_path,
            "htdemucs",
        )
        vocals = load_audio_librosa(vocals_path, 44_100)
        backing = load_audio_librosa(backing_path, 44_100)

        exp_key = track.track_key
        new_full = get_muq_embedding(full_mix, "experiment_htdemucs_full", exp_key)
        new_vocals = get_muq_embedding(vocals, "experiment_htdemucs_vocals", exp_key)
        new_backing = get_muq_embedding(backing, "experiment_htdemucs_backing", exp_key)

        return TrackResult(
            track=track,
            status="processed",
            full_cosine=cosine_similarity(track.emb_full, new_full),
            vocal_cosine=cosine_similarity(track.emb_vocals, new_vocals),
            backing_cosine=cosine_similarity(track.emb_backing, new_backing),
            htdemucs_seconds=seconds,
        )
    except Exception as exc:
        return TrackResult(track=track, status="skipped", note=str(exc)[:240])
    finally:
        if tmp is not None:
            tmp.cleanup()


def measure_ft_runtime(tracks: list[TrackBaseline], limit: int) -> list[float]:
    timings: list[float] = []
    for track in tracks[:limit]:
        if not track.audio_path.exists() or track.audio_path.stat().st_size == 0:
            continue
        tmp: tempfile.TemporaryDirectory | None = None
        try:
            _, _, seconds, tmp = run_demucs_two_stem(track.audio_path, "htdemucs_ft")
            timings.append(seconds)
            print(f"ft runtime sample [{track.track_id}] {track.label}: {seconds:.2f}s")
        except Exception as exc:
            print(f"ft runtime sample skipped [{track.track_id}] {track.label}: {exc}")
        finally:
            if tmp is not None:
                tmp.cleanup()
    return timings


def print_results(
    results: list[TrackResult],
    threshold: float,
    ft_timings: list[float] | None = None,
) -> None:
    processed = [r for r in results if r.status == "processed"]
    skipped = [r for r in results if r.status != "processed"]

    print()
    print("Per-track results")
    print("-" * 132)
    print(
        f"{'ID':>5}  {'Track':44}  {'VD':>6}  {'full':>8}  {'vocal':>8}  "
        f"{'backing':>8}  {'htdemucs_s':>10}  Note"
    )
    print("-" * 132)
    for result in results:
        track = result.track
        print(
            f"{track.track_id:>5}  "
            f"{_clip(track.label, 44):44}  "
            f"{_fmt(track.vocal_dominance):>6}  "
            f"{_fmt(result.full_cosine):>8}  "
            f"{_fmt(result.vocal_cosine):>8}  "
            f"{_fmt(result.backing_cosine):>8}  "
            f"{_fmt(result.htdemucs_seconds):>10}  "
            f"{result.note}"
        )

    print("-" * 132)
    print()
    print("Aggregate")
    print(f"selected: {len(results)}")
    print(f"processed: {len(processed)}")
    print(f"skipped: {len(skipped)}")

    if not processed:
        print("No tracks processed; cannot compute aggregate stats.")
        return

    full_values = [r.full_cosine for r in processed if r.full_cosine is not None]
    vocal_values = [r.vocal_cosine for r in processed if r.vocal_cosine is not None]
    backing_values = [r.backing_cosine for r in processed if r.backing_cosine is not None]
    htdemucs_times = [
        r.htdemucs_seconds for r in processed if r.htdemucs_seconds is not None
    ]

    full_mean, full_min = _mean_min(full_values)
    vocal_mean, vocal_min = _mean_min(vocal_values)
    backing_mean, backing_min = _mean_min(backing_values)
    htdemucs_mean = statistics.mean(htdemucs_times)

    print(f"full cosine:    mean={full_mean:.6f}  min={full_min:.6f}")
    print(f"vocal cosine:   mean={vocal_mean:.6f}  min={vocal_min:.6f}")
    print(f"backing cosine: mean={backing_mean:.6f}  min={backing_min:.6f}")
    print(f"htdemucs time:  mean={htdemucs_mean:.2f}s/track")

    if ft_timings:
        ft_mean = statistics.mean(ft_timings)
        reduction = 100.0 * (ft_mean - htdemucs_mean) / ft_mean
        print(f"htdemucs_ft time sample: mean={ft_mean:.2f}s/track")
        print(f"runtime reduction: {reduction:.1f}%")
    else:
        reduction = None

    means = [full_mean, vocal_mean, backing_mean]
    avg_similarity_pct = 100.0 * statistics.mean(means)
    verdict_prefix = (
        "ADOPT CANDIDATE"
        if all(value >= threshold for value in means)
        else "KEEP TESTING / KEEP htdemucs_ft"
    )
    runtime_text = (
        f"; measured Demucs runtime reduced by {reduction:.1f}%"
        if reduction is not None
        else "; htdemucs_ft runtime was not measured"
    )
    print()
    print(
        f"Verdict: {verdict_prefix}. htdemucs embeddings are on average "
        f"{avg_similarity_pct:.2f}% similar to htdemucs_ft across full/vocal/backing"
        f"{runtime_text}."
    )


def _to_float_array(value: Any) -> np.ndarray:
    return np.array(value, dtype=np.float32)


def _mean_min(values: list[float]) -> tuple[float, float]:
    return statistics.mean(values), min(values)


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _clip(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return value[:width - 1] + "…"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare htdemucs against htdemucs_ft baseline embeddings."
    )
    parser.add_argument("--limit", type=int, default=30, help="Number of tracks to test")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.97,
        help="Mean cosine threshold required for adoption verdict",
    )
    parser.add_argument(
        "--measure-ft-runtime",
        action="store_true",
        help="Also time htdemucs_ft on a small sample for runtime reduction",
    )
    parser.add_argument(
        "--ft-runtime-limit",
        type=int,
        default=5,
        help="Number of tracks to time with htdemucs_ft when enabled",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    all_tracks = fetch_indexed_tracks()
    selected = choose_varied_tracks(all_tracks, args.limit)

    print(f"Fetched {len(all_tracks)} indexed baseline tracks from DB.")
    print(f"Selected {len(selected)} varied tracks for experiment.")
    print("No DB writes or audio downloads will be performed.")

    results: list[TrackResult] = []
    for index, track in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] {track.label}")
        result = process_track(track)
        results.append(result)
        if result.status == "processed":
            print(
                f"  full={result.full_cosine:.4f} "
                f"vocal={result.vocal_cosine:.4f} "
                f"backing={result.backing_cosine:.4f} "
                f"htdemucs={result.htdemucs_seconds:.2f}s"
            )
        else:
            print(f"  skipped: {result.note}")

    ft_timings = None
    if args.measure_ft_runtime:
        print()
        print(f"Measuring htdemucs_ft runtime on up to {args.ft_runtime_limit} tracks...")
        ft_timings = measure_ft_runtime(selected, args.ft_runtime_limit)

    print_results(results, threshold=args.threshold, ft_timings=ft_timings)


if __name__ == "__main__":
    main()
