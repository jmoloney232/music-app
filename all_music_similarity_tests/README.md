# All Music Similarity Tests

This folder collects the comparison work from the chat session. The old
`track_ingestion.py` spike is intentionally left outside this folder.

## Layout

- `current/`: latest working project snapshot, including `model_comparison.py`,
  the active 25-pair `test_pairs.json`, and the latest MuQ-only results.
- `runs/01_all_models_10_pairs/`: first test with OpenL3, MERT, MuQ-MuLan,
  CLAP, and Essentia on the original 10 pairs.
- `runs/02_muq_only_25_pairs/`: second test with 25 pairs using MuQ-MuLan only.
- `harness/`: latest harness/dependency files as a compact reference copy.
- `cache/`: audio, embedding, and feature caches from the test runs for faster
  local reruns.
- `docs/`: setup notes.
- `packages/`: earlier zip packages created during the session.

## Not Included

- `.venv/`: the Python virtual environment is not included because it is large
  and machine-specific. Recreate it with `requirements.txt`.
- `track_ingestion.py`: left in the parent folder as requested.
