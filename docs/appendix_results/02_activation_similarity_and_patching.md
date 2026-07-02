# Appendix: activation similarity, broad patching, and final-direction controls

This document combines the clean304 appendix results from:

```text
activation_similarity/
appendix_patching/
final_direction_ablation/
final_direction_controls/
```

## Dataset usage

These results are based on the clean304 scenario pool.

| Analysis | Count |
|---|---:|
| Raw activation similarity | 304 scenarios |
| AB recipient contrast | 49 scenarios |
| AC purpose contrast | 87 scenarios |
| AD both/final contrast | 190 scenarios |
| Strict recipient span | 28 scenarios |
| Strict purpose span | 65 scenarios |
| Strict both span | 85 scenarios |
| Final-direction ablation/control | 190 AD cases split 95 train / 95 test |

## 1. Activation similarity

### Purpose

This checks whether CI tuning radically changes the base model's hidden-state space.

### Raw final-token cosine similarity

Base and CI hidden states remain extremely aligned at the final token:

| Layer | A | B | C | D |
|---:|---:|---:|---:|---:|
| 18 | 0.9963 | 0.9962 | 0.9962 | 0.9961 |
| 20 | 0.9969 | 0.9964 | 0.9962 | 0.9958 |
| 22 | 0.9977 | 0.9970 | 0.9967 | 0.9962 |
| 24 | 0.9987 | 0.9981 | 0.9978 | 0.9973 |
| 26 | 0.9991 | 0.9987 | 0.9985 | 0.9981 |

### Contrast-direction cosine similarity

At the final token:

| Layer | AB B−A | AC C−A | AD D−A |
|---:|---:|---:|---:|
| 18 | 0.962 | 0.969 | 0.973 |
| 20 | 0.967 | 0.977 | 0.977 |
| 22 | 0.971 | 0.981 | 0.981 |
| 24 | 0.975 | 0.983 | 0.983 |
| 26 | 0.973 | 0.984 | 0.984 |
| 27 | 0.975 | 0.985 | 0.986 |

### Interpretation

CI tuning does not radically rewrite the representation space. Base and CI remain highly aligned, supporting the claim that CI tuning changes routing/use of existing representations more than creating a fully new representation space.

## 2. Final-direction ablation

### Purpose

This broad experiment tests whether the final-token D-vs-A privacy/refusal direction is causally active.

### Direction separability

| Layer | Held-out AUC | Test D−A score gap |
|---:|---:|---:|
| 16 | 0.979 | 1.93 |
| 17 | 0.996 | 2.88 |
| 18 | 1.000 | 14.68 |
| 20 | 1.000 | 36.14 |
| 22 | 1.000 | 62.27 |
| 24 | 1.000 | 93.69 |

### Ablation result at α=1.0

| Layer | No→Yes flips | Flip rate | Mean shift toward Yes |
|---:|---:|---:|---:|
| 16 | 12/95 | 12.6% | +0.153 |
| 17 | 19/95 | 20.0% | +0.283 |
| 18 | 95/95 | 100% | +3.208 |
| 20 | 95/95 | 100% | +5.240 |
| 22 | 95/95 | 100% | +5.363 |
| 24 | 95/95 | 100% | +5.595 |
| 26 | 95/95 | 100% | +6.244 |

Random directions had only about 0.7–1.4% flip rates.

### Interpretation

A broad final-token D-vs-A privacy/refusal direction is causally active from around L18 onward. This motivates the more localized L18 attention and L22 MLP analyses.

## 3. Final-direction controls

### D_remove_signed

Removing the D/refusal direction from D prompts breaks D refusals:

| Layer | α | No→Yes flips |
|---:|---:|---:|
| 18 | 0.25 | 59/95 |
| 18 | 1.0 | 95/95 |
| 20 | 1.0 | 95/95 |
| 22 | 1.0 | 95/95 |
| 26 | 1.0 | 95/95 |

### A_add_direction

Adding the D-vs-A direction to A prompts can induce refusal at high alpha:

| Layer | α | Yes→No flips |
|---:|---:|---:|
| 20 | 1.5 | 95/95 |
| 21 | 1.5 | 95/95 |
| 22 | 1.5 | 95/95 |
| 23 | 1.5 | 95/95 |
| 24 | 1.5 | 95/95 |
| 25 | 1.5 | 95/95 |
| 26 | 1.5 | 95/95 |

### A_remove_positive

Removing positive-only direction from A has essentially no flips, supporting that signed intervention matters.

## 4. Within-model patching

This older result tests whether hidden-state patching can move one PrivacyLens condition toward another within base or CI.

### Final AD patching peaks

| Model | Patch | Layer | n | Mean aligned effect | Flip rate |
|---|---|---:|---:|---:|---:|
| Base | final_AD A→D | 26 | 190 | 12.66 | 0.5% |
| Base | final_AD D→A | 27 | 190 | 14.55 | 97.9% |
| CI | final_AD A→D | 26 | 190 | 14.42 | 98.9% |
| CI | final_AD D→A | 27 | 190 | 15.89 | 100% |

### Purpose AC patching peaks

| Model | Patch | Layer | n | Mean aligned effect | Flip rate |
|---|---|---:|---:|---:|---:|
| Base | final_AC A→C | 26 | 87 | 11.49 | 2.3% |
| Base | final_AC C→A | 27 | 87 | 13.44 | 98.9% |
| CI | final_AC A→C | 26 | 87 | 13.08 | 98.9% |
| CI | final_AC C→A | 27 | 87 | 14.60 | 100% |
| CI | purpose_last_AC A→C | 9 | 87 | 8.73 | 96.6% |

### Recipient AB patching peaks

| Model | Patch | Layer | n | Mean aligned effect | Flip rate |
|---|---|---:|---:|---:|---:|
| Base | final_AB A→B | 26 | 49 | 8.44 | 0% |
| Base | final_AB B→A | 27 | 49 | 10.34 | 98.0% |
| CI | final_AB A→B | 26 | 49 | 9.00 | 100% |
| CI | final_AB B→A | 27 | 49 | 10.53 | 100% |
| CI | recipient_last_AB A→B | 6 | 49 | 6.58 | 100% |

### CI strict-span peaks

| Patch family | Direction | Layer | n | Flip rate |
|---|---|---:|---:|---:|
| recipient_span_AB | A→B | 6 | 28 | 100% |
| recipient_span_AB | B→A | 6 | 28 | 92.9% |
| purpose_span_AC | A→C | 0 | 65 | 98.5% |
| purpose_span_AC | C→A | 2 | 65 | 98.5% |
| both_span_AD | A→D | 3 | 85 | 98.8% |
| both_span_AD | D→A | 3 | 85 | 95.3% |

## Placement

Appendix/supporting.

These results support shared geometry and broad causal direction, but the main causal story should remain focused on the targeted L18→L22 pathway.
