# Figures

This directory contains the saved figure artifacts used to inspect the main model-diffing results. Each figure is provided as both a vector PDF and a PNG preview. The corresponding plotting scripts live in `scripts/figures/` and resolve their default inputs from the reorganized result folders.

| Figure | Plot script | Main source data |
|---|---|---|
| `summary/executive_summary_mechanism.*` | `scripts/figures/plot_executive_summary_mechanism.py` | same-prompt cross-checkpoint transfer plus Base L18/L22 remove-rescue outputs |
| `clean304/within_model_patching_flow.*` | `scripts/figures/plot_within_model_patching_flow.py` | `results/clean304/within_model_patching/` |
| `clean304/activation_similarity_ad.*` | `scripts/figures/plot_activation_similarity_ad.py` | `results/clean304/activation_similarity/ABC_contrast_summary.csv` |
| `clean304/same_prompt_cross_checkpoint_transfer.*` | `scripts/figures/plot_same_prompt_cross_checkpoint_transfer.py` | `results/clean304/cross_model_transfer/DD_same_final_both_summary.csv` |
| `clean304/component_localization.*` | `scripts/figures/plot_component_localization.py` | `results/clean304/component_direction_ablation/component_ablation_summary.csv` |
| `privacylens/ci_l22_writer_dose_response.*` | `scripts/figures/plot_ci_l22_writer_dose_response.py` | `results/privacylens/ci_l22_writer_transfer/*/direction_ablation_summary.csv` |

From the repository root, each figure can be regenerated with a one-line command, for example:

```bash
python scripts/figures/plot_executive_summary_mechanism.py
python scripts/figures/plot_same_prompt_cross_checkpoint_transfer.py
python scripts/figures/plot_ci_l22_writer_dose_response.py
```

The plotting scripts use the current repository paths by default, but still expose command-line arguments where useful for alternate inputs or output locations.
