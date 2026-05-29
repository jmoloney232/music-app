"""
v1.5 track feature extraction pipeline.

Public API:
    ingest_one_track(artist, title) -> dict
    print_track_summary(features)
    print_similarity_table(features_a, features_b)

Worker mode (invoked by this file's own subprocess):
    python track_ingestion.py --essentia-tf-worker <audio_path> <out_json>

Dependencies:
    requests, librosa, numpy, torch, muq, essentia (core),
    essentia-tensorflow (optional — graceful fallback on M-series),
    demucs (CLI), rich
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

AUDIO_CACHE = ROOT / "audio_cache"
STEMS_CACHE = ROOT / "stems_cache"
EMBEDDING_CACHE = ROOT / "embedding_cache"
FEATURE_CACHE = ROOT / "feature_cache"
MODELS_DIR = ROOT / "essentia_models"


def ensure_dirs() -> None:
    for d in (AUDIO_CACHE, STEMS_CACHE, EMBEDDING_CACHE, FEATURE_CACHE, MODELS_DIR):
        d.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utilities (adapted from model_comparison.py patterns)
# ---------------------------------------------------------------------------

def slugify(value: str, max_len: int = 90) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:max_len] or "unknown"


def stable_track_key(artist: str, title: str) -> str:
    raw = f"{artist}::{title}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:10]
    return f"{slugify(artist)}_{slugify(title)}_{digest}"


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return float("nan")
    return float(np.dot(a, b) / denom)


def torch_device() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def normalize_key_name(key: str) -> str:
    return {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}.get(key, key)


def key_to_camelot(key: str | None, scale: str | None) -> str | None:
    if not key or not scale:
        return None
    key = normalize_key_name(key)
    scale = scale.lower()
    minor = {"G#": 1, "D#": 2, "A#": 3, "F": 4, "C": 5, "G": 6,
             "D": 7, "A": 8, "E": 9, "B": 10, "F#": 11, "C#": 12}
    major = {"B": 1, "F#": 2, "C#": 3, "G#": 4, "D#": 5, "A#": 6,
             "F": 7, "C": 8, "G": 9, "D": 10, "A": 11, "E": 12}
    if scale.startswith("minor") or scale == "m":
        number, mode = minor.get(key), "A"
    else:
        number, mode = major.get(key), "B"
    return f"{number}{mode}" if number else None


# ---------------------------------------------------------------------------
# iTunes fetch & audio cache
# ---------------------------------------------------------------------------

MATCH_CONFIDENCE_THRESHOLD = 0.72

_JUNK_RE = re.compile(
    r'\s*\[[^\]]{0,80}\]'
    r'|\s*\(Free\s+(?:DL|Download)[^\)]*\)',
    re.IGNORECASE,
)
_TRAILING_CAPS_RE = re.compile(r'\s+[A-Z]{3,}(?:\s+[A-Z]{3,})*$')
_MIX_VERSION_RE = re.compile(
    r'[\s(]*\b(?:extended\s+(?:mix|version)|original\s+mix|'
    r'radio\s+(?:edit|mix)|club\s+(?:mix|edit)|dub\s+mix|extended)\b[)\s]*$',
    re.IGNORECASE,
)


def _fix_mojibake(text: str) -> str:
    try:
        import ftfy
        return ftfy.fix_text(text)
    except ImportError:
        pass
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _strip_junk(text: str) -> str:
    return _JUNK_RE.sub("", text).strip()


_MIN_ARTIST_SCORE = 0.45  # prevents title-only coincidences from matching wrong artists


def _score_match(result: dict, cand_artist: str, cand_title: str) -> float:
    def norm(s: str) -> str:
        return re.sub(r"[^\w\s]", "", s.lower()).strip()
    a = difflib.SequenceMatcher(None, norm(cand_artist), norm(result.get("artistName") or "")).ratio()
    if a < _MIN_ARTIST_SCORE:
        return 0.0
    t = difflib.SequenceMatcher(None, norm(cand_title), norm(result.get("trackName") or "")).ratio()
    return 0.35 * a + 0.65 * t


def _itunes_candidates(artist: str, title: str) -> list[tuple[str, str]]:
    """Generate candidate (artist, title) interpretations for fallback matching."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(a: str, t: str) -> None:
        a, t = a.strip(), t.strip()
        key = (a.lower(), t.lower())
        if a and t and key not in seen:
            seen.add(key)
            out.append((a, t))

    fa, ft = _fix_mojibake(artist), _fix_mojibake(title)

    # 1. Mojibake-fixed + square-bracket junk stripped
    add(fa, _strip_junk(ft))

    # 2. Split combined label on " - " to detect prefixed-label layout (SoundCloud/UKF style)
    #    e.g. "Wakaan - PEEKABOO - Maniac [UKF Premiere]" → parts[1]=PEEKABOO, parts[2]=Maniac
    parts = [p.strip() for p in f"{fa} - {ft}".split(" - ")]
    if len(parts) >= 3:
        add(parts[1], _strip_junk(parts[2]))

    # 3. Layout B: trailing ALL-CAPS label word(s) on the title — strip only when lowercase text remains
    #    e.g. "Stampedo MONSTER FORCE" → "Stampedo"
    clean_ft = _strip_junk(ft)
    stripped = _TRAILING_CAPS_RE.sub("", clean_ft).strip()
    if stripped and stripped != clean_ft and re.search(r"[a-z]", stripped):
        add(fa, stripped)

    # 4. Title field contains " - " — treat as embedded "artist - title"
    if " - " in ft:
        tp = ft.split(" - ", 1)
        add(tp[0].strip(), _strip_junk(tp[1].strip()))

    # 5. Strip trailing mix-version suffix so Beatport "Free Your Mind Extended Mix"
    #    matches iTunes "Free Your Mind" (radio edit / album version)
    mix_cleaned = _MIX_VERSION_RE.sub("", clean_ft).strip()
    if mix_cleaned and mix_cleaned != clean_ft:
        add(fa, mix_cleaned)

    return out


def _itunes_query(params: dict) -> list[dict]:
    for attempt in range(4):
        resp = requests.get("https://itunes.apple.com/search", params=params, timeout=20)
        if resp.status_code not in (429, 403):
            break
        delay = 5 * (attempt + 1)
        log.warning("iTunes rate/block (%s); retrying in %ss", resp.status_code, delay)
        time.sleep(delay)
    if resp.status_code in (429, 403):
        log.warning("iTunes search still %s after retries — skipping query", resp.status_code)
        return []
    resp.raise_for_status()
    return resp.json().get("results", [])


def search_itunes_preview(artist: str, title: str) -> str:
    label = f"{artist} - {title}"

    # ---- STRICT FIRST: identical to prior behavior — first previewUrl wins ----
    for params in [
        {"term": label, "media": "music", "entity": "song", "limit": 5},
        {"term": label, "media": "all", "limit": 10},
    ]:
        for result in _itunes_query(params):
            url = result.get("previewUrl")
            if url:
                return url

    # ---- FALLBACK (strict miss only): candidate parsing + fuzzy scoring ----
    candidates = _itunes_candidates(artist, title)
    log.info("iTunes strict miss for %r — trying %d fallback candidates", label, len(candidates))

    best_url: str | None = None
    best_score = 0.0
    best_info = ""

    for cand_artist, cand_title in candidates:
        cand_label = f"{cand_artist} - {cand_title}"
        log.info("  candidate: %r", cand_label)
        for q_variant, params in [
            ("combined", {"term": cand_label, "media": "music", "entity": "song", "limit": 25}),
            ("title-only", {"term": cand_title, "media": "music", "entity": "song", "limit": 25}),
        ]:
            for result in _itunes_query(params):
                url = result.get("previewUrl")
                if not url:
                    continue
                score = _score_match(result, cand_artist, cand_title)
                if score > best_score:
                    best_score = score
                    best_url = url
                    best_info = (
                        f"candidate=({cand_artist!r}, {cand_title!r}), "
                        f"query={q_variant!r}, score={score:.3f}, "
                        f"match={result.get('artistName')!r} / {result.get('trackName')!r}"
                    )
            if best_score >= MATCH_CONFIDENCE_THRESHOLD:
                break
        if best_score >= MATCH_CONFIDENCE_THRESHOLD:
            break

    if best_url and best_score >= MATCH_CONFIDENCE_THRESHOLD:
        log.info("iTunes fallback matched: %s", best_info)
        return best_url

    debug = f"; best_candidate={best_info}" if best_info else ""
    raise ValueError(f"No iTunes preview URL for {label}{debug}")


def fetch_audio(artist: str, title: str, track_key: str) -> Path:
    path = AUDIO_CACHE / f"{track_key}.m4a"
    if path.exists() and path.stat().st_size > 0:
        log.info("audio cache hit: %s - %s", artist, title)
        return path
    log.info("fetching audio: %s - %s", artist, title)
    url = search_itunes_preview(artist, title)
    resp = requests.get(url, timeout=45)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    return path


def load_audio_librosa(path: Path, sr: int) -> np.ndarray:
    wav, _ = librosa.load(str(path), sr=sr, mono=True)
    return wav.astype(np.float32)


# ---------------------------------------------------------------------------
# Demucs source separation
# ---------------------------------------------------------------------------

DEMUCS_MODEL = "htdemucs"
STEM_NAMES = ("vocals", "drums", "bass", "other")


def get_stems(audio_path: Path, track_key: str) -> dict[str, Path]:
    stem_paths = {
        stem: STEMS_CACHE / f"{track_key}_{DEMUCS_MODEL}_4stem_{stem}.wav"
        for stem in STEM_NAMES
    }

    if all(path.exists() and path.stat().st_size > 0 for path in stem_paths.values()):
        log.info("4-stem cache hit: %s", track_key)
        return stem_paths

    log.info("running Demucs %s 4-stem on: %s", DEMUCS_MODEL, audio_path.name)
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                sys.executable,
                "-m", "demucs",
                "-n", DEMUCS_MODEL,
                "--out", tmpdir,
                str(audio_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Demucs failed for {audio_path.name}:\n{result.stderr}"
            )

        stem_dir = Path(tmpdir) / DEMUCS_MODEL / audio_path.stem
        for stem, dest in stem_paths.items():
            src = stem_dir / f"{stem}.wav"
            if not src.exists():
                raise RuntimeError(f"Demucs did not produce expected stem: {src}")
            dest.unlink(missing_ok=True)
            shutil.move(str(src), str(dest))

    log.info("4-stems cached: %s", track_key)
    return stem_paths


def mix_stems(stems: list[np.ndarray]) -> np.ndarray:
    if not stems:
        raise ValueError("No stems supplied for mixing")
    min_len = min(len(stem) for stem in stems)
    stacked = np.vstack([stem[:min_len] for stem in stems])
    return stacked.sum(axis=0).astype(np.float32)


# ---------------------------------------------------------------------------
# MuQ-MuLan embeddings
# ---------------------------------------------------------------------------

_muq_model_cache: dict[str, Any] = {}


def get_muq_model(device: str) -> Any:
    if device not in _muq_model_cache:
        import torch
        from muq import MuQMuLan
        log.info("loading MuQ-MuLan-large on %s", device)
        model = MuQMuLan.from_pretrained("OpenMuQ/MuQ-MuLan-large")
        # MPS can be unreliable for some ops; fall back to CPU
        try:
            model = model.to(device).eval()
            # quick smoke-test
            import torch as _t
            _t.no_grad().__enter__()
            dummy = _t.zeros(1, 24000, device=device)
            model(wavs=dummy)
            _t.no_grad().__exit__(None, None, None)
        except Exception:
            log.warning("MuQ failed on %s, falling back to cpu", device)
            device = "cpu"
            model = model.to(device).eval()
        _muq_model_cache[device] = (model, device)
    return _muq_model_cache[device]


def embed_muq(wav_24k: np.ndarray, model: Any, device: str) -> np.ndarray:
    import torch
    tensor = torch.tensor(wav_24k, dtype=torch.float32).unsqueeze(0).to(device)
    with torch.no_grad():
        out = model(wavs=tensor)
    arr = out.detach().cpu().numpy()
    # shape is (1, 512) or (1, n_frames, 512)
    if arr.ndim == 3:
        arr = arr.mean(axis=1)
    return arr[0].astype(np.float32)


def _muq_cache_path(variant: str, track_key: str) -> Path:
    return EMBEDDING_CACHE / f"muq_{variant}_{track_key}.npy"


def get_muq_embedding(wav_44k: np.ndarray, variant: str, track_key: str) -> np.ndarray:
    cache = _muq_cache_path(variant, track_key)
    if cache.exists():
        log.info("muq %s embedding cache hit: %s", variant, track_key)
        return np.load(cache)

    device = torch_device()
    model, device = get_muq_model(device)
    wav_24k = librosa.resample(wav_44k, orig_sr=44_100, target_sr=24_000)
    log.info("computing muq %s embedding: %s", variant, track_key)
    emb = embed_muq(wav_24k, model, device)
    np.save(cache, emb)
    return emb


# ---------------------------------------------------------------------------
# Vocal dominance
# ---------------------------------------------------------------------------

def compute_vocal_dominance(vocals_wav: np.ndarray, full_mix_wav: np.ndarray, sr: int = 44_100) -> float:
    rms_vocals = float(np.sqrt(np.mean(vocals_wav ** 2)))
    rms_mix = float(np.sqrt(np.mean(full_mix_wav ** 2)))
    rms_ratio = rms_vocals / (rms_mix + 1e-9)

    # downsample for pyin — voiced detection doesn't need 44.1kHz resolution
    vocals_16k = librosa.resample(vocals_wav, orig_sr=sr, target_sr=16_000)
    _, voiced_flag, _ = librosa.pyin(
        vocals_16k, fmin=80.0, fmax=2000.0, sr=16_000, hop_length=512
    )
    voiced_ratio = float(np.mean(voiced_flag))

    return float(np.clip(rms_ratio * voiced_ratio, 0.0, 1.0))


def vocal_class(vd: float) -> str:
    if vd < 0.10:
        return "instrumental"
    if vd > 0.20:
        return "vocal"
    return "ambiguous"


def similarity(f_a: dict[str, Any], f_b: dict[str, Any]) -> float:
    full_sim    = cosine_similarity(f_a["emb_full"],    f_b["emb_full"])
    vocal_sim   = cosine_similarity(f_a["emb_vocals"],  f_b["emb_vocals"])
    backing_sim = cosine_similarity(f_a["emb_backing"], f_b["emb_backing"])
    has_4stem = all(
        f_a.get(key) is not None and f_b.get(key) is not None
        for key in ("emb_drums", "emb_bass", "emb_other")
    )

    ca = vocal_class(f_a["vocal_dominance"])
    cb = vocal_class(f_b["vocal_dominance"])

    if has_4stem:
        drums_sim = cosine_similarity(f_a["emb_drums"], f_b["emb_drums"])
        bass_sim = cosine_similarity(f_a["emb_bass"], f_b["emb_bass"])
        other_sim = cosine_similarity(f_a["emb_other"], f_b["emb_other"])

        if ca == "vocal" and cb == "vocal":
            w_full, w_vocal, w_drums, w_bass, w_other = 0.40, 0.25, 0.15, 0.10, 0.10
        elif ca == "instrumental" and cb == "instrumental":
            w_full, w_vocal, w_drums, w_bass, w_other = 0.50, 0.00, 0.20, 0.15, 0.15
        else:
            w_full, w_vocal, w_drums, w_bass, w_other = 0.55, 0.00, 0.15, 0.10, 0.20

        return (
            w_full  * full_sim +
            w_vocal * vocal_sim +
            w_drums * drums_sim +
            w_bass  * bass_sim +
            w_other * other_sim
        )

    if ca == "vocal" and cb == "vocal":
        w_full, w_vocal, w_backing = 0.50, 0.30, 0.20
    elif ca == "instrumental" and cb == "instrumental":
        w_full, w_vocal, w_backing = 0.70, 0.00, 0.30
    else:
        w_full, w_vocal, w_backing = 0.75, 0.00, 0.25

    return (
        w_full    * full_sim +
        w_vocal   * vocal_sim +
        w_backing * backing_sim
    )


# ---------------------------------------------------------------------------
# Essentia core features (no TensorFlow — always available)
# ---------------------------------------------------------------------------

def compute_essentia_core(wav_44k: np.ndarray, track_key: str) -> dict[str, Any]:
    cache = FEATURE_CACHE / f"{track_key}.json"
    if cache.exists():
        log.info("essentia core cache hit: %s", track_key)
        return json.loads(cache.read_text())

    try:
        import essentia.standard as es
    except ImportError as exc:
        raise RuntimeError("essentia is not installed") from exc

    features: dict[str, Any] = {
        "bpm": None, "key": None, "scale": None,
        "key_strength": None, "camelot": None, "danceability": None,
        "mfcc_mean": None,
    }

    try:
        rhythm = es.RhythmExtractor2013(method="multifeature")
        bpm, *_ = rhythm(wav_44k)
        features["bpm"] = float(bpm)
    except Exception as exc:
        log.warning("Essentia BPM failed: %s", exc)

    try:
        key, scale, strength = es.KeyExtractor()(wav_44k)
        features["key"] = key
        features["scale"] = scale
        features["key_strength"] = float(strength)
        features["camelot"] = key_to_camelot(key, scale)
    except Exception as exc:
        log.warning("Essentia key failed: %s", exc)

    try:
        dance_result = es.Danceability()(wav_44k)
        raw_dance = float(
            dance_result[0] if isinstance(dance_result, tuple) else dance_result
        )
        # Essentia danceability is on a ~0-3 scale; normalize to 0-1 for
        # consistency with all other stored features (vocal_dominance, moods, etc.)
        features["danceability"] = min(raw_dance / 3.0, 1.0)
    except Exception as exc:
        log.warning("Essentia danceability failed: %s", exc)

    try:
        mfcc_frames = librosa.feature.mfcc(y=wav_44k, sr=44_100, n_mfcc=13)
        features["mfcc_mean"] = mfcc_frames.mean(axis=1).tolist()
    except Exception as exc:
        log.warning("MFCC failed: %s", exc)

    cache.write_text(json.dumps(features, indent=2))
    return features


# ---------------------------------------------------------------------------
# Essentia TF features — subprocess worker (graceful fallback on M-series)
# ---------------------------------------------------------------------------

ESSENTIA_TF_MOODS = [
    "mood_happy", "mood_sad", "mood_relaxed",
    "mood_aggressive", "mood_acoustic", "mood_party",
]

ESSENTIA_TF_MODEL_FILES: dict[str, str] = {
    "mood_happy":       "mood_happy-musicnn-msd-2.pb",
    "mood_sad":         "mood_sad-musicnn-msd-2.pb",
    "mood_relaxed":     "mood_relaxed-musicnn-msd-2.pb",
    "mood_aggressive":  "mood_aggressive-musicnn-msd-2.pb",
    "mood_acoustic":    "mood_acoustic-musicnn-msd-2.pb",
    "mood_party":       "mood_party-musicnn-msd-2.pb",
    "arousal_valence":  "deam-msd-musicnn-2.pb",
    "effnet_emb":       "discogs-effnet-bs64-1.pb",
    "discogs400":       "genre_discogs400-discogs-effnet-1.pb",
}

DISCOGS_LABELS_FILE = MODELS_DIR / "discogs400_labels.json"

ESSENTIA_MODEL_URLS: dict[str, str] = {
    "msd-musicnn-1.pb":
        "https://essentia.upf.edu/models/feature-extractors/musicnn/msd-musicnn-1.pb",
    "mood_happy-musicnn-msd-2.pb":
        "https://essentia.upf.edu/models/classifiers/mood_happy/mood_happy-musicnn-msd-2.pb",
    "mood_sad-musicnn-msd-2.pb":
        "https://essentia.upf.edu/models/classifiers/mood_sad/mood_sad-musicnn-msd-2.pb",
    "mood_relaxed-musicnn-msd-2.pb":
        "https://essentia.upf.edu/models/classifiers/mood_relaxed/mood_relaxed-musicnn-msd-2.pb",
    "mood_aggressive-musicnn-msd-2.pb":
        "https://essentia.upf.edu/models/classifiers/mood_aggressive/mood_aggressive-musicnn-msd-2.pb",
    "mood_acoustic-musicnn-msd-2.pb":
        "https://essentia.upf.edu/models/classifiers/mood_acoustic/mood_acoustic-musicnn-msd-2.pb",
    "mood_party-musicnn-msd-2.pb":
        "https://essentia.upf.edu/models/classifiers/mood_party/mood_party-musicnn-msd-2.pb",
    "deam-msd-musicnn-2.pb":
        "https://essentia.upf.edu/models/classification-heads/deam/deam-msd-musicnn-2.pb",
    "discogs-effnet-bs64-1.pb":
        "https://essentia.upf.edu/models/music-style-classification/discogs-effnet/discogs-effnet-bs64-1.pb",
    "genre_discogs400-discogs-effnet-1.pb":
        "https://essentia.upf.edu/models/classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.pb",
}


def ensure_essentia_models() -> None:
    for filename, url in ESSENTIA_MODEL_URLS.items():
        dest = MODELS_DIR / filename
        if dest.exists() and dest.stat().st_size > 0:
            continue
        log.info("downloading Essentia model: %s", filename)
        resp = requests.get(url, timeout=300, stream=True)
        resp.raise_for_status()
        tmp = dest.with_suffix(".tmp")
        try:
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
            tmp.rename(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        log.info("saved %s (%.1f MB)", filename, dest.stat().st_size / 1e6)


def _essentia_tf_worker(audio_path: Path, out_json: Path) -> None:
    """Worker: runs inside a subprocess to isolate TF from the main process."""
    import essentia.standard as es

    wav_16k = librosa.load(str(audio_path), sr=16_000, mono=True)[0].astype(np.float32)
    result: dict[str, Any] = {}

    # MusiCNN embeddings (shared input for mood + arousal/valence)
    musicnn_emb = None
    effnet_emb = None

    # -- MusiCNN embedding (required by mood + AV models) --------------------
    musicnn_pb = MODELS_DIR / "msd-musicnn-1.pb"
    if musicnn_pb.exists():
        try:
            extractor = es.TensorflowPredictMusiCNN(
                graphFilename=str(musicnn_pb),
                output="model/dense/BiasAdd",
            )
            musicnn_emb = extractor(wav_16k)
        except Exception as exc:
            log.warning("MusiCNN embedding failed: %s", exc)
    else:
        log.warning("MusiCNN model not found at %s — skipping mood/AV", musicnn_pb)

    # -- Mood classifiers (full self-contained models — take raw audio) --------
    # These are NOT classification heads; use TensorflowPredictMusiCNN on audio
    for mood in ESSENTIA_TF_MOODS:
        pb = MODELS_DIR / ESSENTIA_TF_MODEL_FILES[mood]
        if not pb.exists():
            result[mood] = None
            continue
        try:
            clf = es.TensorflowPredictMusiCNN(
                graphFilename=str(pb),
                output="model/Sigmoid",
            )
            probs = clf(wav_16k)
            # binary classifiers return [p_not, p_yes] per frame — take mean of p_yes (index 1)
            result[mood] = float(np.mean(probs[:, 1]) if probs.ndim == 2 else probs[-1])
        except Exception as exc:
            log.warning("Mood %s failed: %s", mood, exc)
            result[mood] = None

    # -- Arousal / Valence ----------------------------------------------------
    av_pb = MODELS_DIR / ESSENTIA_TF_MODEL_FILES["arousal_valence"]
    if av_pb.exists() and musicnn_emb is not None:
        try:
            av_model = es.TensorflowPredict2D(
                graphFilename=str(av_pb),
                output="model/Identity",
            )
            av_out = av_model(musicnn_emb)
            av_mean = av_out.mean(axis=0) if av_out.ndim == 2 else av_out
            result["arousal"] = float(av_mean[0])
            result["valence"] = float(av_mean[1])
        except Exception as exc:
            log.warning("Arousal/valence failed: %s", exc)
            result["arousal"] = None
            result["valence"] = None
    else:
        result["arousal"] = None
        result["valence"] = None

    # -- Effnet-Discogs embeddings --------------------------------------------
    effnet_pb = MODELS_DIR / ESSENTIA_TF_MODEL_FILES["effnet_emb"]
    if effnet_pb.exists():
        try:
            effnet_extractor = es.TensorflowPredictEffnetDiscogs(
                graphFilename=str(effnet_pb),
                output="PartitionedCall:1",
            )
            effnet_emb = effnet_extractor(wav_16k)
        except Exception as exc:
            log.warning("Effnet-Discogs embedding failed: %s", exc)

    # -- 400-class genre classifier -------------------------------------------
    discogs_pb = MODELS_DIR / ESSENTIA_TF_MODEL_FILES["discogs400"]
    if discogs_pb.exists() and effnet_emb is not None:
        try:
            genre_clf = es.TensorflowPredict2D(
                graphFilename=str(discogs_pb),
                input="serving_default_model_Placeholder",
                output="PartitionedCall:0",
            )
            genre_probs = genre_clf(effnet_emb)
            mean_probs = genre_probs.mean(axis=0) if genre_probs.ndim == 2 else genre_probs
            result["discogs_styles_400"] = mean_probs.tolist()

            # top-5 labels
            top5_idx = np.argsort(mean_probs)[-5:][::-1].tolist()
            labels: list[str] | None = None
            if DISCOGS_LABELS_FILE.exists():
                labels = json.loads(DISCOGS_LABELS_FILE.read_text())
            if labels and len(labels) >= 400:
                result["discogs_top5"] = [labels[i] for i in top5_idx]
            else:
                result["discogs_top5"] = [f"class_{i}" for i in top5_idx]
        except Exception as exc:
            log.warning("Discogs-400 genre failed: %s", exc)
            result["discogs_styles_400"] = None
            result["discogs_top5"] = None
    else:
        result["discogs_styles_400"] = None
        result["discogs_top5"] = None

    out_json.write_text(json.dumps(result))


def compute_essentia_tf(audio_path: Path, track_key: str) -> dict[str, Any] | None:
    cache = FEATURE_CACHE / f"{track_key}_tf.json"
    if cache.exists():
        log.info("essentia TF cache hit: %s", track_key)
        return json.loads(cache.read_text())

    ensure_essentia_models()
    log.info("running Essentia TF worker for: %s", track_key)
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--essentia-tf-worker",
            str(audio_path),
            str(cache),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-400:]
        log.warning(
            "Essentia TF worker failed (M-series TF fallback active): %s", detail
        )
        return None

    return json.loads(cache.read_text())


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def ingest_one_track(artist: str, title: str) -> dict[str, Any]:
    ensure_dirs()
    track_key = stable_track_key(artist, title)

    # 1. Fetch audio
    _t0 = time.perf_counter()
    audio_path = fetch_audio(artist, title, track_key)
    print(f"[timing] audio_fetch: {time.perf_counter() - _t0:.1f}s")

    # 2. Load full mix at 44.1 kHz
    log.info("loading full mix: %s - %s", artist, title)
    full_mix_wav = load_audio_librosa(audio_path, 44_100)
    duration = len(full_mix_wav) / 44_100

    # 3. Demucs separation
    _t0 = time.perf_counter()
    stem_paths = get_stems(audio_path, track_key)
    print(f"[timing] demucs: {time.perf_counter() - _t0:.1f}s")

    # 4. Load stems at 44.1 kHz
    log.info("loading stems")
    vocals_wav = load_audio_librosa(stem_paths["vocals"], 44_100)
    drums_wav = load_audio_librosa(stem_paths["drums"], 44_100)
    bass_wav = load_audio_librosa(stem_paths["bass"], 44_100)
    other_wav = load_audio_librosa(stem_paths["other"], 44_100)
    backing_wav = mix_stems([drums_wav, bass_wav, other_wav])

    # 5. Vocal dominance
    log.info("computing vocal dominance")
    vocal_dominance = compute_vocal_dominance(vocals_wav, full_mix_wav, sr=44_100)

    # 6. MuQ-MuLan embeddings
    log.info("computing MuQ embeddings")
    _t0 = time.perf_counter()
    emb_full = get_muq_embedding(full_mix_wav, "full", track_key)
    emb_vocals = get_muq_embedding(vocals_wav, f"{DEMUCS_MODEL}_4stem_vocals", track_key)
    emb_drums = get_muq_embedding(drums_wav, f"{DEMUCS_MODEL}_4stem_drums", track_key)
    emb_bass = get_muq_embedding(bass_wav, f"{DEMUCS_MODEL}_4stem_bass", track_key)
    emb_other = get_muq_embedding(other_wav, f"{DEMUCS_MODEL}_4stem_other", track_key)
    emb_backing = get_muq_embedding(backing_wav, f"{DEMUCS_MODEL}_4stem_backing", track_key)
    print(f"[timing] muq_embeddings: {time.perf_counter() - _t0:.1f}s")

    # 7. Essentia core features
    log.info("computing Essentia core features")
    _t0 = time.perf_counter()
    core = compute_essentia_core(full_mix_wav, track_key)

    # 8. Essentia TF features are intentionally disabled for production ingestion.
    # Keep nullable output fields for DB/schema compatibility.
    log.info("skipping Essentia TF features")
    tf_feats = None
    print(f"[timing] essentia: {time.perf_counter() - _t0:.1f}s")

    return {
        "artist": artist,
        "title": title,
        "track_key": track_key,
        "duration_s": duration,
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
        # MuQ embeddings (numpy arrays)
        "emb_full": emb_full,
        "emb_vocals": emb_vocals,
        "emb_backing": emb_backing,
        "emb_drums": emb_drums,
        "emb_bass": emb_bass,
        "emb_other": emb_other,
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


# ---------------------------------------------------------------------------
# Rich terminal output
# ---------------------------------------------------------------------------

def _bar(value: float | None, width: int = 20) -> str:
    from rich.text import Text
    if value is None:
        return "[dim]n/a[/dim]"
    filled = int(round(value * width))
    bar = "█" * filled + "░" * (width - filled)
    pct = f"{value:.2f}"
    return f"[cyan]{bar}[/cyan] {pct}"


def print_track_summary(f: dict[str, Any]) -> None:
    from rich import print as rprint
    from rich.panel import Panel
    from rich.table import Table

    label = f"{f['artist']} — {f['title']}"
    rprint(Panel(f"[bold white]{label}[/bold white]  "
                 f"[dim]{f['duration_s']:.1f}s[/dim]",
                 expand=False))

    # Core features
    core_tbl = Table(show_header=True, header_style="bold magenta", box=None)
    core_tbl.add_column("Feature", style="bold")
    core_tbl.add_column("Value")

    bpm_str = f"{f['bpm']:.1f}" if f.get("bpm") is not None else "n/a"
    key_str = f"{f.get('key', 'n/a')} {f.get('scale', '')}"
    cam_str = f.get("camelot") or "n/a"
    dance_str = f"{f['danceability']:.3f}" if f.get("danceability") is not None else "n/a"

    core_tbl.add_row("BPM", bpm_str)
    core_tbl.add_row("Key", key_str.strip())
    core_tbl.add_row("Camelot", cam_str)
    core_tbl.add_row("Danceability", dance_str)
    core_tbl.add_row("Vocal Dominance", _bar(f.get("vocal_dominance")))

    if f.get("mfcc_mean"):
        mfcc_str = "  ".join(f"{v:+.1f}" for v in f["mfcc_mean"])
        core_tbl.add_row("MFCC mean (13)", mfcc_str)

    rprint(core_tbl)

    # MuQ embedding info
    emb_tbl = Table(show_header=True, header_style="bold blue", box=None)
    emb_tbl.add_column("MuQ Embedding", style="bold")
    emb_tbl.add_column("Shape")
    emb_tbl.add_column("L2 norm")
    for variant, key in [
        ("full mix", "emb_full"),
        ("vocals", "emb_vocals"),
        ("drums", "emb_drums"),
        ("bass", "emb_bass"),
        ("other", "emb_other"),
        ("backing mix", "emb_backing"),
    ]:
        emb = f.get(key)
        if emb is not None:
            emb_tbl.add_row(variant, str(emb.shape), f"{float(np.linalg.norm(emb)):.4f}")
        else:
            emb_tbl.add_row(variant, "n/a", "n/a")
    rprint(emb_tbl)

    # Mood
    mood_keys = ["mood_happy", "mood_sad", "mood_relaxed",
                 "mood_aggressive", "mood_acoustic", "mood_party"]
    mood_tbl = Table(show_header=True, header_style="bold green", box=None)
    mood_tbl.add_column("Mood", style="bold")
    mood_tbl.add_column("Probability")
    for mk in mood_keys:
        mood_tbl.add_row(mk.replace("mood_", "").title(), _bar(f.get(mk)))
    rprint(mood_tbl)

    # Arousal / Valence
    if f.get("arousal") is not None:
        rprint(f"  Arousal: [yellow]{f['arousal']:.3f}[/yellow]   "
               f"Valence: [yellow]{f['valence']:.3f}[/yellow]")
    else:
        rprint("  Arousal/Valence: [dim]n/a (TF unavailable)[/dim]")

    # Discogs top-5
    if f.get("discogs_top5"):
        rprint("\n  [bold]Top-5 Discogs styles:[/bold]")
        for i, style in enumerate(f["discogs_top5"], 1):
            rprint(f"    {i}. {style}")
    else:
        rprint("  Discogs styles: [dim]n/a (TF unavailable)[/dim]")


def print_similarity_table(f_a: dict[str, Any], f_b: dict[str, Any]) -> None:
    from rich import print as rprint
    from rich.table import Table

    label_a = f"{f_a['artist']} — {f_a['title']}"
    label_b = f"{f_b['artist']} — {f_b['title']}"
    rprint(f"\n[bold]Cosine similarity:[/bold] {label_a}  ↔  {label_b}")

    tbl = Table(show_header=True, header_style="bold cyan", box=None)
    tbl.add_column("Embedding", style="bold")
    tbl.add_column("Similarity")

    for label, key_a, key_b in [
        ("full mix", "emb_full", "emb_full"),
        ("vocals", "emb_vocals", "emb_vocals"),
        ("drums", "emb_drums", "emb_drums"),
        ("bass", "emb_bass", "emb_bass"),
        ("other", "emb_other", "emb_other"),
        ("backing mix", "emb_backing", "emb_backing"),
    ]:
        a_emb = f_a.get(key_a)
        b_emb = f_b.get(key_b)
        if a_emb is not None and b_emb is not None:
            sim = cosine_similarity(a_emb, b_emb)
            tbl.add_row(label, f"{sim:.6f}")
        else:
            tbl.add_row(label, "n/a")

    tbl.add_row("─" * 16, "─" * 10)
    ca = vocal_class(f_a["vocal_dominance"])
    cb = vocal_class(f_b["vocal_dominance"])
    combined = similarity(f_a, f_b)
    label_a = f_a.get("artist", "A")
    label_b = f_b.get("artist", "B")
    tbl.add_row(
        "[bold]COMBINED[/bold]",
        f"[bold]{combined:.6f}[/bold]   [dim]({label_a}={ca}, {label_b}={cb})[/dim]",
    )
    rprint(tbl)


# ---------------------------------------------------------------------------
# Database persistence
# ---------------------------------------------------------------------------

_MOOD_KEYS = [
    "mood_happy", "mood_sad", "mood_relaxed",
    "mood_aggressive", "mood_acoustic", "mood_party",
]


def get_connection() -> Any:
    import psycopg
    from pgvector.psycopg import register_vector
    url = os.environ["DATABASE_URL"]
    conn = psycopg.connect(url)
    register_vector(conn)
    return conn


def save_track_features(features: dict[str, Any]) -> int:
    conn = get_connection()
    _t0 = time.perf_counter()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tracks (artist, title, status)
                VALUES (%s, %s, 'indexed')
                ON CONFLICT (artist, title) DO UPDATE
                    SET status = EXCLUDED.status
                RETURNING id
                """,
                (features["artist"], features["title"]),
            )
            track_id: int = cur.fetchone()[0]

            mood_vals = [features.get(k) for k in _MOOD_KEYS]
            mood = mood_vals if any(v is not None for v in mood_vals) else None

            av_vals = [features.get("arousal"), features.get("valence")]
            av = av_vals if any(v is not None for v in av_vals) else None

            ds = features.get("discogs_styles_400")
            ds_vec = np.array(ds, dtype=np.float32) if ds is not None else None

            cur.execute(
                """
                INSERT INTO embeddings (
                    track_id, muq_full, muq_vocals, muq_backing,
                    muq_drums, muq_bass, muq_other,
                    vocal_dominance, bpm, key, camelot, danceability,
                    mood, arousal_valence, mfcc_mean,
                    discogs_styles, top_styles, computed_at
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, NOW()
                )
                ON CONFLICT (track_id) DO UPDATE SET
                    muq_full         = EXCLUDED.muq_full,
                    muq_vocals       = EXCLUDED.muq_vocals,
                    muq_backing      = EXCLUDED.muq_backing,
                    muq_drums        = EXCLUDED.muq_drums,
                    muq_bass         = EXCLUDED.muq_bass,
                    muq_other        = EXCLUDED.muq_other,
                    vocal_dominance  = EXCLUDED.vocal_dominance,
                    bpm              = EXCLUDED.bpm,
                    key              = EXCLUDED.key,
                    camelot          = EXCLUDED.camelot,
                    danceability     = EXCLUDED.danceability,
                    mood             = EXCLUDED.mood,
                    arousal_valence  = EXCLUDED.arousal_valence,
                    mfcc_mean        = EXCLUDED.mfcc_mean,
                    discogs_styles   = EXCLUDED.discogs_styles,
                    top_styles       = EXCLUDED.top_styles,
                    computed_at      = EXCLUDED.computed_at
                """,
                (
                    track_id,
                    features.get("emb_full"),
                    features.get("emb_vocals"),
                    features.get("emb_backing"),
                    features.get("emb_drums"),
                    features.get("emb_bass"),
                    features.get("emb_other"),
                    features.get("vocal_dominance"),
                    features.get("bpm"),
                    features.get("key"),
                    features.get("camelot"),
                    features.get("danceability"),
                    mood,
                    av,
                    features.get("mfcc_mean"),
                    ds_vec,
                    json.dumps(features.get("discogs_top5")) if features.get("discogs_top5") else None,
                ),
            )
    conn.close()
    print(f"[timing] db_save: {time.perf_counter() - _t0:.1f}s")
    return track_id


def fetch_track_features(track_id: int) -> dict[str, Any]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.artist, t.title,
                   e.muq_full, e.muq_vocals, e.muq_backing,
                   e.muq_drums, e.muq_bass, e.muq_other,
                   e.vocal_dominance, e.bpm, e.key, e.camelot, e.danceability,
                   e.mfcc_mean, e.top_styles
            FROM tracks t
            JOIN embeddings e ON e.track_id = t.id
            WHERE t.id = %s
            """,
            (track_id,),
        )
        row = cur.fetchone()
    conn.close()

    (
        artist, title,
        muq_full, muq_vocals, muq_backing,
        muq_drums, muq_bass, muq_other,
        vocal_dominance, bpm, key, camelot, danceability,
        mfcc, top_styles,
    ) = row

    return {
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


# ---------------------------------------------------------------------------
# Entry point — worker mode or demo run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Subprocess worker mode
    if len(sys.argv) >= 4 and sys.argv[1] == "--essentia-tf-worker":
        _essentia_tf_worker(Path(sys.argv[2]), Path(sys.argv[3]))
        sys.exit(0)

    from rich import print as rprint

    tracks = [
        ("The Beatles",      "Come Together"),   # vocal_dominance expected ~0.8+
        ("Daft Punk",        "Around the World"), # expected ~0.3–0.5
        ("Boards of Canada", "Roygbiv"),          # expected ~0.05–0.15
    ]

    features_list = []
    for artist, title in tracks:
        rprint(f"\n[bold yellow]━━━ Ingesting: {artist} — {title} ━━━[/bold yellow]")
        f = ingest_one_track(artist, title)
        features_list.append(f)
        print_track_summary(f)
        rprint(f"\n  [bold]vocal_dominance = {f['vocal_dominance']:.4f}[/bold]")

    # Pairwise similarity tables (in-memory)
    rprint("\n[bold yellow]━━━ Pairwise MuQ Similarities ━━━[/bold yellow]")
    pairs = [
        (features_list[0], features_list[1]),
        (features_list[0], features_list[2]),
        (features_list[1], features_list[2]),
    ]
    for fa, fb in pairs:
        print_similarity_table(fa, fb)

    # Save to database
    rprint("\n[bold green]━━━ Saving to database ━━━[/bold green]")
    track_ids = []
    for f in features_list:
        tid = save_track_features(f)
        track_ids.append(tid)
        rprint(f"  Saved [bold]{f['artist']} — {f['title']}[/bold] → track_id={tid}")

    # Fetch back from database and re-run similarity to verify round-trip
    rprint("\n[bold green]━━━ DB round-trip similarity check ━━━[/bold green]")
    db_features = [fetch_track_features(tid) for tid in track_ids]
    for fa, fb in [
        (db_features[0], db_features[1]),
        (db_features[0], db_features[2]),
        (db_features[1], db_features[2]),
    ]:
        print_similarity_table(fa, fb)
