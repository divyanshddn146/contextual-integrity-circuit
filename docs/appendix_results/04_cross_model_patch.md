# Appendix: cross-model patching

## Purpose

Cross-model patching tests whether base and CI models share compatible privacy-decision geometry.

There are two related experiments:

1. `cross_model_patch.py`: broad A/B/C/D cross-model patching across final and span sites.
2. `cross_model_DD_final_both.py`: focused D-only final-token swap between base and CI.

## Important interpretation of direction names

Names such as `A_to_D` mean:

```text
source activation = A
target prompt = D
```

So `A_to_D` means patch A activation into a D prompt, often testing whether D/No becomes A/Yes. It does not mean “make A become D.”

## Files

The cross-model result set contains:

```text
full_final_and_span_detail.csv
full_final_and_span_summary.csv
full_final_and_span_peaks.csv
DD_same_final_both_detail.csv
DD_same_final_both_summary.csv
DD_same_final_both_peaks.csv
```

## Dataset

Clean304-derived subsets:

| Patch set | n |
|---|---:|
| final_AB | 49 |
| final_AC | 87 |
| final_AD | 190 |
| recipient_span_AB | 28 |
| purpose_span_AC | 65 |
| both_span_AD | 85 |
| DD_same_final_both | 190 |

## 1. Broad cross-model patching: base → CI

This asks whether base activations can drive CI decisions. The answer is yes, very strongly.

### Final-token patching: base → CI

| Experiment | Meaning | Best layer | Flips |
|---|---|---:|---:|
| final_AB A_to_B | base A into CI B | L26 | 49/49 |
| final_AB B_to_A | base B into CI A | L27 | 48/49 |
| final_AC A_to_C | base A into CI C | L26 | 86/87 |
| final_AC C_to_A | base C into CI A | L27 | 86/87 |
| final_AD A_to_D | base A into CI D | L26 | 188/190 |
| final_AD D_to_A | base D into CI A | L27 | 186/190 |

### Span patching: base → CI

| Experiment | Meaning | Best layer | Flips |
|---|---|---:|---:|
| recipient_span_AB A_to_B | base A recipient span into CI B | L6 | 28/28 |
| recipient_span_AB B_to_A | base B recipient span into CI A | L6 | 26/28 |
| purpose_span_AC A_to_C | base A purpose span into CI C | L0 | 64/65 |
| purpose_span_AC C_to_A | base C purpose span into CI A | L2 | 64/65 |
| both_span_AD A_to_D | base A both span into CI D | L3 | 84/85 |
| both_span_AD D_to_A | base D both span into CI A | L4 | 82/85 |

Interpretation: base span-level and final-token representations are already readable by the CI model.

## 2. Broad cross-model patching: CI → base

CI final disallowed activations patched into base A prompts are very strong:

| Experiment | Meaning | Best layer | Flips |
|---|---|---:|---:|
| final_AB B_to_A | CI B into base A | L27 | 49/49 |
| final_AC C_to_A | CI C into base A | L27 | 87/87 |
| final_AD D_to_A | CI D into base A | L27 | 190/190 |

CI A-source patches into base disallowed targets look weaker in flip counts:

| Experiment | Best flip count |
|---|---:|
| final_AB A_to_B | 9/49 |
| final_AC A_to_C | 5/87 |
| final_AD A_to_D | 16/190 |

This does not necessarily mean failure. Base disallowed targets are often already Yes-like, so A-source patches have less room to cause additional Yes flips.

## 3. DD same-final cross-model patching

This is the cleanest cross-model result to mention in the main text.

### CI D → base D

Patch CI D/refusal final activation into base D prompt.

Result:

```text
CI D → base D rescued 189/190 base cases into No.
patched_no_rate = 100%
```

Interpretation: the base model can decode and use CI-like refusal final-token activations.

### base D → CI D

Patch base D final activation into CI D prompt.

Result:

```text
base D → CI D destroyed 188/190 CI refusals.
patched_yes_rate = 100%
```

Interpretation: base D activations are weaker/more Yes-like than CI D activations; replacing CI D with base D destroys CI's refusal.

## Overall interpretation

Cross-model patching supports the shared-geometry/routing claim:

> Base and CI share compatible activation geometry. Base activations can drive CI decisions, and CI final refusal activations can drive base refusals. However, the base model does not naturally route disallowed prompts into the strong CI-like refusal state as reliably.

## Main-text usage

Mention only the focused DD same-final headline result in the main text:

> Cross-model D-final patching showed that CI final-token refusal activations can rescue base D failures in 189/190 cases, while base D activations patched into CI D prompts destroy CI refusals in 188/190 cases.

Full details belong in appendix.
