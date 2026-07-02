# Main result 5: Base L22 remove/rescue across all PrivacyLens levels

## Purpose

This experiment tests whether the CI-discovered L22 writer-neuron pathway also exists in the base Qwen2.5-7B-Instruct model.

It has two directions:

1. **Remove:** base normal-No cases → remove L22 refusal contribution → test No→Yes.
2. **Rescue:** base normal-Yes failures → add CI-like L22 refusal contribution → test Yes→No.

## Base normal behavior

| Level | Base No | Base Yes | Total |
|---|---:|---:|---:|
| seed | 477 | 16 | 493 |
| vignette | 480 | 13 | 493 |
| trajectory | 462 | 31 | 493 |
| trajectory_enhancing | 491 | 2 | 493 |

The base model already refuses most PrivacyLens prompts, but still has some Yes failures.

## Remove result: break base refusals

L22 top100 removal:

| Level | Base No cases | α=4 No→Yes | α=6 No→Yes | Random control |
|---|---:|---:|---:|---:|
| seed | 477 | 179/477 = 37.5% | 477/477 = 100% | 0 |
| vignette | 480 | 146/480 = 30.4% | 480/480 = 100% | 0 |
| trajectory | 462 | 382/462 = 82.7% | 462/462 = 100% | 0 |
| trajectory_enhancing | 491 | 212/491 = 43.2% | 491/491 = 100% | 0 |

Overall:

```text
L22 top100 α=6 removal flipped 1910/1910 base No cases to Yes.
Random controls: 0 flips.
```

## Rescue result: fix base Yes failures

L22 top100 rescue:

| Level | Base Yes cases | α=0.5 Yes→No | α=1 Yes→No | α=2 Yes→No | Random control |
|---|---:|---:|---:|---:|---:|
| seed | 16 | 5/16 = 31.2% | 9/16 = 56.2% | 15/16 = 93.8% | 0 |
| vignette | 13 | 4/13 = 30.8% | 5/13 = 38.5% | 10/13 = 76.9% | 0 |
| trajectory | 31 | 10/31 = 32.3% | 18/31 = 58.1% | 29/31 = 93.5% | 0 |
| trajectory_enhancing | 2 | 1/2 = 50.0% | 2/2 = 100% | 2/2 = 100% | 0 |

Overall:

```text
L22 top100 α=2 rescued 56/62 base Yes failures into No.
Random controls: 0/62.
```

## Generation examples

Remove generation across all four levels:

| Generation type | Count |
|---|---:|
| Normal base generated No | 80/80 |
| Patched/remove generated Yes | 80/80 |
| Random control generated No | 80/80 |

Rescue generation across all four levels:

| Generation type | Count |
|---|---:|
| Normal base generated Yes | 94/94 |
| Patched/rescue generated No | 94/94 |
| Random control generated Yes | 94/94 |

## Interpretation

This is central evidence for the pre-existing-machinery claim.

The base model already contains a compatible downstream L22 privacy/refusal writer pathway. Removing the L22 refusal contribution breaks base refusals, while adding a CI-like contribution rescues base Yes failures.

## Placement

Main text.
