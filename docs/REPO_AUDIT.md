# Repository audit

This audit describes the public, GitHub-ready package. The repo is organized around one main story: a candidate L18 attention → L22 MLP pathway for contextual-integrity privacy decisions.

## Required main-result file checks

| Result group | Status |
|---|---|
| CI L22 writer-neuron scan | Present |
| CI L22 direction ablation: seed/vignette/trajectory/trajectory_enhancing | Present |
| CI L18 attention-head scan | Present |
| CI L18→L22 mediation: all four levels | Present |
| Base L22 remove/rescue: all four levels | Present |
| Base L18→L22 remove/rescue: remove and rescue for all four levels | Present |
| 3-page technical note PDF and LaTeX source | Present |

## Public cleanup decisions

The public package intentionally omits raw scratch notes, nested duplicate repos, old documentation copies, legacy source-capped dumps, and duplicate-preserved folders. The cleaned docs in `docs/main_results/` and `docs/appendix_results/` are the intended source of truth.

## Main folders to use

```text
results/main/
scripts/main/
docs/main_results/
tables/main/table_1_ci_l22_direction_ablation_all_levels.csv and related `tables/main/` files
```

## Appendix folders to use

```text
results/appendix_clean304/

scripts/appendix/
docs/appendix_results/
tables/appendix/ appendix summary tables
```

## First files to read

```text
README.md
docs/technical_note/CI_Privacy_MechInterp_Technical_Note.pdf
docs/00_project_overview.md
docs/02_main_story.md
docs/RESULT_SUMMARY.md
```
