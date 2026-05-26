"""
Experimental 4-stem track feature extraction pipeline.

This module intentionally leaves track_ingestion.py, the ingestion worker, and
the database schema untouched. It is for manual comparison of Demucs 4-stem
MuQ embeddings:

    python track_ingestion_4stem.py "Artist" "Title"
    python track_ingestion_4stem.py "Artist A" "Title A" "Artist B" "Title B"
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from track_ingestion import (
    STEMS_CACHE,
    compute_essentia_core,
    compute_essentia_tf,
    compute_vocal_dominance,
    cosine_similarity,
    ensure_dirs,
    fetch_audio,
    get_muq_embedding,
    load_audio_librosa,
    stable_track_key,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)

STEM_NAMES = ("vocals", "drums", "bass", "other")
FOUR_STEM_WEIGHTS = {
    "full": 0.35,
    "vocals": 0.20,
    "drums": 0.15,
    "bass": 0.15,
    "other": 0.10,
    "style": 0.05,
}


def get_4stems(audio_path: Path, track_key: str) -> dict[str, Path]:
    """Run Demucs standard 4-stem separation and return cached stem paths."""
    stem_paths = {
        stem: STEMS_CACHE / f"{track_key}_4stem_{stem}.wav"
        for stem in STEM_NAMES
    }

    if all(path.exists() and path.stat().st_size > 0 for path in stem_paths.values()):
        log.info("4-stem cache hit: %s", track_key)
        return stem_paths

    log.info("running Demucs 4-stem htdemucs_ft on: %s", audio_path.name)
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m", "demucs",
                    "-n", "htdemucs_ft",
                    "--out", tmpdir,
                    str(audio_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=900,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Demucs is not installed for this Python environment. Install it with "
                "`pip install demucs`, then rerun the 4-stem ingestion."
            ) from exc
        if result.returncode != 0:
            raise RuntimeError(
                f"Demucs 4-stem failed for {audio_path.name}:\n{result.stderr}"
            )

        stem_dir = Path(tmpdir) / "htdemucs_ft" / audio_path.stem
        for stem, dest in stem_paths.items():
            src = stem_dir / f"{stem}.wav"
            if not src.exists():
                raise RuntimeError(f"Demucs did not produce expected stem: {src}")
            dest.unlink(missing_ok=True)
            shutil.move(str(src), str(dest))

    log.info("4-stems cached: %s", track_key)
    return stem_paths


def _mix_stems(stems: list[np.ndarray]) -> np.ndarray:
    if not stems:
        raise ValueError("No stems supplied for mixing")
    min_len = min(len(stem) for stem in stems)
    stacked = np.vstack([stem[:min_len] for stem in stems])
    return stacked.sum(axis=0).astype(np.float32)


def ingest_one_track_4stem(artist: str, title: str) -> dict[str, Any]:
    """Fetch, separate, and embed one track with Demucs 4-stem separation."""
    ensure_dirs()
    track_key = stable_track_key(artist, title)

    audio_path = fetch_audio(artist, title, track_key)

    log.info("loading full mix: %s - %s", artist, title)
    full_mix_wav = load_audio_librosa(audio_path, 44_100)
    duration = len(full_mix_wav) / 44_100

    stem_paths = get_4stems(audio_path, track_key)

    log.info("loading 4 stems")
    vocals_wav = load_audio_librosa(stem_paths["vocals"], 44_100)
    drums_wav = load_audio_librosa(stem_paths["drums"], 44_100)
    bass_wav = load_audio_librosa(stem_paths["bass"], 44_100)
    other_wav = load_audio_librosa(stem_paths["other"], 44_100)
    instrumental_wav = _mix_stems([drums_wav, bass_wav, other_wav])

    log.info("computing vocal dominance")
    vocal_dominance = compute_vocal_dominance(vocals_wav, full_mix_wav, sr=44_100)

    log.info("computing 4-stem MuQ embeddings")
    emb_full = get_muq_embedding(full_mix_wav, "full", track_key)
    emb_vocals = get_muq_embedding(vocals_wav, "4stem_vocals", track_key)
    emb_drums = get_muq_embedding(drums_wav, "4stem_drums", track_key)
    emb_bass = get_muq_embedding(bass_wav, "4stem_bass", track_key)
    emb_other = get_muq_embedding(other_wav, "4stem_other", track_key)
    emb_instrumental = get_muq_embedding(
        instrumental_wav,
        "4stem_instrumental",
        track_key,
    )

    log.info("computing Essentia core features")
    core = compute_essentia_core(full_mix_wav, track_key)

    log.info("computing Essentia TF features")
    tf_feats = compute_essentia_tf(audio_path, track_key)

    return {
        "artist": artist,
        "title": title,
        "track_key": track_key,
        "duration_s": duration,
        "stem_mode": "demucs_4stem",
        "stem_paths": {stem: str(path) for stem, path in stem_paths.items()},
        # Essentia core
        "bpm": core.get("bpm"),
        "key": core.get("key"),
        "scale": core.get("scale"),
        "key_strength": core.get("key_strength"),
        "camelot": core.get("camelot"),
        "danceability": core.get("danceability"),
        "mfcc_mean": core.get("mfcc_mean"),
        # Vocal analysis
        "vocal_dominance": vocal_dominance,
        # MuQ embeddings
        "emb_full": emb_full,
        "emb_vocals": emb_vocals,
        "emb_drums": emb_drums,
        "emb_bass": emb_bass,
        "emb_other": emb_other,
        "emb_instrumental": emb_instrumental,
        # TF features (may be None on M-series fallback)
        "mood_happy": tf_feats.get("mood_happy") if tf_feats else None,
        "mood_sad": tf_feats.get("mood_sad") if tf_feats else None,
        "mood_relaxed": tf_feats.get("mood_relaxed") if tf_feats else None,
        "mood_aggressive": tf_feats.get("mood_aggressive") if tf_feats else None,
        "mood_acoustic": tf_feats.get("mood_acoustic") if tf_feats else None,
        "mood_party": tf_feats.get("mood_party") if tf_feats else None,
        "arousal": tf_feats.get("arousal") if tf_feats else None,
        "valence": tf_feats.get("valence") if tf_feats else None,
        "discogs_styles_400": tf_feats.get("discogs_styles_400") if tf_feats else None,
        "discogs_top5": tf_feats.get("discogs_top5") if tf_feats else None,
    }


def similarity_4stem(f_a: dict[str, Any], f_b: dict[str, Any]) -> float:
    """Manual 4-stem similarity score for experiment comparison."""
    weights = dict(FOUR_STEM_WEIGHTS)

    sims = {
        "full": cosine_similarity(f_a["emb_full"], f_b["emb_full"]),
        "vocals": cosine_similarity(f_a["emb_vocals"], f_b["emb_vocals"]),
        "drums": cosine_similarity(f_a["emb_drums"], f_b["emb_drums"]),
        "bass": cosine_similarity(f_a["emb_bass"], f_b["emb_bass"]),
        "other": cosine_similarity(f_a["emb_other"], f_b["emb_other"]),
    }

    if f_a.get("discogs_styles_400") and f_b.get("discogs_styles_400"):
        sims["style"] = cosine_similarity(
            np.array(f_a["discogs_styles_400"]),
            np.array(f_b["discogs_styles_400"]),
        )
    else:
        weights["full"] += weights["style"]
        weights["style"] = 0.0
        sims["style"] = 0.0

    return float(sum(weights[name] * sims[name] for name in weights))


def print_track_summary_4stem(f: dict[str, Any]) -> None:
    try:
        from rich import print as rprint
        from rich.panel import Panel
        from rich.table import Table
    except ImportError:
        _print_plain_summary(f)
        return

    label = f"{f['artist']} - {f['title']}"
    rprint(Panel(f"[bold white]{label}[/bold white]  [dim]{f['duration_s']:.1f}s[/dim]",
                 expand=False))

    core_tbl = Table(show_header=True, header_style="bold magenta", box=None)
    core_tbl.add_column("Feature", style="bold")
    core_tbl.add_column("Value")
    core_tbl.add_row("Stem Mode", f.get("stem_mode", "n/a"))
    core_tbl.add_row("BPM", f"{f['bpm']:.1f}" if f.get("bpm") is not None else "n/a")
    core_tbl.add_row("Key", f"{f.get('key', 'n/a')} {f.get('scale', '')}".strip())
    core_tbl.add_row("Camelot", f.get("camelot") or "n/a")
    core_tbl.add_row(
        "Danceability",
        f"{f['danceability']:.3f}" if f.get("danceability") is not None else "n/a",
    )
    core_tbl.add_row(
        "Vocal Dominance",
        f"{f['vocal_dominance']:.4f}" if f.get("vocal_dominance") is not None else "n/a",
    )
    rprint(core_tbl)

    emb_tbl = Table(show_header=True, header_style="bold blue", box=None)
    emb_tbl.add_column("MuQ Embedding", style="bold")
    emb_tbl.add_column("Shape")
    emb_tbl.add_column("L2 norm")
    for label, key in [
        ("full mix", "emb_full"),
        ("vocals", "emb_vocals"),
        ("drums", "emb_drums"),
        ("bass", "emb_bass"),
        ("other", "emb_other"),
        ("instrumental", "emb_instrumental"),
    ]:
        emb = f.get(key)
        if emb is not None:
            emb_tbl.add_row(label, str(emb.shape), f"{float(np.linalg.norm(emb)):.4f}")
        else:
            emb_tbl.add_row(label, "n/a", "n/a")
    rprint(emb_tbl)

    mood_tbl = Table(show_header=True, header_style="bold green", box=None)
    mood_tbl.add_column("Mood", style="bold")
    mood_tbl.add_column("Probability")
    for key in [
        "mood_happy",
        "mood_sad",
        "mood_relaxed",
        "mood_aggressive",
        "mood_acoustic",
        "mood_party",
    ]:
        value = f.get(key)
        mood_tbl.add_row(
            key.replace("mood_", "").title(),
            f"{value:.3f}" if value is not None else "n/a",
        )
    rprint(mood_tbl)

    if f.get("arousal") is not None:
        rprint(f"  Arousal: [yellow]{f['arousal']:.3f}[/yellow]   "
               f"Valence: [yellow]{f['valence']:.3f}[/yellow]")
    else:
        rprint("  Arousal/Valence: [dim]n/a (TF unavailable)[/dim]")

    if f.get("discogs_top5"):
        rprint("\n  [bold]Top-5 Discogs styles:[/bold]")
        for i, style in enumerate(f["discogs_top5"], 1):
            rprint(f"    {i}. {style}")
    else:
        rprint("  Discogs styles: [dim]n/a (TF unavailable)[/dim]")


def print_similarity_table_4stem(f_a: dict[str, Any], f_b: dict[str, Any]) -> None:
    try:
        from rich import print as rprint
        from rich.table import Table
    except ImportError:
        print(f"4-stem similarity: {similarity_4stem(f_a, f_b):.6f}")
        return

    label_a = f"{f_a['artist']} - {f_a['title']}"
    label_b = f"{f_b['artist']} - {f_b['title']}"
    rprint(f"\n[bold]4-stem cosine similarity:[/bold] {label_a}  <->  {label_b}")

    tbl = Table(show_header=True, header_style="bold cyan", box=None)
    tbl.add_column("Embedding", style="bold")
    tbl.add_column("Similarity")
    for label, key in [
        ("full mix", "emb_full"),
        ("vocals", "emb_vocals"),
        ("drums", "emb_drums"),
        ("bass", "emb_bass"),
        ("other", "emb_other"),
        ("instrumental", "emb_instrumental"),
    ]:
        tbl.add_row(label, f"{cosine_similarity(f_a[key], f_b[key]):.6f}")

    tbl.add_row("-" * 16, "-" * 10)
    tbl.add_row("[bold]COMBINED[/bold]", f"[bold]{similarity_4stem(f_a, f_b):.6f}[/bold]")
    rprint(tbl)


def _print_plain_summary(f: dict[str, Any]) -> None:
    print(f"{f['artist']} - {f['title']} ({f['duration_s']:.1f}s)")
    print(f"stem_mode: {f.get('stem_mode')}")
    print(f"bpm: {f.get('bpm')}  key: {f.get('camelot')}  danceability: {f.get('danceability')}")
    print(f"vocal_dominance: {f.get('vocal_dominance')}")
    for label, key in [
        ("full mix", "emb_full"),
        ("vocals", "emb_vocals"),
        ("drums", "emb_drums"),
        ("bass", "emb_bass"),
        ("other", "emb_other"),
        ("instrumental", "emb_instrumental"),
    ]:
        emb = f.get(key)
        print(f"{label}: shape={getattr(emb, 'shape', None)} norm={float(np.linalg.norm(emb)):.4f}")
    print(f"discogs_top5: {f.get('discogs_top5')}")


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run experimental 4-stem ingestion.")
    parser.add_argument("tracks", nargs="+", help="Artist/title pair, or two pairs for comparison")
    args = parser.parse_args()

    if len(args.tracks) not in (2, 4):
        raise SystemExit(
            'Usage: python track_ingestion_4stem.py "Artist" "Title" '
            'or python track_ingestion_4stem.py "Artist A" "Title A" "Artist B" "Title B"'
        )

    try:
        f_a = ingest_one_track_4stem(args.tracks[0], args.tracks[1])
        print_track_summary_4stem(f_a)

        if len(args.tracks) == 4:
            f_b = ingest_one_track_4stem(args.tracks[2], args.tracks[3])
            print_track_summary_4stem(f_b)
            print_similarity_table_4stem(f_a, f_b)
    except RuntimeError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    _main()
