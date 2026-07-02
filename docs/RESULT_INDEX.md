# Result index

## Main scripts

```text
scripts/main/
  mlp_neuron_writer_scan.py
  privacylens_direction_ablation_generation.py
  privacylens_attention_head_writer_scan_ablation.py
  privacylens_l18_heads_to_l22_mlp_mediation_with_generation.py
  base_privacylens_direction_remove_rescue.py
  base_privacylens_l18_to_l22_rescue_mediation_with_generation.py
```

## Main results

| Folder | Purpose |
|---|---|
| `results/main/ci_l22_writer_scan/` | CI MLP writer-neuron discovery. Identifies L22 N13149 and related writer neurons. |
| `results/main/ci_l22_direction_ablation/` | All-four-level PrivacyLens L22 direction ablation/generation. |
| `results/main/ci_l18_attention_head_scan/` | L18 attention-head scan; discovers H15, H18, H4, H13, H20. |
| `results/main/ci_l18_to_l22_mediation/` | All-four-level CI mediation: L18 top heads shift L22 N13149 and Yes/No margin. |
| `results/main/base_l22_remove_rescue/` | All-four-level base L22 remove/rescue. |
| `results/main/base_l18_to_l22_remove_rescue/` | All-four-level base L18 remove/rescue mediation. |

## Appendix clean304 results

| Folder | Purpose |
|---|---|
| `results/appendix_clean304/activation_similarity/` | Base-CI activation/counterfactual direction similarity. |
| `results/appendix_clean304/final_direction_ablation/` | Broad final-token D-vs-A direction ablation. |
| `results/appendix_clean304/final_direction_controls/` | Signed controls for final direction. |
| `results/appendix_clean304/component_direction_ablation/` | Coarse localization to L18 attention and late MLP/residual. |
| `results/appendix_clean304/within_model_patching/` | Older within-model A/B/C/D patching. |
| `results/appendix_clean304/cross_model_patch/` | Base↔CI cross-model patching and D-final swap. |
| `results/appendix_clean304/mlp_neuron_writer_robustness/` | Seed1, zero-check, and base writer-overlap variants. |
| `results/appendix_clean304/mlp_neuron_sufficiency/` | Writer-neuron sufficiency variants. |
| `results/appendix_clean304/old_base_neuron_rescue/` | Older base rescue variants. |
| `results/appendix_clean304/base_top_vs_ci_top_neuron_overlap/` | Base-vs-CI top neuron overlap and steering. |

## Preserved/non-final material

| Folder | Purpose |
|---|---|
| `` | Exploratory and pilot results/scripts preserved. |
| `scripts/utils_or_legacy/` | Helpers and older scripts. |
