# Music Audio Embedding Model Comparison

## Summary Table

| Model | Spearman | Pearson | Kendall |
| --- | ---: | ---: | ---: |
| openl3 |  |  |  |
| mert |  |  |  |
| muq | 0.6303 | 0.7126 | 0.5114 |
| clap |  |  |  |
| essentia |  |  |  |

## Best Model Overall

Best overall by Spearman correlation: **muq**. This is the primary ranking metric because the human labels are ordinal 1-5 scores.

## Best Model Per Category

| Category | Best model | Spearman |
| --- | --- | ---: |
| extremely_low | n/a | insufficient score variation |
| high | n/a | insufficient score variation |
| medium_high | n/a | insufficient score variation |
| very_high | n/a | insufficient score variation |
| very_low | n/a | insufficient score variation |

## Top 5 Model Disagreement Pairs

Not enough successful embedding scores to calculate disagreement.

## Recommended Weights

Weights are proportional to positive overall Spearman correlation and normalized to sum to 1. If correlations are unavailable, they fall back to a uniform prior.

- MERT=0.000
- MuQ=1.000
- CLAP=0.000
- OpenL3=0.000

## Caveats and Limitations

- iTunes previews are 30-second AAC clips and may not represent the full track.
- Human scores are ordinal, so Spearman should be treated as the headline metric.
- Cached embeddings make reruns deterministic for the same code, dependencies, and downloaded previews.
- Essentia is an interpretable feature layer; its derived similarity is a simple heuristic over BPM, key compatibility, and danceability.
