# Results

Saved outputs are grouped by evaluation role rather than by an old main/appendix distinction.

## `clean304/`

Controlled mechanism discovery and checkpoint comparison:

```text
within_model_patching/
activation_similarity/
cross_model_transfer/
final_direction_ablation/
final_direction_controls/
component_direction_ablation/
writer_neuron_scan/
supporting/
```

`supporting/` contains writer-sufficiency, split robustness, writer-overlap, and earlier cross-checkpoint writer-rescue variants that support the main model-diffing conclusion without needing to sit in the primary path.

## `privacylens/`

Out-of-discovery transfer and direct tests inside Base:

```text
ci_l22_writer_transfer/
ci_l18_head_transfer/
ci_l18_to_l22_propagation/
base_l22_remove_rescue/
base_l18_remove_rescue/
```

The `ci_l18_to_l22_propagation/` name is deliberate. These experiments show that changing the L18 head state moves the downstream L22 writer state and the decision, but they do not include a blocking experiment that would justify a formal mediation claim.
