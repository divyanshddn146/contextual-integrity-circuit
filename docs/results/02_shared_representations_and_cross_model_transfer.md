# 2. Shared representations and cross-model transfer

## Activation similarity

Base and CI remain geometrically close in late layers. Raw final-token states have cosine similarity above 0.99, but raw cosine can be dominated by shared background structure, so the more informative comparison is between matched counterfactual directions.

Representative D-minus-A direction cosine similarities are:

| Layer | Base/CI D-minus-A cosine |
|---|---:|
| 18 | 0.973 |
| 20 | 0.977 |
| 22 | 0.981 |
| 24 | 0.983 |
| 26 | 0.984 |

These values are observational. They show aligned geometry, not behavioral interchangeability by themselves.

## Cross-model patching

Cross-model patching asks the stronger question: can a state produced by one checkpoint still be used by the downstream computation of the other?

### Base to CI

Base-produced recipient and purpose states transfer strongly into CI. On strict length-compatible spans, Base-to-CI patching changes:

- 28/28 recipient A-to-B cases at the best valid recipient-span site,
- 64/65 purpose A-to-C cases,
- 84/85 combined A-to-D span cases.

This indicates that Base already computes semantic states that CI can read and use.

### CI to Base

The reverse direction is different. CI semantic-span states often produce large margin movements inside Base without fully crossing Base's native decision boundary. Once a strong late state has formed, however, Base can use it reliably.

At the final position on the 190 A/D improvement cases, a late CI D state changes 189/190 Base decisions toward No at the latest valid matched block-output site.

## Same-prompt D-to-D transfer

The cleanest checkpoint-difference test keeps the prompt itself fixed. On the same 190 D prompts, only the checkpoint producing the donor state changes.

The effect is modest through earlier layers, then rises sharply around L18. At L26:

- CI-D state into Base-D changes 189/190 Base decisions toward No.
- Base-D state into CI-D changes 188/190 CI decisions toward Yes.

By late layers, the transferred state nearly carries the donor checkpoint's decision with it.

## Interpretation

The two checkpoints do not appear to use disjoint privacy representations. Base states are readable by CI, late states are strongly usable in both directions, and the major checkpoint difference becomes behaviorally important during later integration rather than at the earliest semantic encoding stage.

Saved outputs: `results/clean304/activation_similarity/` and `results/clean304/cross_model_transfer/`.
