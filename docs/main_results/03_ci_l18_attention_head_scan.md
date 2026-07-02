# Main result 3: CI L18 attention-head scan

## Purpose

This experiment searches for upstream attention heads that causally affect the final privacy decision and may route context into the downstream L22 writer pathway.

It asks:

> Are there attention heads upstream of L22 whose outputs write in the privacy/refusal direction and causally move the final Yes/No decision?

## Method

The scan ranks L18 attention heads by how much their D-vs-A head-output contribution aligns with the refusal/privacy direction.

For attention heads, the writer score is approximately:

```text
writer_score(head) = dot(mean_head_output_D - mean_head_output_A, refusal_direction)
```

Positive scores indicate heads whose D-vs-A output supports the refusal/No direction.

After ranking, the top heads are causally validated by final-token head-output patching toward the A/allowed mean.

## Dataset/level

This scan was run on PrivacyLens `trajectory` prompts.

Normal CI behavior:

| Normal decision | Count |
|---|---:|
| No | 478 |
| Yes | 15 |
| Total | 493 |

The patching summaries focus on the 478 normal-No cases.

## Top L18 heads

| Rank | Head | Writer score |
|---:|---|---:|
| 1 | L18H15 | +0.9017 |
| 2 | L18H18 | +0.8557 |
| 3 | L18H4 | +0.7217 |
| 4 | L18H13 | +0.5125 |
| 5 | L18H20 | +0.4734 |
| 6 | L18H16 | +0.3363 |
| 7 | L18H5 | +0.2064 |
| 8 | L18H2 | +0.1801 |
| 9 | L18H21 | +0.1627 |
| 10 | L18H27 | +0.0706 |

The canonical top5 set used later is:

```text
L18H15, L18H18, L18H4, L18H13, L18H20
```

## Causal patching result

| Intervention | Heads | Mean margin shift toward Yes | No→Yes flips | Flip rate |
|---|---|---:|---:|---:|
| Random 1 head | random | +0.72 | 4/478 | 0.8% |
| Random 3 heads | random | +0.34 | 1/478 | 0.2% |
| Random 5 heads | random | +1.01 | 1/478 | 0.2% |
| Random 10 heads | random | +0.73 | 4/478 | 0.8% |
| L18 top1 | H15 | +1.65 | 4/478 | 0.8% |
| L18 top3 | H15,H18,H4 | +9.91 | 46/478 | 9.6% |
| L18 top5 | H15,H18,H4,H13,H20 | +16.67 | 150/478 | 31.4% |
| L18 top10 | top 10 heads | +16.82 | 113/478 | 23.6% |

## Interpretation

The L18 top5 heads causally affect the final decision. They produce a large Yes-margin shift and many No→Yes flips, while random heads have almost no effect.

Top5 is cleaner than top10: top10 has similar average margin shift but fewer flips, likely because it adds weaker/noisier heads.

## What this proves and does not prove

This result proves:

> A small set of L18 attention heads causally influences the privacy Yes/No decision.

It does not by itself prove:

> Those L18 heads operate through L22 N13149.

The L18→L22 mediation experiment provides that link.

## Placement

Main text as upstream-head discovery.
