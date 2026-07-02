# Main result 1: CI L22 MLP writer-neuron scan

## Purpose

This experiment identifies MLP neurons whose writes explain the D-vs-A privacy/refusal direction in the CI model.

The central question is:

> Which MLP neurons write the privacy/refusal decision direction?

## Dataset

This uses the clean304-derived AD subset:

| Split | Count |
|---|---:|
| Train | 95 |
| Test | 95 |
| Total AD cases | 190 |

## Method

For each MLP neuron, the writer score is:

```text
writer_score_j = activation_gap_j(D - A) × downproj_dot_refusal_direction_j
```

A positive writer score means the neuron contributes to the D/refusal-vs-A/allowed difference. This can happen either by turning on a No-writing neuron or by turning down a Yes-writing neuron.

## Main top neurons

| Rank | Layer | Neuron | Writer score |
|---:|---:|---:|---:|
| 1 | 22 | 13149 | 8.355 |
| 2 | 23 | 7028 | 4.440 |
| 3 | 23 | 4894 | 3.378 |
| 4 | 23 | 10710 | 3.141 |
| 5 | 23 | 4059 | 2.613 |
| 6 | 26 | 10844 | 2.323 |

The strongest neuron is **L22 N13149**.

For L22 N13149:

| Quantity | Value |
|---|---:|
| A activation mean | +14.62 |
| D activation mean | -3.34 |
| D−A activation gap | -17.96 |
| Down-projection dot direction | -0.465 |
| Writer score | +8.355 |

Interpretation: L22 N13149 behaves like a Yes/allowed-writing neuron that is suppressed on D/refusal prompts. Turning down a Yes-writing neuron contributes to refusal.

## Ablation result

Ablating top writer neurons on held-out D prompts flips the model from No to Yes.

| Layer | k | No→Yes flips | Flip rate | Mean shift toward Yes |
|---:|---:|---:|---:|---:|
| 22 | 1 | 95/95 | 100% | +2.71 |
| 22 | 5 | 95/95 | 100% | +2.98 |
| 22 | 10 | 95/95 | 100% | +3.01 |
| 22 | 50 | 95/95 | 100% | +3.30 |
| 22 | 100 | 95/95 | 100% | +3.47 |
| 20 | 50 | 95/95 | 100% | +3.93 |
| 20 | 100 | 95/95 | 100% | +5.11 |

Random controls are much weaker. The main interpretation is that a small set of writer neurons, especially L22 N13149, causally controls the held-out D/refusal decision.

## Robustness variants

- `mlp_neuron_writer_seed1`: replicate run; top neuron remains L22 N13149 with writer score about 8.16 and similar flip effects.
- `mlp_neuron_writer_zero_check`: zeroing writer neurons is weaker but still shows causal effect.
- `mlp_neuron_writer_base`: base-model writer scores also identify L22 N13149, supporting shared base/CI machinery. Its ablation part is not the main result because the ablation summary is tiny/incomplete.

## Main claim from this
This is the discovery result for the downstream L22 writer-neuron pathway.
