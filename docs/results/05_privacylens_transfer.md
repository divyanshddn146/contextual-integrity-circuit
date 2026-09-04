# 5. PrivacyLens transfer

The controlled CLEAN304 data is intentionally simple, so the next question is whether the same fixed components remain behaviorally relevant on a different privacy-prompt distribution.

No PrivacyLens prompt is used to re-estimate the main D-minus-A direction or re-rank the fixed writer/head sets used in these transfer tests.

## L22 writer transfer

Across the four PrivacyLens prompt levels, CI natively answers No on 1,937 prompts.

For the fixed CLEAN304-derived L22 top-100 writer set:

| Intervention strength | No-to-Yes changes |
|---|---:|
| alpha=1 | 6/1937 |
| alpha=2 | 17/1937 |
| alpha=4 | **836/1937** |
| alpha=6 | 1937/1937 |

Matched random-neuron controls produce 0/1937 changes, and their largest mean margin movement is approximately +0.013.

The alpha=4 result is the more informative transfer result because it is strong without being at ceiling. The alpha=6 result is a stronger controllability demonstration.

## L18 head transfer

The L18 head ranking is computed from the 304 CLEAN304 A/D pairs. The fixed top-five set is:

```text
H15, H18, H4, H13, H20
```

On the 478 PrivacyLens trajectory prompts where CI natively answers No, exact A-mean replacement at alpha=1 changes:

- top 1: 4/478,
- top 3: 46/478,
- **top 5: 150/478**,
- top 10: 113/478.

The size-matched random top-five control changes 1/478. The fact that top-10 is not stronger than top-5 also argues against a generic "more heads means more disruption" explanation.

## Downstream propagation from L18 to L22

The fixed top-five intervention is then evaluated across all four PrivacyLens prompt levels while tracking N13149 without directly editing L22.

| Level | L18 top-5 changes | Random | N13149 shift toward A | Correlation with margin shift |
|---|---:|---:|---:|---:|
| seed | 56/481 | 1/481 | +20.77 | 0.816 |
| vignette | 61/485 | 0/485 | +16.73 | 0.911 |
| trajectory | 150/478 | 1/478 | +18.28 | 0.897 |
| trajectory-enhancing | 14/493 | 0/493 | +12.56 | 0.936 |

Overall, the targeted L18 intervention changes 281/1937 decisions versus 2/1937 for random heads.

This establishes `do(L18) -> change in N13149` and independently `do(L18) -> change in decision`. It does **not** establish blocked mediation, because N13149 is not clamped while intervening at L18.

Saved outputs: `results/privacylens/ci_l22_writer_transfer/`, `results/privacylens/ci_l18_head_transfer/`, and `results/privacylens/ci_l18_to_l22_propagation/`.
