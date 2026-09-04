# Scripts

Scripts are grouped by the role they play in the current report.

## `clean304/`

Controlled discovery and Base/CI model-diffing analyses:

```text
ci_dataset.py
run_behavior.py
mine_ci_improvement_cases.py
run_patching.py
activation_similarity.py
cross_model_patching.py
same_prompt_cross_model_transfer.py
final_direction_controls.py
component_direction_ablation.py
mlp_neuron_writer_scan.py
mlp_neuron_sufficiency_steer.py
writer_overlap_and_cross_checkpoint_reuse.py
cross_checkpoint_writer_replacement.py
cross_checkpoint_writer_additive.py
```

The earlier `main/`, `appendix/`, and `utils_or_legacy/` split was removed because it no longer matched the current report. Several analyses that used to be labelled appendix are central to the new model-diffing story.

## `privacylens/`

Out-of-discovery transfer and the direct Base tests:

```text
privacylens_direction_ablation_generation.py
privacylens_attention_head_writer_scan_ablation.py
privacylens_l18_heads_to_l22_propagation_with_generation.py
base_privacylens_direction_remove_rescue.py
base_privacylens_l18_to_l22_remove_rescue_with_generation.py
ablate_privacylens_levels_A_baseline.py
build_same_prompt_correction_analysis.py
```

These files are intentionally kept together because several scripts import helper functions from `privacylens_direction_ablation_generation.py`.

## `figures/`

Plotting scripts for the saved reviewer-facing figures:

```text
plot_executive_summary_mechanism.py
plot_within_model_patching_flow.py
plot_activation_similarity_ad.py
plot_same_prompt_cross_checkpoint_transfer.py
plot_component_localization.py
plot_ci_l22_writer_dose_response.py
```

These scripts use the reorganized `results/` paths by default and write to `figures/`. See `figures/README.md` for the figure-to-data mapping.

Run scripts from the repository root. Exact dataset/result mapping is documented in `docs/01_evidence_map.md` and `docs/02_reproducibility.md`.
