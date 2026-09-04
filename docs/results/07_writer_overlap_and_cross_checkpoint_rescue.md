# 7. Writer overlap and cross-checkpoint rescue

The Base remove/rescue experiment shows that similarly defined machinery is behaviorally active before CI tuning. Two further analyses ask whether the checkpoints also use overlapping MLP coordinates and whether a writer change estimated in CI can be used directly by Base.

## Writer identity overlap

Base and CI writer rankings are computed independently. The overlap is high throughout the late-layer region:

| Ranking | Shared writers |
|---|---:|
| L22 top 50 | 46/50 = 92.0% |
| L22 top 100 | 92/100 = 92.0% |
| L22 top 200 | 177/200 = 88.5% |
| L20 top 100 | 89/100 = 89.0% |
| L23 top 100 | 89/100 = 89.0% |
| L26 top 100 | 91/100 = 91.0% |

Across the multilayer ranking, Base and CI share 90% of the global top-100 writers and 92% of the global top-200 writers.

This overlap is observational evidence. It does not by itself show functional interchangeability.

## CI-derived writer changes inside Base

The functional test applies writer changes estimated from CI directly inside Base on the 95 held-out CLEAN304 D failures.

For the top-ranked CI writer alone:

- alpha=0.25 changes 51/95 Base decisions,
- alpha=0.5 changes 78/95,
- alpha=1 changes 93/95,
- alpha=1.5 changes 95/95.

The fixed top-five set reaches 92/95 at alpha=0.5 and 95/95 at alpha=1.

For global top-100 rankings, both independently Base-ranked and CI-ranked sets change 92/95 Base D failures at alpha=0.25 and 95/95 at alpha=0.5.

## Interpretation

The downstream writer basis is not disjoint across checkpoints. Many of the same neurons rank highly in both models, and CI-estimated writer changes can be read and used by Base's downstream computation. This strengthens the shared-machinery interpretation without requiring the stronger claim that the two checkpoints are internally identical.

Saved outputs: `results/clean304/supporting/cross_checkpoint_writer_reuse/` and `results/clean304/supporting/writer_robustness/`.
