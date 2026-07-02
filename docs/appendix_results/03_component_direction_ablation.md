# Appendix: component direction ablation

## Purpose

This experiment is a coarse component-level direction ablation. It asks where the D-vs-A privacy/refusal direction is causally active:

1. Attention output.
2. MLP output.
3. Full residual stream after the layer (`resid_post`).

It tests components across layers 0–27 with alpha values 0.5, 1.0, and 1.5.

The intervention removes the component's positive projection along the D-vs-A refusal direction from D/refusal prompts and checks whether No becomes Yes.

## Dataset

This uses the clean304-derived AD subset:

| Split | Count |
|---|---:|
| Train | 95 |
| Test | 95 |
| Total | 190 |

The ablation is evaluated on 95 held-out D/refusal prompts.

## Main conclusion

The result motivates the targeted pathway analysis:

```text
L18 attention heads → L22 MLP writer pathway → final privacy decision
```

Coarse localization shows:

- The strongest attention contribution is sharply localized around **L18**.
- MLP components are strong around **L20–L22** and late layers.
- The residual stream contains a very strong D-vs-A direction from L18 onward.

## Attention component results

At α=1.0:

| Layer | No→Yes flips | Flip rate | Mean shift toward Yes |
|---:|---:|---:|---:|
| L18 | 93/95 | 97.9% | +2.335 |
| L20 | 36/95 | 37.9% | +0.397 |
| L21 | 29/95 | 30.5% | +0.338 |
| L19 | 7/95 | 7.4% | +0.112 |
| L17 | 3/95 | 3.2% | +0.052 |
| L22 | 0/95 | 0% | 0.000 |
| L23 | 0/95 | 0% | 0.000 |

Across alphas:

| Layer | α=0.5 flips | α=1.0 flips | α=1.5 flips |
|---:|---:|---:|---:|
| L18 | 82/95 | 93/95 | 95/95 |
| L20 | 13/95 | 36/95 | 54/95 |
| L21 | 12/95 | 29/95 | 48/95 |
| L19 | 4/95 | 7/95 | 9/95 |

Interpretation: L18 is the dominant attention component, which motivated the L18 attention-head scan.

## MLP component results

At α=1.0:

| Layer | No→Yes flips | Flip rate | Mean shift toward Yes |
|---:|---:|---:|---:|
| L27 | 94/95 | 98.9% | +3.465 |
| L21 | 94/95 | 98.9% | +2.813 |
| L20 | 94/95 | 98.9% | +2.586 |
| L22 | 91/95 | 95.8% | +1.954 |
| L19 | 87/95 | 91.6% | +1.782 |
| L18 | 72/95 | 75.8% | +0.874 |
| L23 | 59/95 | 62.1% | +0.672 |
| L26 | 59/95 | 62.1% | +0.650 |

At α=1.5:

| Layer | No→Yes flips |
|---:|---:|
| L27 | 95/95 |
| L21 | 95/95 |
| L20 | 95/95 |
| L22 | 95/95 |
| L19 | 95/95 |
| L18 | 80/95 |
| L23 | 75/95 |
| L26 | 74/95 |

Interpretation: late/middle-late MLP components carry a strong refusal direction. This motivates the targeted L22 MLP writer-neuron scan.

## Residual stream results

At α=1.0:

| Layer | No→Yes flips | Flip rate | Mean shift toward Yes |
|---:|---:|---:|---:|
| L18 | 95/95 | 100% | +3.208 |
| L19 | 95/95 | 100% | +4.228 |
| L20 | 95/95 | 100% | +5.240 |
| L21 | 95/95 | 100% | +5.023 |
| L22 | 95/95 | 100% | +5.363 |
| L23 | 95/95 | 100% | +5.358 |
| L24 | 95/95 | 100% | +5.595 |
| L25 | 95/95 | 100% | +6.073 |
| L26 | 95/95 | 100% | +6.244 |
| L27 | 95/95 | 100% | +5.809 |

The full residual stream contains a strong D-vs-A direction from L18 onward. This is broad evidence, not a localized mechanism.

## Projection analysis

### Attention D−A projection gap

| Layer | D−A projection gap |
|---:|---:|
| L18 | 4.166 |
| L23 | 3.775 |
| L25 | 3.085 |
| L22 | 2.387 |
| L19 | 2.316 |

### MLP D−A projection gap

| Layer | D−A projection gap |
|---:|---:|
| L27 | 51.019 |
| L26 | 34.556 |
| L23 | 24.546 |
| L25 | 23.524 |
| L22 | 23.437 |
| L24 | 23.365 |
| L20 | 16.824 |
| L21 | 15.766 |

### Residual D−A projection gap

| Layer | D−A projection gap |
|---:|---:|
| L27 | 138.772 |
| L26 | 132.619 |
| L25 | 111.118 |
| L24 | 93.690 |
| L23 | 80.312 |
| L22 | 62.273 |
| L21 | 45.728 |
| L20 | 36.136 |
| L18 | 14.682 |

## Random controls

Random-direction controls are tiny compared with real direction interventions:

| Component | Max random flips |
|---|---:|
| attention | 3/95 |
| MLP | 8/95 |
| residual | 2/95 |

## Placement

Appendix/supporting, but worth one sentence in main text.

Suggested sentence:

> A coarse component-level direction ablation first localized causal signal to L18 attention and late MLP components: removing the D-vs-A direction from L18 attention flipped 93/95 held-out D prompts, and removing it from L22 MLP flipped 91/95, while random directions produced at most 8/95 flips.
