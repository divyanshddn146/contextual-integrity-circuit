# Appendix: MLP neuron sufficiency, base rescue, and base/CI writer overlap

This appendix covers neuron-level follow-up experiments around the MLP writer-neuron story.

These are not the main writer scan itself. They ask:

1. If writer neurons are necessary-like for D→No, are they sufficient-like to make A→No?
2. Can CI-discovered writer neurons rescue base-model failures?
3. Are base-top and CI-top writer neurons mostly the same?

## Dataset

These results use the clean304-derived AD subset:

| Split | Count |
|---|---:|
| Train | 95 |
| Test | 95 |
| Total AD cases | 190 |

## 1. `mlp_neuron_sufficiency/`: naive replacement attempt

### Purpose

Allowed A prompts normally say Yes. This test replaces selected writer-neuron activations with D-like values and asks whether A becomes No.

### Result

It produces large margin shifts toward No but zero actual Yes→No flips.

| Layer | k | alpha | Mean shift toward No | Yes→No flips |
|---:|---:|---:|---:|---:|
| 20 | 50 | 2.0 | +11.74 | 0/95 |
| 20 | 20 | 2.0 | +10.32 | 0/95 |
| 22 | 50 | 2.0 | +10.00 | 0/95 |
| 23 | 50 | 2.0 | +9.49 | 0/95 |
| 22 | 20 | 2.0 | +9.03 | 0/95 |

Interpretation: naive replacement weakens Yes but is not sufficient to cross the decision boundary.

Placement: appendix diagnostic only.

## 2. `mlp_neuron_sufficiency_add_delta/`: additive D−A delta

### Purpose

This stronger sufficiency test adds the learned D−A writer-neuron activation delta to A prompts:

```text
m_j ← m_j + α × (D_mean_j − A_mean_j)
```

### Main result

At α=3.0, top writer neurons induce many Yes→No flips.

| Layer | k | alpha | Mean shift toward No | Yes→No flips |
|---:|---:|---:|---:|---:|
| 20 | 100 | 3.0 | +15.67 | 95/95 |
| 20 | 50 | 3.0 | +14.72 | 95/95 |
| 22 | 100 | 3.0 | +14.19 | 79/95 |
| 23 | 50 | 3.0 | +14.83 | 71/95 |
| 23 | 100 | 3.0 | +14.59 | 69/95 |
| 20 | 20 | 3.0 | +13.65 | 57/95 |
| 22 | 50 | 3.0 | +13.65 | 55/95 |
| 23 | 20 | 3.0 | +13.95 | 50/95 |

Random controls produced 0/95 flips across these settings.

Interpretation: adding the writer-neuron D−A delta can induce refusal, supporting sufficiency-like behavior.

## 3. `mlp_neuron_sufficiency_add_delta_seed1/`: robustness

This replicate shows the same pattern:

| Layer | k | alpha | Mean shift toward No | Yes→No flips |
|---:|---:|---:|---:|---:|
| 20 | 100 | 3.0 | +15.77 | 95/95 |
| 20 | 50 | 3.0 | +14.80 | 95/95 |
| 22 | 100 | 3.0 | +14.35 | 81/95 |
| 23 | 50 | 3.0 | +14.61 | 63/95 |
| 23 | 100 | 3.0 | +14.53 | 62/95 |
| 22 | 50 | 3.0 | +13.76 | 48/95 |

Random controls were tiny, with max random flip rate around 0.35%.

## 4. `mlp_neuron_sufficiency_strong_alpha/`

This high-alpha version shows full sufficiency at stronger strengths, but it is more artificial/OOD.

Examples:

| Layer | k | alpha | Mean shift toward No | Yes→No flips |
|---:|---:|---:|---:|---:|
| 23 | 50 | 4.0 | +21.79 | 95/95 |
| 23 | 20 | 4.0 | +21.31 | 95/95 |
| 23 | 100 | 4.0 | +20.39 | 95/95 |
| 22 | 100 | 4.0 | +16.41 | 95/95 |
| 20 | 100 | 4.0 | +16.39 | 95/95 |
| 22 | 50 | 4.0 | +16.11 | 95/95 |
| 20 | 50 | 4.0 | +15.99 | 95/95 |

Random controls stayed at 0/95 flips.

Use this as appendix only; do not emphasize high-alpha results in main text.

## 5. `base_rescue_actual_ci_top/`: replacement with CI D means

### Purpose

This older base-rescue experiment asks whether CI-discovered writer-neuron indices can rescue base D failures when patched to CI D-mean activations.

The base D test set has:

```text
normal base D decision: 95/95 Yes
mean normal base margin: +0.765 Yes-minus-No
```

### Main result

Global multilayer CI top neurons rescue many base failures:

| Selection | k | alpha | Mean shift toward No | Yes→No flips |
|---|---:|---:|---:|---:|
| global multilayer CI top | 100 | 1.0 | +0.993 | 66/95 |
| global multilayer CI top | 200 | 1.0 | +0.964 | 62/95 |
| global multilayer CI top | 50 | 1.0 | +0.876 | 62/95 |
| global multilayer CI top | 20 | 1.0 | +0.732 | 51/95 |
| global multilayer CI top | 10 | 1.0 | +0.684 | 47/95 |
| global multilayer CI top | 5 | 1.0 | +0.569 | 34/95 |
| global multilayer CI top | 1 | 1.0 | +0.363 | 15/95 |

Random controls: 0/95 flips.

Interpretation: CI-discovered writer neurons are compatible with the base model and can rescue base failures.

## 6. `base_neuron_rescue_steer_ci_top/`: CI D−A delta steering in base

### Purpose

This stronger variant adds the CI D−A neuron delta into base D prompts:

```text
base D prompt
m_j ← m_j + α × (CI_D_mean_j − CI_A_mean_j)
```

### Main result

Even tiny top-k settings work strongly.

| k | alpha | Mean shift toward No | Yes→No flips |
|---:|---:|---:|---:|
| 1 | 0.25 | +0.630 | 51/95 |
| 1 | 0.50 | +1.236 | 78/95 |
| 1 | 1.00 | +2.366 | 93/95 |
| 1 | 1.50 | +3.400 | 95/95 |
| 5 | 0.25 | +1.162 | 73/95 |
| 5 | 0.50 | +2.309 | 92/95 |
| 5 | 1.00 | +4.755 | 95/95 |
| 5 | 2.00 | +12.138 | 95/95 |
| 5 | 3.00 | +21.635 | 95/95 |

At very large k/alpha random controls can start to have some effect, so the cleanest result is top1/top5 at moderate alpha.

## 7. `base_top_vs_ci_top_steer/`: base-top vs CI-top overlap

### Purpose

This asks whether important writer neurons in base and CI are mostly the same or totally different.

### Overlap result

| Selection | k | Overlap |
|---|---:|---:|
| L22 layerwise | 50 | 46/50 = 92% |
| L22 layerwise | 100 | 92/100 = 92% |
| L22 layerwise | 200 | 177/200 = 88.5% |
| L20 layerwise | 100 | 89/100 = 89% |
| L23 layerwise | 100 | 89/100 = 89% |
| L26 layerwise | 100 | 91/100 = 91% |
| L27 layerwise | 100 | 91/100 = 91% |
| global multilayer | 100 | 90/100 = 90% |
| global multilayer | 200 | 184/200 = 92% |

### Steering result

Both CI-top and base-top sets can rescue base D failures.

Global multilayer CI-top steering:

| k | alpha | Yes→No flips |
|---:|---:|---:|
| 50 | 0.25 | 92/95 |
| 50 | 0.50 | 95/95 |
| 50 | 1.00 | 95/95 |
| 100 | 0.25 | 92/95 |
| 100 | 0.50 | 95/95 |
| 100 | 1.00 | 95/95 |
| 200 | 0.25 | 93/95 |
| 200 | 0.50 | 95/95 |
| 200 | 1.00 | 95/95 |

Global multilayer base-top steering:

| k | alpha | Yes→No flips |
|---:|---:|---:|
| 50 | 0.25 | 79/95 |
| 50 | 0.50 | 92/95 |
| 50 | 1.00 | 95/95 |
| 100 | 0.25 | 92/95 |
| 100 | 0.50 | 95/95 |
| 100 | 1.00 | 95/95 |
| 200 | 0.25 | 92/95 |
| 200 | 0.50 | 95/95 |
| 200 | 1.00 | 95/95 |

Random controls are small, with maximum random mean flip rate around 2.1%.

## Main interpretation

These results strongly support the pre-existing machinery claim:

> Base and CI top writer-neuron sets substantially overlap, and CI-derived writer-neuron deltas can rescue base failures.

## Suggested main-text mention

> Additional neuron-level controls supported this interpretation: base and CI top writer-neuron sets strongly overlapped, with 92/100 overlap for the L22 top-100 neurons, and adding CI-derived writer-neuron D−A deltas could rescue held-out base D failures into No responses.

## Placement

Appendix, with one short mention in the main text if space allows.
