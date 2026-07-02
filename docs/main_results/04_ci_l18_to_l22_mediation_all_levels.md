# Main result 4: CI L18→L22 mediation across all PrivacyLens levels

## Purpose

This experiment tests the pathway hypothesis:

```text
L18 attention heads → L22 MLP neuron 13149 → final Yes/No decision
```

It uses the fixed L18 top5 heads discovered by the attention-head scan:

```text
L18H15, L18H18, L18H4, L18H13, L18H20
```

For normal-No CI prompts, it patches those heads toward the A/allowed mean and measures:

1. Yes/No margin shift.
2. No→Yes flips.
3. L22 N13149 activation shift toward A/allowed.
4. Correlation between L22 shift and margin shift.
5. Random-head control behavior.

## All-level result

| Level | Normal-No cases | L18 top5 No→Yes flips | Random flips | Margin shift | L22 shift toward A | Corr. |
|---|---:|---:|---:|---:|---:|---:|
| seed | 481 | 56/481 = 11.6% | 1/481 | +16.94 | +20.77 | 0.816 |
| vignette | 485 | 61/485 = 12.6% | 0/485 | +14.98 | +16.73 | 0.911 |
| trajectory | 478 | 150/478 = 31.4% | 1/478 | +16.67 | +18.28 | 0.897 |
| trajectory_enhancing | 493 | 14/493 = 2.8% | 0/493 | +13.31 | +12.56 | 0.936 |

Overall:

| Intervention | Flips |
|---|---:|
| L18 top5 | 281/1937 = 14.5% |
| Random heads | 2/1937 = 0.1% |

## Interpretation

The most important result is the L22 activation mediation, not just flips.

Across all four prompt levels, patching the L18 top5 heads consistently moves L22 N13149 toward the A/allowed activation state. The correlation between L22 movement and Yes-margin movement is high across levels.

This supports the pathway claim:

> L18 attention heads act as upstream routing components that influence the downstream L22 writer-neuron decision state.

## Generation examples

The result includes qualitative generation examples. For each level, 5 paired examples were generated:

```text
normal generation
patched L18-top5 generation
```

Summary:

| Level | Normal generations | Patched generations |
|---|---:|---:|
| seed | 5/5 No | 5/5 Yes |
| vignette | 5/5 No | 5/5 Yes |
| trajectory | 5/5 No | 5/5 Yes |
| trajectory_enhancing | 5/5 No | 5/5 Yes |

Generation quality varies by level. Trajectory is cleanest; seed is more mixed/conditional. Use generation as qualitative support, not the main causal metric.

## Caveat

L18 is upstream. It should not be expected to flip every case. The direct L22 intervention is the stronger downstream decision-control result.

## Placement

Main text.
