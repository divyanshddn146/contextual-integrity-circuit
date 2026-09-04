# Reproducibility map

## Repository convention

```text
data/       input datasets and curated prompt pools
scripts/    experiment code
results/    saved experiment outputs
tables/     compact summary tables
docs/       report and human-readable evidence map
```

The previous repository separated `main` and `appendix` analyses. That split no longer matches the current model-diffing story, so the repository is now organized by **controlled CLEAN304 discovery/model diffing** versus **PrivacyLens transfer/validation**.

## Controlled CLEAN304 analyses

Run these from the repository root.

```text
scripts/clean304/ci_dataset.py
scripts/clean304/run_behavior.py
scripts/clean304/mine_ci_improvement_cases.py
scripts/clean304/run_patching.py
scripts/clean304/activation_similarity.py
scripts/clean304/cross_model_patching.py
scripts/clean304/same_prompt_cross_model_transfer.py
scripts/clean304/final_direction_controls.py
scripts/clean304/component_direction_ablation.py
scripts/clean304/mlp_neuron_writer_scan.py
scripts/clean304/mlp_neuron_sufficiency_steer.py
scripts/clean304/writer_overlap_and_cross_checkpoint_reuse.py
```

`run_behavior.py`, `mine_ci_improvement_cases.py`, and `run_patching.py` use `ci_dataset.py` as a local helper. The writer and component analyses also use the same CLEAN304 construction.

Primary outputs:

```text
results/clean304/within_model_patching/
results/clean304/activation_similarity/
results/clean304/cross_model_transfer/
results/clean304/final_direction_ablation/
results/clean304/final_direction_controls/
results/clean304/component_direction_ablation/
results/clean304/writer_neuron_scan/
results/clean304/supporting/
```

## PrivacyLens transfer and Base tests

```text
scripts/privacylens/privacylens_direction_ablation_generation.py
scripts/privacylens/privacylens_attention_head_writer_scan_ablation.py
scripts/privacylens/privacylens_l18_heads_to_l22_propagation_with_generation.py
scripts/privacylens/base_privacylens_direction_remove_rescue.py
scripts/privacylens/base_privacylens_l18_to_l22_remove_rescue_with_generation.py
scripts/privacylens/ablate_privacylens_levels_A_baseline.py
scripts/privacylens/build_same_prompt_correction_analysis.py
```

These scripts share helper functions from `privacylens_direction_ablation_generation.py`, so they are intentionally kept in one directory.

Primary outputs:

```text
results/privacylens/ci_l22_writer_transfer/
results/privacylens/ci_l18_head_transfer/
results/privacylens/ci_l18_to_l22_propagation/
results/privacylens/base_l22_remove_rescue/
results/privacylens/base_l18_remove_rescue/
```

## Discovery versus validation

The distinction matters for the interpretation of transfer results.

- CLEAN304 is used to construct the controlled counterfactuals and to discover the D-minus-A direction, writer ranking, and L18 head ranking.
- The main PrivacyLens transfer experiments keep those components fixed rather than re-selecting them on PrivacyLens.
- The L18 head ranking is computed from the 304 CLEAN304 A/D pairs. The 478 native-No PrivacyLens trajectory prompts are the evaluation set for the headline top-k head intervention.
- The all-level PrivacyLens experiments then reuse the fixed head set across seed, vignette, trajectory, and trajectory-enhancing prompts.

## Same-prompt correction analysis

The 27 Base-Yes/CI-No correction cases are a descriptive analysis, not a new intervention. `scripts/privacylens/build_same_prompt_correction_analysis.py` reconstructs them from the already saved Base and CI PrivacyLens evaluation outputs by matching `case_index` within each prompt level and checking that the prompt text agrees across checkpoints. It writes the reviewer-friendly row-level export to `results/privacylens/same_prompt_correction_analysis.csv` and the report-level summary to `tables/privacylens/same_prompt_correction_summary.csv`.

## Summary tables

Small reviewer-friendly summaries are under:

```text
tables/clean304/
tables/privacylens/
```

The detailed row-level outputs remain under `results/`.


## Figure regeneration

Saved PDF and PNG figures live under `figures/`. The plotting scripts are separated from the experiment scripts so it is clear that they only read saved result CSVs and render figures. From the repository root:

```bash
python scripts/figures/plot_within_model_patching_flow.py
python scripts/figures/plot_activation_similarity_ad.py
python scripts/figures/plot_same_prompt_cross_checkpoint_transfer.py
python scripts/figures/plot_component_localization.py
python scripts/figures/plot_ci_l22_writer_dose_response.py
python scripts/figures/plot_executive_summary_mechanism.py
```

Each command has defaults pointing to the current reorganized result folders. See `figures/README.md` for the exact figure-to-input mapping.

## Models

The repository does not redistribute model checkpoints. The analyses compare the released Qwen2.5-7B-Instruct checkpoint with the contextual-integrity-tuned derivative used in the CI-RL work. Architecture and tokenizer are therefore held fixed across the model-diffing comparison.
