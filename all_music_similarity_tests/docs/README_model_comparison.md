# Music Model Comparison Harness

Use Python 3.10 or 3.11 for the full dependency stack. This machine has
`/opt/homebrew/bin/python3.11`, which is preferable to the default `python3`
reported as 3.14.

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python model_comparison.py
```

`model_comparison.py` reads `test_pairs.json`. If the file does not exist, it
creates a 20-pair starter file for editing. Results are written to `results/`.

The first full run can download around 5 GB of model checkpoints. Audio,
embeddings, and Essentia features are cached in `audio_cache/`,
`embedding_cache/`, and `feature_cache/`.
