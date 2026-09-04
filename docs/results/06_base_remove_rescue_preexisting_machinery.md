# 6. Base remove/rescue: the key pre-existing-machinery test

The previous experiments identify a candidate pathway in CI and show strong cross-checkpoint compatibility. That still leaves one important alternative: CI could have created the L18/L22 machinery, while Base merely retained enough downstream capacity to read a transplanted CI state.

The direct test is to intervene on the corresponding machinery **inside Base itself**.

## L22 remove/rescue

Across the four PrivacyLens prompt levels, Base has 1,910 native-No decisions and 62 native-Yes decisions.

| Intervention | Targeted changes | Matched random |
|---|---:|---:|
| L22 remove, alpha=6 | **1910/1910** No-to-Yes | 0/1910 |
| L22 rescue, alpha=2 | **56/62** Yes-to-No | 0/62 |

The weaker L22 removal at alpha=4 already changes 919/1910 decisions, so the result is not visible only at the ceiling-strength setting.

Removal and rescue answer complementary questions. Removal shows that the selected L22 contribution is already active in successful Base No decisions. Rescue shows that adding the corresponding No-aligned contribution can recover many Base failures.

## L18 remove/rescue

The same logic is repeated upstream using the fixed CLEAN304-ranked heads H15, H18, H4, H13, and H20. The head identities come from the CI/CLEAN304 analysis, but the A and D reference activations used for the Base interventions are computed within Base itself.

| Intervention | Targeted changes | Matched random |
|---|---:|---:|
| L18 remove toward A | **453/1910** No-to-Yes | 1/1910 |
| L18 rescue toward D | **31/62** Yes-to-No | 2/62 |

In both directions, the L18 intervention also moves downstream N13149 toward the corresponding target state.

## Interpretation

This is the strongest evidence against the original "entirely new machinery" hypothesis. The downstream L22 writer mechanism is already behaviorally active in Base, and the upstream L18 head set is also partially active. The direct L22 intervention remains stronger, which is consistent with L18 being an upstream routing component rather than the final decision gate.

Saved outputs: `results/privacylens/base_l22_remove_rescue/` and `results/privacylens/base_l18_remove_rescue/`.
