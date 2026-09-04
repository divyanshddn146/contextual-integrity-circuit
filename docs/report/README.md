# Current report

The current report is:

`Does_Privacy_Post_Training_Create_New_Mechanisms_or_Reuse_Old_Ones.pdf`

The repository was reorganized after this PDF was exported so that the code and results follow the report's current model-diffing story rather than the earlier `main` versus `appendix` split.

The script basenames listed in Appendix P map to the current repository as follows:

| Report basename | Current path |
|---|---|
| `run_behavior.py` | `scripts/clean304/run_behavior.py` |
| `mine_ci_improvement_cases.py` | `scripts/clean304/mine_ci_improvement_cases.py` |
| `run_patching.py` | `scripts/clean304/run_patching.py` |
| `activation_similarity.py` | `scripts/clean304/activation_similarity.py` |
| `cross_model_patch.py` | `scripts/clean304/cross_model_patching.py` |
| `cross_model_DD_final_both.py` | `scripts/clean304/same_prompt_cross_model_transfer.py` |
| `component_direction_ablation.py` | `scripts/clean304/component_direction_ablation.py` |
| `mlp_neuron_writer_scan.py` | `scripts/clean304/mlp_neuron_writer_scan.py` |
| `privacylens_direction_ablation_generation.py` | `scripts/privacylens/privacylens_direction_ablation_generation.py` |
| `privacylens_attention_head_writer_scan_ablation.py` | `scripts/privacylens/privacylens_attention_head_writer_scan_ablation.py` |
| `privacylens_l18_heads_to_l22_mlp_mediation_with_generation.py` | `scripts/privacylens/privacylens_l18_heads_to_l22_propagation_with_generation.py` |
| `base_privacylens_direction_remove_rescue.py` | `scripts/privacylens/base_privacylens_direction_remove_rescue.py` |
| `base_privacylens_l18_to_l22_rescue_mediation_with_generation.py` | `scripts/privacylens/base_privacylens_l18_to_l22_remove_rescue_with_generation.py` |

The two L18-to-L22 filenames were deliberately changed from `mediation` to `propagation` so that the repository terminology matches the report's actual claim. These experiments track a downstream response to an upstream intervention, but do not clamp L22 and therefore do not establish formal blocked mediation.

For the current path-to-result map, use `docs/01_evidence_map.md` and `docs/02_reproducibility.md` rather than the older directory labels in Appendix P.
