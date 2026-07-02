# Repository structure

```text
contextual-integrity-circuit/
  README.md
  requirements.txt

  docs/
    technical_note/
      CI_Privacy_MechInterp_Technical_Note.pdf
      CI_Privacy_MechInterp_Technical_Note.tex

    main_results/
      01_ci_l22_writer_scan.md
      02_ci_l22_direction_ablation_all_levels.md
      03_ci_l18_attention_head_scan.md
      04_ci_l18_to_l22_mediation_all_levels.md
      05_base_l22_remove_rescue_all_levels.md
      06_base_l18_to_l22_remove_rescue_all_levels.md

    appendix_results/
      02_activation_similarity_and_patching.md
      03_component_direction_ablation.md
      04_cross_model_patch.md
      05_mlp_neuron_sufficiency_and_base_overlap.md

    00_project_overview.md
    02_main_story.md
    03_dataset_usage.md
    04_main_vs_appendix.md
    RESULT_SUMMARY.md
    RESULT_INDEX.md
    RESULT_INDEX_EXPANDED.md
    MAIN_RESULTS_CHECKLIST.md
    REPO_AUDIT.md

  data/
    README.md
    raw/
      PrivacyLens/data/main_data.json
    final/
      curated_candidate_pool_source_capped_CLEAN304.csv

  scripts/
    main/
    appendix/
    utils_or_legacy/

  results/
    main/
    appendix_clean304/

  tables/
    main_results_summary.csv
    appendix_results_summary.csv
```

## Main-vs-appendix rule

The main story is built from the six files in `docs/main_results/`. Appendix results support the interpretation but are not be introduced as separate central claims.
