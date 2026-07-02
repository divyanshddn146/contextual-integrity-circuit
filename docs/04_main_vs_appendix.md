# Main vs appendix placement

## Main text

Use these as the main causal story:

1. CI L22 MLP writer-neuron scan.
2. CI L22 direction ablation/generation across all PrivacyLens levels.
3. CI L18 attention-head scan.
4. CI L18→L22 mediation across all PrivacyLens levels.
5. Base L22 remove/rescue across all PrivacyLens levels.
6. Base L18→L22 remove/rescue across all PrivacyLens levels.

## Mention briefly in main, detailed in appendix

These are strong but should not become full main sections:

- Cross-model D-final patching: CI D→base D rescues 189/190; base D→CI D destroys 188/190.
- Component direction ablation: L18 attention and L20–L22/L27 MLP components are causally strong.
- Base/CI top writer-neuron overlap: L22 top100 overlap is 92/100.

## Appendix

Place full details for:

- Activation similarity.
- Final-direction ablation and controls.
- Within-model A/B/C/D patching.
- Cross-model patching.
- Component direction ablation.
- MLP neuron sufficiency / add-delta controls.
- Base-top vs CI-top writer-neuron overlap.
- Older base rescue variants.
- A-baseline PrivacyLens level ablation.

## Legacy / preserved notes

Scratch notes are not included in the public repo. The cleaned documentation in `docs/main_results/` and `docs/appendix_results/` should be used as the source of truth.
