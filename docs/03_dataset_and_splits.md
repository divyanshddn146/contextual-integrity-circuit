# Datasets and analysis splits

## CLEAN304

The controlled dataset contains 304 scenarios. Each scenario defines a sender, information, allowed and disallowed recipients, allowed and disallowed purposes, source/domain metadata, and manual plausibility notes.

The four matched conditions are:

| Condition | Recipient | Purpose | Expected decision |
|---|---|---|---|
| A | allowed | allowed | Yes |
| B | disallowed | allowed | No |
| C | allowed | disallowed | No |
| D | disallowed | disallowed | No |

The A/B/C/D construction lets recipient and purpose be changed while holding the underlying scenario fixed.

### Analysis counts

| Analysis | Count |
|---|---:|
| Raw Base/CI activation similarity | 304 |
| AB recipient-improvement contrast | 49 |
| AC purpose-improvement contrast | 87 |
| AD both/final improvement contrast | 190 |
| Strict recipient-span subset | 28 |
| Strict purpose-span subset | 65 |
| Strict both-span subset | 85 |
| AD discovery split | 95 |
| AD held-out split | 95 |

The 190 AD improvement cases are the clean set where Base remains wrong on D while CI is correct. Writer ranking and several direction/component analyses use the 95-case discovery split and are evaluated on the 95 held-out cases unless the report states otherwise.

The final input files are under `data/final/`.

## Broader 391-case patching pool

The repository also retains a 391-scenario source-capped pool used by some broad patching, activation-similarity, and cross-model analyses during the full sweep. The final report reports the clean contrast-specific eligibility counts above.

## PrivacyLens

The transfer evaluation uses 493 PrivacyLens scenarios at four prompt levels:

```text
seed
vignette
trajectory
trajectory_enhancing
```

That gives 1,972 prompt instances in total.

For the CI checkpoint, the number of native-No prompts used in the all-level transfer analyses is:

| Level | CI native No |
|---|---:|
| seed | 481 |
| vignette | 485 |
| trajectory | 478 |
| trajectory-enhancing | 493 |
| **Total** | **1,937** |

For Base, the corresponding native decisions are:

| Level | Base No | Base Yes |
|---|---:|---:|
| seed | 477 | 16 |
| vignette | 480 | 13 |
| trajectory | 462 | 31 |
| trajectory-enhancing | 491 | 2 |
| **Total** | **1,910** | **62** |

The PrivacyLens analyses convert each case into a simplified Yes/No disclosure decision prompt. They do not claim to reproduce the full original agent-action benchmark interaction format.

## Why the split matters

CLEAN304 provides matched counterfactuals and precise intervention sites, so it is useful for mechanism discovery. PrivacyLens serves a different role: testing whether the already identified components remain behaviorally relevant on a different prompt distribution. Re-running every discovery search on PrivacyLens would weaken that distinction.
