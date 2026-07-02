# Main result 6: Base L18→L22 remove/rescue across all PrivacyLens levels

## Purpose

This experiment tests whether the base model also has a partially usable upstream L18→L22 routing pathway.

It has two directions:

1. **Remove:** base normal-No cases → patch L18 top5 heads toward A/allowed → test No→Yes and L22 shift toward A.
2. **Rescue:** base normal-Yes failures → patch L18 top5 heads toward D/refusal → test Yes→No and L22 shift toward D.

The same L18 top5 head identities are used:

```text
L18H15, L18H18, L18H4, L18H13, L18H20
```

## Base remove: No → Yes

| Level | Base No cases | Top L18 No→Yes | Random No→Yes | Margin shift toward Yes | L22 shift toward A |
|---|---:|---:|---:|---:|---:|
| seed | 477 | 80/477 = 16.8% | 1/477 | +17.80 | +22.49 |
| vignette | 480 | 90/480 = 18.8% | 0/480 | +16.04 | +19.21 |
| trajectory | 462 | 214/462 = 46.3% | 0/462 | +16.38 | +19.39 |
| trajectory_enhancing | 491 | 69/491 = 14.1% | 0/491 | +15.14 | +15.94 |

Overall:

```text
Top L18 remove: 453/1910 No→Yes = 23.7%
Random remove: 1/1910 No→Yes = 0.05%
```

## Base rescue: Yes → No

| Level | Base Yes cases | Top L18 Yes→No | Random Yes→No | Margin shift toward No | L22 shift toward D |
|---|---:|---:|---:|---:|---:|
| seed | 16 | 5/16 = 31.2% | 1/16 | +4.26 | +4.85 |
| vignette | 13 | 4/13 = 30.8% | 0/13 | +5.77 | +5.95 |
| trajectory | 31 | 20/31 = 64.5% | 1/31 | +7.51 | +8.00 |
| trajectory_enhancing | 2 | 2/2 = 100% | 0/2 | +6.59 | +9.16 |

Overall:

```text
Top L18 rescue: 31/62 Yes→No = 50.0%
Random rescue: 2/62 Yes→No = 3.2%
```

## Generation examples

Remove generation:

```text
seed: 5/5 normal No, 5/5 patched Yes
vignette: 5/5 normal No, 5/5 patched Yes
trajectory: 5/5 normal No, 5/5 patched Yes
trajectory_enhancing: 5/5 normal No, 5/5 patched Yes
```

Rescue generation:

```text
seed: 5/5 normal Yes, 5/5 patched No
vignette: 5/5 normal Yes, 4/5 patched No
trajectory: 5/5 normal Yes, 5/5 patched No
trajectory_enhancing: 2/2 normal Yes, 2/2 patched No
```

## Interpretation

This suggests that the base model has not only downstream L22 machinery, but also a partially usable upstream L18→L22 routing pathway.

However, L18 should be described as an upstream routing component, not the final decision gate. The direct L22 interventions remain stronger.
