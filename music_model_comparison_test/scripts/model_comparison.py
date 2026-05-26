"""
Compare music audio embedding models against curated human similarity scores.

Usage:
    python3 model_comparison.py

The script reads test_pairs.json from the project root. If it is missing, a
starter file is created so you can edit it before a full run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import requests
from tqdm import tqdm


ROOT = Path(__file__).resolve().parent
TEST_PAIRS_PATH = ROOT / "test_pairs.json"
AUDIO_CACHE = ROOT / "audio_cache"
EMBEDDING_CACHE = ROOT / "embedding_cache"
FEATURE_CACHE = ROOT / "feature_cache"
RESULTS_DIR = ROOT / "results"
LOG_PATH = RESULTS_DIR / "run.log"

MODEL_DOWNLOAD_WARNING = """
First uncached run may download several large model checkpoints:
  - MuQ-MuLan-large: roughly 3 GB
  - CLAP music: roughly 1.5 GB
  - MERT-v1-95M: roughly 400 MB
  - OpenL3: roughly 50 MB
Audio previews are cached in audio_cache/ and embeddings in embedding_cache/.
"""

EMBEDDING_MODELS = ("openl3", "mert", "muq", "clap")
ALL_SCORE_MODELS = ("openl3", "mert", "muq", "clap", "essentia")


@dataclass(frozen=True)
class Track:
    artist: str
    title: str

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.title}"


@dataclass(frozen=True)
class TestPair:
    pair_id: str
    track_a: Track
    track_b: Track
    human_score: float
    category: str
    note: str = ""


class ModelUnavailable(RuntimeError):
    pass


class EmbeddingBackend:
    name: str
    sample_rate: int

    def embed(self, wav: np.ndarray) -> np.ndarray:
        raise NotImplementedError


def ensure_dirs() -> None:
    for path in (AUDIO_CACHE, EMBEDDING_CACHE, FEATURE_CACHE, RESULTS_DIR):
        path.mkdir(exist_ok=True)


def setup_logging() -> None:
    ensure_dirs()
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(console)


def configure_matplotlib_cache() -> None:
    cache_dir = RESULTS_DIR / "matplotlib"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))


def slugify(value: str, max_len: int = 90) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:max_len] or "unknown"


def stable_track_key(track: Track) -> str:
    raw = f"{track.artist}::{track.title}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:10]
    return f"{slugify(track.artist)}_{slugify(track.title)}_{digest}"


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return float("nan")
    return float(np.dot(a, b) / denom)


def load_audio(path: Path, sample_rate: int) -> np.ndarray:
    try:
        import librosa
    except ImportError as exc:
        raise ModelUnavailable("librosa is required for audio loading") from exc

    wav, _sr = librosa.load(path, sr=sample_rate, mono=True)
    return wav.astype(np.float32, copy=False)


def search_itunes_preview(track: Track) -> str:
    queries = [
        {"term": track.label, "media": "music", "entity": "song", "limit": 5},
        {"term": track.label, "media": "all", "limit": 10},
    ]
    for params in queries:
        response = None
        for attempt in range(4):
            response = requests.get("https://itunes.apple.com/search", params=params, timeout=20)
            if response.status_code != 429:
                break
            delay = 5 * (attempt + 1)
            logging.warning("iTunes rate limited %s; retrying in %ss", track.label, delay)
            time.sleep(delay)
        if response is None:
            continue
        response.raise_for_status()
        for result in response.json().get("results", []):
            preview = result.get("previewUrl")
            if preview:
                return preview
    raise ValueError(f"No iTunes preview URL for {track.label}")


def cached_audio_path(track: Track) -> Path:
    return AUDIO_CACHE / f"{stable_track_key(track)}.m4a"


def fetch_audio(track: Track) -> Path:
    path = cached_audio_path(track)
    if path.exists() and path.stat().st_size > 0:
        logging.info("audio cache hit: %s", track.label)
        return path

    logging.info("fetching audio: %s", track.label)
    preview_url = search_itunes_preview(track)
    response = requests.get(preview_url, timeout=45)
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


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


def to_device(batch: dict[str, Any], device: str) -> dict[str, Any]:
    moved = {}
    for key, value in batch.items():
        moved[key] = value.to(device) if hasattr(value, "to") else value
    return moved


class OpenL3Backend(EmbeddingBackend):
    name = "openl3"
    sample_rate = 48_000

    def __init__(self) -> None:
        configure_matplotlib_cache()
        try:
            import openl3
        except ImportError as exc:
            raise ModelUnavailable("openl3 is not installed") from exc
        self.openl3 = openl3

    def embed(self, wav: np.ndarray) -> np.ndarray:
        emb, _ts = self.openl3.get_audio_embedding(
            wav,
            self.sample_rate,
            content_type="music",
            embedding_size=512,
            center=True,
            hop_size=0.1,
            verbose=False,
        )
        return emb.mean(axis=0).astype(np.float32)


class MertBackend(EmbeddingBackend):
    name = "mert"
    sample_rate = 24_000

    def __init__(self, device: str) -> None:
        try:
            import torch
            from transformers import AutoModel, Wav2Vec2FeatureExtractor
        except ImportError as exc:
            raise ModelUnavailable("torch and transformers are required for MERT") from exc

        self.torch = torch
        self.device = device
        logging.info("loading MERT on %s", device)
        self.processor = Wav2Vec2FeatureExtractor.from_pretrained(
            "m-a-p/MERT-v1-95M",
            trust_remote_code=True,
        )
        self.model = AutoModel.from_pretrained(
            "m-a-p/MERT-v1-95M",
            trust_remote_code=True,
        ).to(device).eval()

    def embed(self, wav: np.ndarray) -> np.ndarray:
        inputs = self.processor(wav, sampling_rate=self.sample_rate, return_tensors="pt")
        inputs = to_device(dict(inputs), self.device)
        with self.torch.no_grad():
            outputs = self.model(**inputs)
            emb = outputs.last_hidden_state.mean(dim=1)
        return emb.detach().cpu().numpy()[0].astype(np.float32)


class MuqBackend(EmbeddingBackend):
    name = "muq"
    sample_rate = 24_000

    def __init__(self, device: str) -> None:
        try:
            import torch
            from muq import MuQMuLan
        except ImportError as exc:
            raise ModelUnavailable("muq and torch are required for MuQ-MuLan") from exc

        self.torch = torch
        self.device = device
        logging.info("loading MuQ-MuLan on %s", device)
        self.model = MuQMuLan.from_pretrained("OpenMuQ/MuQ-MuLan-large").to(device).eval()

    def embed(self, wav: np.ndarray) -> np.ndarray:
        audio_tensor = self.torch.tensor(wav, dtype=self.torch.float32).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            emb = self.model(wavs=audio_tensor)
        return emb.detach().cpu().numpy()[0].astype(np.float32)


class ClapBackend(EmbeddingBackend):
    name = "clap"
    sample_rate = 48_000

    def __init__(self, device: str) -> None:
        try:
            import torch
            from transformers import ClapModel, ClapProcessor
        except ImportError as exc:
            raise ModelUnavailable("torch and transformers are required for CLAP") from exc

        self.torch = torch
        self.device = device
        logging.info("loading CLAP on %s", device)
        self.processor = ClapProcessor.from_pretrained("laion/larger_clap_music")
        self.model = ClapModel.from_pretrained("laion/larger_clap_music").to(device).eval()

    def embed(self, wav: np.ndarray) -> np.ndarray:
        inputs = self.processor(audio=[wav], return_tensors="pt", sampling_rate=self.sample_rate)
        inputs = to_device(dict(inputs), self.device)
        with self.torch.no_grad():
            emb = self.model.get_audio_features(**inputs)
        if not hasattr(emb, "detach"):
            pooled = getattr(emb, "pooler_output", None)
            emb = pooled if pooled is not None else getattr(emb, "audio_embeds", None)
        if emb is None:
            raise RuntimeError("CLAP returned no audio embedding tensor")
        return emb.detach().cpu().numpy()[0].astype(np.float32)


def load_backend(name: str, device: str) -> EmbeddingBackend:
    backends = {
        "openl3": lambda: OpenL3Backend(),
        "mert": lambda: MertBackend(device),
        "muq": lambda: MuqBackend(device),
        "clap": lambda: ClapBackend(device),
    }
    try:
        return backends[name]()
    except Exception as exc:
        if device == "mps" and name in {"mert", "muq", "clap"}:
            logging.warning("%s failed on MPS, retrying on CPU: %s", name, exc)
            return load_backend_cpu(name)
        raise


def load_backend_cpu(name: str) -> EmbeddingBackend:
    if name == "openl3":
        return OpenL3Backend()
    if name == "mert":
        return MertBackend("cpu")
    if name == "muq":
        return MuqBackend("cpu")
    if name == "clap":
        return ClapBackend("cpu")
    raise ValueError(name)


def embedding_cache_path(model_name: str, track: Track) -> Path:
    return EMBEDDING_CACHE / f"{model_name}_{stable_track_key(track)}.npy"


def get_embedding(track: Track, backend: EmbeddingBackend) -> np.ndarray:
    cache_path = embedding_cache_path(backend.name, track)
    if cache_path.exists():
        logging.info("embedding cache hit: %s %s", backend.name, track.label)
        return np.load(cache_path)

    audio_path = fetch_audio(track)
    wav = load_audio(audio_path, backend.sample_rate)
    logging.info("computing %s embedding: %s", backend.name, track.label)
    emb = backend.embed(wav)
    np.save(cache_path, emb)
    return emb


def normalize_key_name(key: str) -> str:
    aliases = {
        "Db": "C#",
        "Eb": "D#",
        "Gb": "F#",
        "Ab": "G#",
        "Bb": "A#",
    }
    return aliases.get(key, key)


def key_to_camelot(key: str | None, scale: str | None) -> tuple[int, str] | None:
    if not key or not scale:
        return None
    key = normalize_key_name(key)
    scale = scale.lower()
    minor = {
        "G#": 1,
        "D#": 2,
        "A#": 3,
        "F": 4,
        "C": 5,
        "G": 6,
        "D": 7,
        "A": 8,
        "E": 9,
        "B": 10,
        "F#": 11,
        "C#": 12,
    }
    major = {
        "B": 1,
        "F#": 2,
        "C#": 3,
        "G#": 4,
        "D#": 5,
        "A#": 6,
        "F": 7,
        "C": 8,
        "G": 9,
        "D": 10,
        "A": 11,
        "E": 12,
    }
    if scale.startswith("minor") or scale == "m":
        number = minor.get(key)
        mode = "A"
    else:
        number = major.get(key)
        mode = "B"
    return (number, mode) if number else None


def key_compatible(a_key: str | None, a_scale: str | None, b_key: str | None, b_scale: str | None) -> bool | None:
    a = key_to_camelot(a_key, a_scale)
    b = key_to_camelot(b_key, b_scale)
    if not a or not b:
        return None
    a_num, a_mode = a
    b_num, b_mode = b
    if a_num == b_num:
        return True
    if a_mode == b_mode and ((a_num - b_num) % 12 in {1, 11}):
        return True
    return False


def feature_cache_path(track: Track) -> Path:
    return FEATURE_CACHE / f"{stable_track_key(track)}.json"


def compute_essentia_features_for_audio(audio_path: Path) -> dict[str, Any]:
    try:
        import essentia.standard as es
    except ImportError as exc:
        raise ModelUnavailable("essentia or essentia-tensorflow is not installed") from exc

    wav = load_audio(audio_path, 44_100)
    features: dict[str, Any] = {
        "bpm": None,
        "key": None,
        "scale": None,
        "danceability": None,
    }
    try:
        rhythm = es.RhythmExtractor2013(method="multifeature")
        bpm, _beats, _conf, _estimates, _intervals = rhythm(wav)
        features["bpm"] = float(bpm)
    except Exception as exc:
        logging.exception("Essentia BPM failed for %s: %s", audio_path, exc)

    try:
        key, scale, strength = es.KeyExtractor()(wav)
        features["key"] = key
        features["scale"] = scale
        features["key_strength"] = float(strength)
    except Exception as exc:
        logging.exception("Essentia key failed for %s: %s", audio_path, exc)

    try:
        dance_result = es.Danceability()(wav)
        if isinstance(dance_result, tuple):
            features["danceability"] = float(dance_result[0])
        else:
            features["danceability"] = float(dance_result)
    except Exception as exc:
        logging.exception("Essentia danceability failed for %s: %s", audio_path, exc)

    return features


def get_essentia_features(track: Track) -> dict[str, Any]:
    cache_path = feature_cache_path(track)
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    audio_path = fetch_audio(track)
    logging.info("computing Essentia features in subprocess: %s", track.label)
    env = os.environ.copy()
    env["MODEL_COMPARISON_ESSENTIA_WORKER"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--essentia-worker",
            str(audio_path),
            str(cache_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ModelUnavailable(f"Essentia worker failed for {track.label}: {detail}")

    return json.loads(cache_path.read_text())


def essentia_pair_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    parts: list[float] = []
    if a.get("bpm") is not None and b.get("bpm") is not None:
        bpm_diff = abs(float(a["bpm"]) - float(b["bpm"]))
        bpm_diff = min(bpm_diff, 240.0 - bpm_diff)
        parts.append(max(0.0, 1.0 - bpm_diff / 60.0))
    if a.get("danceability") is not None and b.get("danceability") is not None:
        diff = abs(float(a["danceability"]) - float(b["danceability"]))
        parts.append(max(0.0, 1.0 - diff))
    compat = key_compatible(a.get("key"), a.get("scale"), b.get("key"), b.get("scale"))
    if compat is not None:
        parts.append(1.0 if compat else 0.0)
    return float(np.mean(parts)) if parts else float("nan")


def create_starter_pairs(path: Path) -> None:
    starter = [
        ("p001", ("The Beatles", "Come Together"), ("The Beatles", "Something"), 4, "same_artist_same_album", "Abbey Road production era."),
        ("p002", ("Daft Punk", "Get Lucky"), ("Daft Punk", "Lose Yourself to Dance"), 5, "same_artist_same_album", "Same album and groove palette."),
        ("p003", ("Radiohead", "Airbag"), ("Radiohead", "No Surprises"), 4, "same_artist_same_album", "Same album, different intensity."),
        ("p004", ("David Bowie", "Life on Mars?"), ("David Bowie", "Let's Dance"), 3, "same_artist_different_era", "Same artist, distinct production eras."),
        ("p005", ("Madonna", "Like a Prayer"), ("Madonna", "Hung Up"), 3, "same_artist_different_era", "Dance-pop across decades."),
        ("p006", ("Disclosure", "Latch"), ("Duke Dumont", "Ocean Drive"), 4, "same_genre_different_artist", "Modern dance-pop/house adjacency."),
        ("p007", ("Aphex Twin", "Xtal"), ("Boards of Canada", "Roygbiv"), 4, "same_genre_different_artist", "Warm electronic textures."),
        ("p008", ("Nirvana", "Smells Like Teen Spirit"), ("Pearl Jam", "Even Flow"), 4, "same_genre_different_artist", "Grunge rock comparison."),
        ("p009", ("Burial", "Archangel"), ("Massive Attack", "Teardrop"), 3, "adjacent_subgenre", "Atmospheric UK electronic vs trip hop."),
        ("p010", ("Tame Impala", "Let It Happen"), ("MGMT", "Electric Feel"), 3, "adjacent_subgenre", "Psych-pop/dance crossover."),
        ("p011", ("Bill Withers", "Use Me"), ("Kaytranada", "Lite Spots"), 3, "cross_genre_similar_vibe", "Funk feel across eras."),
        ("p012", ("Stevie Wonder", "Superstition"), ("Daft Punk", "Get Lucky"), 3, "cross_genre_similar_vibe", "Groove-led comparison."),
        ("p013", ("The xx", "Intro"), ("Kendrick Lamar", "PRIDE."), 2, "cross_genre_similar_vibe", "Sparse moody textures."),
        ("p014", ("Miles Davis", "So What"), ("Metallica", "Enter Sandman"), 1, "distant_within_music", "Jazz modal track vs metal anthem."),
        ("p015", ("Bach", "Cello Suite No. 1 in G Major"), ("Skrillex", "Bangarang"), 1, "distant_within_music", "Classical solo cello vs EDM."),
        ("p016", ("Johnny Cash", "Hurt"), ("Avicii", "Levels"), 1, "distant_within_music", "Acoustic ballad vs festival dance."),
        ("p017", ("Serial", "Episode 1"), ("Daft Punk", "One More Time"), 1, "music_vs_speech", "Speech-like iTunes result if available."),
        ("p018", ("Michelle Obama", "Becoming"), ("Nirvana", "Come As You Are"), 1, "music_vs_speech", "Audiobook/speech-like result if available."),
        ("p019", ("The Beatles", "Come Together"), ("The Beatles", "Come Together"), 5, "duplicate_sanity_check", "Same track twice."),
        ("p020", ("Daft Punk", "Get Lucky"), ("Daft Punk", "Get Lucky"), 5, "duplicate_sanity_check", "Same track twice."),
    ]
    data = [
        {
            "id": pair_id,
            "track_a": {"artist": a[0], "title": a[1]},
            "track_b": {"artist": b[0], "title": b[1]},
            "human_score": score,
            "category": category,
            "note": note,
        }
        for pair_id, a, b, score, category, note in starter
    ]
    path.write_text(json.dumps(data, indent=2))


def load_test_pairs(path: Path) -> list[TestPair]:
    if not path.exists():
        create_starter_pairs(path)
        logging.warning("Created starter %s. Edit it, then re-run for curated results.", path)

    raw_pairs = json.loads(path.read_text())
    pairs: list[TestPair] = []
    for item in raw_pairs:
        pairs.append(
            TestPair(
                pair_id=str(item["id"]),
                track_a=Track(**item["track_a"]),
                track_b=Track(**item["track_b"]),
                human_score=float(item["human_score"]),
                category=str(item["category"]),
                note=str(item.get("note", "")),
            )
        )
    return pairs


def correlations(x: list[float], y: list[float]) -> dict[str, float]:
    try:
        from scipy import stats
    except ImportError:
        return {"spearman": float("nan"), "pearson": float("nan"), "kendall": float("nan")}

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    if mask.sum() < 2 or len(np.unique(x_arr[mask])) < 2 or len(np.unique(y_arr[mask])) < 2:
        return {"spearman": float("nan"), "pearson": float("nan"), "kendall": float("nan")}
    return {
        "spearman": float(stats.spearmanr(x_arr[mask], y_arr[mask]).correlation),
        "pearson": float(stats.pearsonr(x_arr[mask], y_arr[mask]).statistic),
        "kendall": float(stats.kendalltau(x_arr[mask], y_arr[mask]).correlation),
    }


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(f):
        return ""
    return f"{f:.{digits}f}"


def compute_rows(
    pairs: list[TestPair],
    model_names: list[str],
    skip_sanity: bool,
    skip_essentia: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    device = torch_device()
    logging.info("using device preference: %s", device)
    logging.info(MODEL_DOWNLOAD_WARNING.strip())

    unavailable: list[str] = []
    backends: dict[str, EmbeddingBackend] = {}
    for name in model_names:
        logging.info("loading backend: %s", name)
        try:
            backends[name] = load_backend(name, device)
        except Exception as exc:
            unavailable.append(f"{name}: {exc}")
            logging.exception("backend unavailable: %s", name)

    if not skip_sanity:
        sanity_check(backends)

    rows: list[dict[str, Any]] = []
    for pair in tqdm(pairs, desc="pairs"):
        try:
            fetch_audio(pair.track_a)
            fetch_audio(pair.track_b)
        except Exception as exc:
            logging.exception("skipping pair %s due to audio fetch failure: %s", pair.pair_id, exc)
            continue

        row: dict[str, Any] = {
            "id": pair.pair_id,
            "category": pair.category,
            "human_score": pair.human_score,
        }

        for model_name in EMBEDDING_MODELS:
            row[f"{model_name}_sim"] = float("nan")

        for name, backend in backends.items():
            try:
                emb_a = get_embedding(pair.track_a, backend)
                emb_b = get_embedding(pair.track_b, backend)
                row[f"{name}_sim"] = cosine_similarity(emb_a, emb_b)
            except Exception as exc:
                logging.exception("%s failed for pair %s: %s", name, pair.pair_id, exc)

        if skip_essentia:
            feat_a = {"bpm": None, "key": None, "scale": None, "danceability": None}
            feat_b = {"bpm": None, "key": None, "scale": None, "danceability": None}
        else:
            try:
                feat_a = get_essentia_features(pair.track_a)
                feat_b = get_essentia_features(pair.track_b)
            except Exception as exc:
                logging.exception("Essentia unavailable for pair %s: %s", pair.pair_id, exc)
                unavailable.append(f"essentia: {exc}")
                feat_a = {"bpm": None, "key": None, "scale": None, "danceability": None}
                feat_b = {"bpm": None, "key": None, "scale": None, "danceability": None}

        key_a = " ".join(v for v in [feat_a.get("key"), feat_a.get("scale")] if v)
        key_b = " ".join(v for v in [feat_b.get("key"), feat_b.get("scale")] if v)
        bpm_a = feat_a.get("bpm")
        bpm_b = feat_b.get("bpm")
        dance_a = feat_a.get("danceability")
        dance_b = feat_b.get("danceability")
        key_ok = key_compatible(feat_a.get("key"), feat_a.get("scale"), feat_b.get("key"), feat_b.get("scale"))

        row.update(
            {
                "essentia_sim": essentia_pair_similarity(feat_a, feat_b),
                "bpm_a": bpm_a,
                "bpm_b": bpm_b,
                "bpm_diff": abs(float(bpm_a) - float(bpm_b)) if bpm_a is not None and bpm_b is not None else None,
                "key_a": key_a,
                "key_b": key_b,
                "key_compatible": key_ok,
                "danceability_a": dance_a,
                "danceability_b": dance_b,
                "danceability_diff": abs(float(dance_a) - float(dance_b)) if dance_a is not None and dance_b is not None else None,
                "note": pair.note,
            }
        )
        rows.append(row)

    return rows, sorted(set(unavailable))


def sanity_check(backends: dict[str, EmbeddingBackend]) -> None:
    if not backends:
        logging.warning("No embedding backends loaded; skipping determinism sanity check.")
        return
    track = Track("The Beatles", "Come Together")
    logging.info("running determinism sanity check with %s", track.label)
    for name, backend in backends.items():
        emb_a = get_embedding(track, backend)
        emb_b = get_embedding(track, backend)
        sim = cosine_similarity(emb_a, emb_b)
        logging.info("sanity %s cosine: %.6f", name, sim)
        if not np.isfinite(sim) or sim <= 0.999:
            raise RuntimeError(f"Determinism check failed for {name}: cosine={sim}")


def write_raw_scores(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "id",
        "category",
        "human_score",
        "openl3_sim",
        "mert_sim",
        "muq_sim",
        "clap_sim",
        "essentia_sim",
        "bpm_a",
        "bpm_b",
        "bpm_diff",
        "key_a",
        "key_b",
        "key_compatible",
        "danceability_a",
        "danceability_b",
        "danceability_diff",
        "note",
    ]
    with (RESULTS_DIR / "raw_scores.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def write_correlation_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    human = [float(row["human_score"]) for row in rows]
    summary: dict[str, dict[str, float]] = {}
    lines = ["Model correlation with human_score", ""]
    for model in ALL_SCORE_MODELS:
        scores = [float(row.get(f"{model}_sim", float("nan"))) for row in rows]
        corr = correlations(scores, human)
        summary[model] = corr
        lines.append(
            f"{model}: Spearman={fmt(corr['spearman'])}, Pearson={fmt(corr['pearson'])}, Kendall={fmt(corr['kendall'])}"
        )
    (RESULTS_DIR / "correlation_summary.txt").write_text("\n".join(lines) + "\n")
    return summary


def write_per_category_breakdown(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    categories = sorted({row["category"] for row in rows})
    result: dict[str, dict[str, dict[str, float]]] = {}
    lines: list[str] = []
    for category in categories:
        subset = [row for row in rows if row["category"] == category]
        human = [float(row["human_score"]) for row in subset]
        lines.append(category)
        result[category] = {}
        for model in ALL_SCORE_MODELS:
            scores = [float(row.get(f"{model}_sim", float("nan"))) for row in subset]
            corr = correlations(scores, human)
            result[category][model] = corr
            lines.append(
                f"  {model}: Spearman={fmt(corr['spearman'])}, Pearson={fmt(corr['pearson'])}, Kendall={fmt(corr['kendall'])}"
            )
        lines.append("")
    (RESULTS_DIR / "per_category_breakdown.txt").write_text("\n".join(lines))
    return result


def normalized_for_heatmap(model: str, value: float) -> float:
    if not np.isfinite(value):
        return float("nan")
    if model == "human":
        return (value - 1.0) / 4.0
    if model == "essentia":
        return value
    return (value + 1.0) / 2.0


def write_heatmap(rows: list[dict[str, Any]]) -> None:
    configure_matplotlib_cache()
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    sorted_rows = sorted(rows, key=lambda row: (float(row["human_score"]), row["id"]))
    labels = [row["id"] for row in sorted_rows]
    models = list(ALL_SCORE_MODELS) + ["human"]
    matrix = []
    annotations = []
    for model in models:
        values = []
        notes = []
        for row in sorted_rows:
            raw = float(row["human_score"]) if model == "human" else float(row.get(f"{model}_sim", float("nan")))
            values.append(normalized_for_heatmap(model, raw))
            notes.append(fmt(raw, 2))
        matrix.append(values)
        annotations.append(notes)

    fig_width = max(10, len(labels) * 0.45)
    fig, ax = plt.subplots(figsize=(fig_width, 4.5))
    image = ax.imshow(np.asarray(matrix, dtype=float), aspect="auto", cmap="viridis", vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(labels)), labels=labels, rotation=65, ha="right")
    ax.set_yticks(np.arange(len(models)), labels=models)
    ax.set_xlabel("Pairs sorted by human_score")
    ax.set_title("Model similarity scores vs human scores")
    for y, row_notes in enumerate(annotations):
        for x, note in enumerate(row_notes):
            if note:
                ax.text(x, y, note, ha="center", va="center", color="white", fontsize=7)
    fig.colorbar(image, ax=ax, label="Normalized score")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "heatmap.png", dpi=180)
    plt.close(fig)


def recommended_weights(summary: dict[str, dict[str, float]]) -> dict[str, float]:
    positives = {
        model: max(0.0, corr.get("spearman", float("nan")))
        for model, corr in summary.items()
        if model in EMBEDDING_MODELS and np.isfinite(corr.get("spearman", float("nan")))
    }
    total = sum(positives.values())
    if total <= 0.0:
        return {model: 1.0 / len(EMBEDDING_MODELS) for model in EMBEDDING_MODELS}
    return {model: positives.get(model, 0.0) / total for model in EMBEDDING_MODELS}


def write_analysis(
    rows: list[dict[str, Any]],
    summary: dict[str, dict[str, float]],
    category_summary: dict[str, dict[str, dict[str, float]]],
    unavailable: list[str],
) -> None:
    weights = recommended_weights(summary)
    best_model = max(
        ALL_SCORE_MODELS,
        key=lambda model: summary.get(model, {}).get("spearman", float("-inf"))
        if np.isfinite(summary.get(model, {}).get("spearman", float("nan")))
        else float("-inf"),
    )

    lines = [
        "# Music Audio Embedding Model Comparison",
        "",
        "## Summary Table",
        "",
        "| Model | Spearman | Pearson | Kendall |",
        "| --- | ---: | ---: | ---: |",
    ]
    for model in ALL_SCORE_MODELS:
        corr = summary.get(model, {})
        lines.append(f"| {model} | {fmt(corr.get('spearman'))} | {fmt(corr.get('pearson'))} | {fmt(corr.get('kendall'))} |")

    lines.extend(
        [
            "",
            "## Best Model Overall",
            "",
            f"Best overall by Spearman correlation: **{best_model}**. This is the primary ranking metric because the human labels are ordinal 1-5 scores.",
            "",
            "## Best Model Per Category",
            "",
            "| Category | Best model | Spearman |",
            "| --- | --- | ---: |",
        ]
    )
    for category, model_corrs in category_summary.items():
        valid = {
            model: model_corrs.get(model, {}).get("spearman", float("nan"))
            for model in ALL_SCORE_MODELS
            if np.isfinite(model_corrs.get(model, {}).get("spearman", float("nan")))
        }
        if valid:
            best = max(valid, key=valid.get)
            lines.append(f"| {category} | {best} | {fmt(valid[best])} |")
        else:
            lines.append(f"| {category} | n/a | insufficient score variation |")

    disagreement_rows = []
    for row in rows:
        scores = [float(row.get(f"{model}_sim", float("nan"))) for model in EMBEDDING_MODELS]
        finite = [score for score in scores if np.isfinite(score)]
        if len(finite) >= 2:
            disagreement_rows.append((float(np.var(finite)), row))
    disagreement_rows.sort(reverse=True, key=lambda item: item[0])

    lines.extend(["", "## Top 5 Model Disagreement Pairs", ""])
    if disagreement_rows:
        lines.extend(["| Pair | Category | Human | Variance | Scores |", "| --- | --- | ---: | ---: | --- |"])
        for variance, row in disagreement_rows[:5]:
            score_text = ", ".join(f"{model}={fmt(row.get(f'{model}_sim'), 3)}" for model in EMBEDDING_MODELS)
            lines.append(f"| {row['id']} | {row['category']} | {fmt(row['human_score'], 1)} | {variance:.5f} | {score_text} |")
    else:
        lines.append("Not enough successful embedding scores to calculate disagreement.")

    lines.extend(
        [
            "",
            "## Recommended Weights",
            "",
            "Weights are proportional to positive overall Spearman correlation and normalized to sum to 1. If correlations are unavailable, they fall back to a uniform prior.",
            "",
            f"- MERT={weights['mert']:.3f}",
            f"- MuQ={weights['muq']:.3f}",
            f"- CLAP={weights['clap']:.3f}",
            f"- OpenL3={weights['openl3']:.3f}",
            "",
            "## Caveats and Limitations",
            "",
            "- iTunes previews are 30-second AAC clips and may not represent the full track.",
            "- Human scores are ordinal, so Spearman should be treated as the headline metric.",
            "- Cached embeddings make reruns deterministic for the same code, dependencies, and downloaded previews.",
            "- Essentia is an interpretable feature layer; its derived similarity is a simple heuristic over BPM, key compatibility, and danceability.",
        ]
    )
    if unavailable:
        lines.append("- Some backends were unavailable or failed during this run:")
        for item in unavailable:
            lines.append(f"  - {item}")
    if sys.version_info >= (3, 12):
        lines.append("- This interpreter is newer than OpenL3's commonly supported Python range. Use Python 3.10 or 3.11 if OpenL3/TensorFlow installation fails.")

    (RESULTS_DIR / "analysis.md").write_text("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=EMBEDDING_MODELS,
        default=list(EMBEDDING_MODELS),
        help="Embedding backends to run.",
    )
    parser.add_argument("--skip-sanity", action="store_true", help="Skip the duplicate embedding determinism check.")
    parser.add_argument("--skip-essentia", action="store_true", help="Skip BPM/key/danceability feature extraction.")
    parser.add_argument("--essentia-worker", nargs=2, metavar=("AUDIO_PATH", "OUTPUT_JSON"), help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    ensure_dirs()
    args = parse_args()
    if args.essentia_worker:
        audio_path, output_path = args.essentia_worker
        features = compute_essentia_features_for_audio(Path(audio_path))
        Path(output_path).write_text(json.dumps(features, indent=2, sort_keys=True))
        return 0

    setup_logging()
    pairs = load_test_pairs(TEST_PAIRS_PATH)
    rows, unavailable = compute_rows(pairs, args.models, args.skip_sanity, args.skip_essentia)
    if not rows:
        logging.error("No pair rows were produced. Check %s for errors.", LOG_PATH)
        return 1

    write_raw_scores(rows)
    summary = write_correlation_summary(rows)
    category_summary = write_per_category_breakdown(rows)
    write_heatmap(rows)
    write_analysis(rows, summary, category_summary, unavailable)

    logging.info("wrote outputs to %s", RESULTS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
