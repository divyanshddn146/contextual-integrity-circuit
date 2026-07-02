# Mechanistic Analysis of Contextual-Integrity Privacy Decisions

This repository contains a mechanistic pilot study of contextual-integrity privacy decisions in `Qwen2.5-7B-Instruct` and a contextual-integrity-tuned variant. The project asks what changes inside the model after CI tuning: does the tuned model learn a new privacy mechanism from scratch, or does it make better use of machinery already present in the base model?

The main evidence points to a candidate pathway:

```text
L18 attention heads  →  L22 MLP writer-neuron pathway  →  final Yes/No privacy decision
```

## Central claim

CI tuning does not appear to create an entirely new privacy circuit. Instead, the base model already contains a compatible L18 attention → L22 MLP privacy-decision pathway, and CI tuning makes privacy-sensitive prompts activate this pathway more reliably.

## Start here

For a concise overview, read the 3-page technical note:

```text
docs/technical_note/CI_Privacy_MechInterp_Technical_Note.pdf
```

For the project map and result details, read:

```text
docs/00_project_overview.md
docs/02_main_story.md
docs/RESULT_SUMMARY.md
docs/RESULT_INDEX.md
docs/MAIN_RESULTS_CHECKLIST.md
```

Detailed result notes are organized as:

```text
docs/main_results/
docs/appendix_results/
```

## Headline results

- **CI L22 direction ablation:** ablating the CI-discovered L22 writer-neuron contribution flips **1937/1937** normal-No PrivacyLens cases to Yes across all four prompt levels at α=6; random-neuron controls flip **0**.
- **CI L18→L22 mediation:** patching the top L18 attention heads shifts L22 neuron 13149 toward the allowed state across all four PrivacyLens levels, with strong correlations between L22 activation shift and Yes/No margin shift.
- **Base L22 remove/rescue:** removing the L22 refusal contribution flips **1910/1910** base-model refusals to Yes; adding a CI-like L22 contribution rescues **56/62** base Yes failures into No.
- **Base L18→L22 remove/rescue:** patching L18 heads toward the allowed state flips **453/1910** base refusals to Yes; patching them toward the refusal state rescues **31/62** base Yes failures to No.

## Repository structure

```text
contextual-integrity-circuit/
  README.md
  requirements.txt

  docs/
    technical_note/
    main_results/
    appendix_results/
    RESULT_SUMMARY.md
    RESULT_INDEX.md
    MAIN_RESULTS_CHECKLIST.md

  data/
    raw/
    final/

  scripts/
    main/
    appendix/
    utils_or_legacy/

  results/
    main/
    appendix_clean304/

  tables/
    README.md
    table_index.csv
    main/
    appendix/
```

## Main result folders

```text
results/main/
  ci_l22_writer_scan/
  ci_l22_direction_ablation/
  ci_l18_attention_head_scan/
  ci_l18_to_l22_mediation/
  base_l22_remove_rescue/
  base_l18_to_l22_remove_rescue/
```

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

## Summary tables

Compact, human-readable tables used by the README and technical note are under:

```text
tables/main/
tables/appendix/
```

These are summary tables only. Full raw run outputs remain under `results/`.

## Dataset note

Input datasets belong under `data/`, not under `results/`. Main all-level PrivacyLens experiments use four prompt levels: `seed`, `vignette`, `trajectory`, and `trajectory_enhancing`. Several appendix experiments use clean304-derived A/D or A/B/C/D subsets. See `data/README.md`, `docs/03_dataset_usage.md`, and `docs/RESULT_SUMMARY.md` for exact counts.

The cleaned package includes result outputs and documentation. Add the raw PrivacyLens file and curated clean304 CSV under `data/` if redistribution is allowed.

## Caveat

The final Yes/No decision is easier to localize than the full generated rationale. The current result should be read as evidence for a candidate decision pathway, not as a complete explanation of all privacy reasoning or generated explanations.


## Data audit

The cleaned repo includes only the final input data needed for the reported analyses. See `docs/DATA_CSV_AUDIT.md` for a file-by-file decision on older CSVs.
