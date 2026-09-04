# Evidence map

This page maps the current report story directly to the saved code and results.

| Report question | Main analysis | Script | Saved results |
|---|---|---|---|
| How large is the CI behavioral improvement? | Controlled A/B/C/D behavior and eligibility | `scripts/clean304/run_behavior.py`, `scripts/clean304/mine_ci_improvement_cases.py` | `data/final/*eligibility*.csv` |
| Is recipient/purpose information already usable in Base? | Within-model patching | `scripts/clean304/run_patching.py` | `results/clean304/within_model_patching/` |
| Are Base and CI representations geometrically aligned? | Raw-state and contrast-direction similarity | `scripts/clean304/activation_similarity.py` | `results/clean304/activation_similarity/` |
| Can internal states be used across checkpoints? | Base-to-CI, CI-to-Base, and same-prompt state transfer | `scripts/clean304/cross_model_patching.py`, `scripts/clean304/same_prompt_cross_model_transfer.py` | `results/clean304/cross_model_transfer/` |
| Where does privacy information become strongly decision-relevant? | Final D-minus-A direction intervention and signed controls | `scripts/clean304/final_direction_controls.py` | `results/clean304/final_direction_ablation/`, `results/clean304/final_direction_controls/` |
| Which module is concentrated around the L18 transition? | Residual, attention, and MLP component intervention | `scripts/clean304/component_direction_ablation.py` | `results/clean304/component_direction_ablation/` |
| Which late writers provide localized handles? | MLP writer-neuron ranking and held-out intervention | `scripts/clean304/mlp_neuron_writer_scan.py` | `results/clean304/writer_neuron_scan/` |
| Do the late writers have sufficiency under stronger interventions? | Replacement and additive writer interventions | `scripts/clean304/mlp_neuron_sufficiency_steer.py` | `results/clean304/supporting/writer_sufficiency/` |
| Does the L22 writer mechanism transfer to PrivacyLens? | Fixed CLEAN304-derived writer transfer across prompt levels | `scripts/privacylens/privacylens_direction_ablation_generation.py` | `results/privacylens/ci_l22_writer_transfer/` |
| Which L18 heads matter on PrivacyLens? | CLEAN304-ranked head intervention | `scripts/privacylens/privacylens_attention_head_writer_scan_ablation.py` | `results/privacylens/ci_l18_head_transfer/` |
| Does changing L18 propagate to the downstream L22 writer state? | L18 intervention plus N13149 tracking | `scripts/privacylens/privacylens_l18_heads_to_l22_propagation_with_generation.py` | `results/privacylens/ci_l18_to_l22_propagation/` |
| Was the L22 machinery already active in Base? | Base L22 remove/rescue | `scripts/privacylens/base_privacylens_direction_remove_rescue.py` | `results/privacylens/base_l22_remove_rescue/` |
| Was the upstream L18 machinery already active in Base? | Base L18 remove/rescue plus downstream N13149 tracking | `scripts/privacylens/base_privacylens_l18_to_l22_remove_rescue_with_generation.py` | `results/privacylens/base_l18_remove_rescue/` |
| Do Base and CI use overlapping late writer coordinates? | Independent writer ranking and CI-derived writer changes in Base | `scripts/clean304/writer_overlap_and_cross_checkpoint_reuse.py` and related robustness scripts | `results/clean304/supporting/cross_checkpoint_writer_reuse/`, `results/clean304/supporting/writer_robustness/` |
| What differs on identical PrivacyLens correction cases? | Paired Base-Yes/CI-No descriptive analysis | `scripts/privacylens/build_same_prompt_correction_analysis.py` | `results/privacylens/same_prompt_correction_analysis.csv`, reconstructed from the saved Base and CI PrivacyLens outputs |

## Reading order

If you want to inspect the evidence in the same order as the report, read:

1. `docs/results/01_behavior_and_information_availability.md`
2. `docs/results/02_shared_representations_and_cross_model_transfer.md`
3. `docs/results/03_decision_transition_and_component_localization.md`
4. `docs/results/04_writer_pathway_and_heldout_validation.md`
5. `docs/results/05_privacylens_transfer.md`
6. `docs/results/06_base_remove_rescue_preexisting_machinery.md`
7. `docs/results/07_writer_overlap_and_cross_checkpoint_rescue.md`
8. `docs/results/08_same_prompt_correction_analysis.md`

## Figure artifacts

The saved figures are under `figures/`, with plotting code under `scripts/figures/`.

| Evidence | Saved figure | Plot script |
|---|---|---|
| Base already carries useful contextual information | `figures/clean304/within_model_patching_flow.pdf` | `scripts/figures/plot_within_model_patching_flow.py` |
| Base/CI privacy contrast remains aligned | `figures/clean304/activation_similarity_ad.pdf` | `scripts/figures/plot_activation_similarity_ad.py` |
| Same-prompt late states transfer across checkpoints | `figures/clean304/same_prompt_cross_checkpoint_transfer.pdf` | `scripts/figures/plot_same_prompt_cross_checkpoint_transfer.py` |
| Sharp L18 attention effect plus broader late MLP contribution | `figures/clean304/component_localization.pdf` | `scripts/figures/plot_component_localization.py` |
| Fixed L22 writers transfer to PrivacyLens with a clear dose response | `figures/privacylens/ci_l22_writer_dose_response.pdf` | `scripts/figures/plot_ci_l22_writer_dose_response.py` |
| Executive synthesis of late state transfer and Base remove/rescue | `figures/summary/executive_summary_mechanism.pdf` | `scripts/figures/plot_executive_summary_mechanism.py` |
