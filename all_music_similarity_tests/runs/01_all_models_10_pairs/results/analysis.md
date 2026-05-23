# Run 01: All Models, 10 Pairs

This run compared OpenL3, MERT, MuQ-MuLan, CLAP, and Essentia-derived features on the first 10 curated pairs.

## Summary

| Model | Spearman | Pearson | Kendall |
| --- | ---: | ---: | ---: |
| MuQ | 0.6039 | 0.6048 | 0.5292 |
| OpenL3 | 0.4577 | 0.6749 | 0.3276 |
| MERT | 0.2479 | 0.1549 | 0.1764 |
| CLAP | 0.0445 | 0.3685 | 0.0252 |
| Essentia | -0.3560 | -0.2307 | -0.2772 |

## Takeaway

MuQ was the best overall model by Spearman rank correlation. OpenL3 and CLAP produced very high cosine scores for nearly every pair, including intentionally distant pairs, so they were less useful as discriminators on this set.

## Recommended Weights

- MERT=0.183
- MuQ=0.446
- CLAP=0.033
- OpenL3=0.338

## Biggest Disagreements

| Pair | Human | Scores |
| --- | ---: | --- |
| p002 | 4 | OpenL3=0.982, MERT=0.829, MuQ=0.071, CLAP=0.940 |
| p009 | 1 | OpenL3=0.985, MERT=0.827, MuQ=0.147, CLAP=0.947 |
| p010 | 1 | OpenL3=0.975, MERT=0.751, MuQ=0.197, CLAP=0.985 |
| p008 | 1 | OpenL3=0.982, MERT=0.837, MuQ=0.504, CLAP=0.807 |
| p006 | 3 | OpenL3=0.983, MERT=0.728, MuQ=0.580, CLAP=0.981 |
