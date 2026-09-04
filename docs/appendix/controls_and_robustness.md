# Controls and robustness notes

This page collects the main interpretation safeguards used across the report.

## Random directions and random components

- Final-direction interventions use matched random directions. Their decision-change rate is about 0.7 to 1.4 percent, far below the discovery-derived D-minus-A direction after L18.
- Component-level random controls peak at 3/95 for attention, 8/95 for MLP, and 2/95 for the residual stream.
- PrivacyLens L22 writer-transfer random-neuron controls produce 0/1937 decision changes in the reported all-level comparison.
- PrivacyLens L18 top-five random controls produce 2/1937 changes across all four levels.
- Base L22 random remove/rescue controls produce 0/1910 and 0/62 changes.
- Base L18 random remove/rescue controls produce 1/1910 and 2/62 changes.

## Direction sign controls

Removing D-minus-A contribution from D states moves the model toward Yes, while adding the same displacement to A states moves the model toward No. Removing only positively D-aligned contribution from A has essentially no effect across the tested late layers and strengths. This makes a generic large-perturbation explanation less plausible.

## Discovery-split robustness

A second discovery split again ranks L22 N13149 first with a writer score of roughly 8.16.

## Strong-intervention caveat

Some transfer and sufficiency results use large alpha values. The report therefore distinguishes:

- non-ceiling results that are more informative about specificity, such as PrivacyLens L22 top-100 at alpha=4, and
- stronger controllability demonstrations, such as alpha=6 ceiling behavior or alpha=3 additive writer sufficiency.

The strong runs show that the identified coordinates can control the decision when pushed, not that natural processing applies an equivalent displacement.

## L18-to-L22 language

Changing L18 heads moves downstream N13149 and also moves the final decision. The correlation between the two changes is high. Because the L18 effect has not been blocked by clamping N13149 to its native value, the result is called **downstream propagation/pathway validation**, not formal mediation.

## Rationale generation

Generation examples are qualitative sanity checks only. The quantitative mechanistic claims remain scoped to the first Yes/No decision.
