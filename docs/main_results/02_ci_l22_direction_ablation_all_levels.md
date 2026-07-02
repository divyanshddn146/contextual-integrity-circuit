# Main result 2: CI L22 direction ablation across all PrivacyLens levels

## Purpose

This is the direct downstream decision-control experiment.

It asks:

> If we remove the refusal-direction contribution of the discovered L22 writer neurons, does the CI model stop refusing and move from No to Yes?

This is a runtime activation intervention, not a permanent weight edit.

## Levels tested

Four PrivacyLens prompt levels were tested:

```text
seed
vignette
trajectory
trajectory_enhancing
```

Each level has 493 prompts.

## Normal CI behavior

| Level | Total | Normal No | Normal Yes | Mean No-case margin |
|---|---:|---:|---:|---:|
| seed | 493 | 481 | 12 | -24.19 |
| vignette | 493 | 485 | 8 | -24.09 |
| trajectory | 493 | 478 | 15 | -20.39 |
| trajectory_enhancing | 493 | 493 | 0 | -22.77 |

The intervention is evaluated on normal-No cases only:

```text
481 + 485 + 478 + 493 = 1937 normal-No cases
```

## Main L22 top100 result

| Level | α=1 flips | α=2 flips | α=4 flips | α=6 flips |
|---|---:|---:|---:|---:|
| seed | 3/481 | 5/481 | 150/481 = 31.2% | 481/481 = 100% |
| vignette | 0/485 | 2/485 | 164/485 = 33.8% | 485/485 = 100% |
| trajectory | 3/478 | 9/478 | 385/478 = 80.5% | 478/478 = 100% |
| trajectory_enhancing | 0/493 | 1/493 | 137/493 = 27.8% | 493/493 = 100% |

Overall:

| α | Total No→Yes flips | Flip rate | Mean margin shift |
|---:|---:|---:|---:|
| 1 | 6/1937 | 0.3% | +3.07 |
| 2 | 17/1937 | 0.9% | +8.00 |
| 4 | 836/1937 | 43.2% | +22.70 |
| 6 | 1937/1937 | 100% | +39.02 |

## Random controls

Random-neuron controls produced zero No→Yes flips across all levels and settings. The largest random mean margin shift was about +0.013, compared with +22.70 at α=4 and +39.02 at α=6 for L22 top100.

## Top-k comparison

At α=6, all top-k settings reach 1937/1937 flips:

| k | Overall α=6 flips |
|---:|---:|
| top50 | 1937/1937 |
| top100 | 1937/1937 |
| top200 | 1937/1937 |
| top500 | 1937/1937 |

At α=4, top100 is the cleanest non-ceiling setting:

| k | α=4 total flips |
|---:|---:|
| top50 | 636/1937 |
| top100 | 836/1937 |
| top200 | 684/1937 |
| top500 | 470/1937 |

## Generation result

For L22 top100 α=6, generation is clean across all four levels:

| Level | Normal generated No | Patched generated Yes | Random generated No |
|---|---:|---:|---:|
| seed | 481/481 | 481/481 | 481/481 |
| vignette | 485/485 | 485/485 | 485/485 |
| trajectory | 478/478 | 478/478 | 478/478 |
| trajectory_enhancing | 493/493 | 493/493 | 493/493 |

## Interpretation

The discovered L22 writer-neuron pathway is a causal downstream decision mechanism for CI privacy refusals. Removing its refusal-direction contribution systematically changes No decisions into Yes decisions, while random-neuron controls do not.

## Best paper wording

> Across all four PrivacyLens prompt levels, ablating the CI-discovered L22 writer-neuron contribution along the refusal direction caused systematic No→Yes flips. With the L22 top-100 writer neurons, α=4 flipped 836/1937 normal-No cases, while α=6 flipped all 1937/1937 cases. Random-neuron controls produced zero flips. In generation, the same intervention changed normal No responses into Yes responses across all α=6 cases, while random controls preserved No responses. This indicates that the L22 writer-neuron pathway is a causal downstream decision mechanism for CI privacy refusals.

## Placement

Main text.
