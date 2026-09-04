# Does Privacy Post-Training Create New Mechanisms or Reuse Old Ones?

This repository contains a mechanistic model-diffing study of two checkpoints with the same `Qwen2.5-7B-Instruct` architecture:

- **Base:** `Qwen2.5-7B-Instruct`
- **CI:** the contextual-integrity post-trained checkpoint released with CI-RL

The project starts from a simple question. CI post-training makes the model much more reliable at contextual privacy decisions, but **what changed internally?** Did training create new privacy machinery, or did it change how machinery already present in Base is recruited and expressed?

## Main conclusion

The evidence favors **reuse of substantially pre-existing machinery**.

Base already contains usable recipient- and purpose-related information. Base and CI preserve highly aligned privacy-related representations, and late states are functionally readable across checkpoints. The important difference appears later in the computation, around layer 18, where the privacy distinction becomes strongly decision-relevant. In CI this transition can be localized to a small set of L18 attention heads followed by a broader late-MLP writer pathway, including L22 neuron N13149.

The strongest test is then performed back inside Base. The same L18 and L22 machinery can be disrupted and rescued by targeted intervention, and Base and CI share most of their highest-ranked late writer neurons. This makes an entirely new-circuit explanation substantially less plausible.

The claim is intentionally narrower than a complete privacy circuit. The mechanistic results concern the **first Yes/No privacy decision**. The L18-to-L22 evidence is downstream propagation, not formal blocked mediation, and N13149 is a strong localized handle rather than a unique bottleneck.

## Start here

The current full report is:

[`docs/report/Does_Privacy_Post_Training_Create_New_Mechanisms_or_Reuse_Old_Ones.pdf`](docs/report/Does_Privacy_Post_Training_Create_New_Mechanisms_or_Reuse_Old_Ones.pdf)

For a fast repository-level view:

1. [`docs/00_project_overview.md`](docs/00_project_overview.md), the research question and experimental sequence.
2. [`docs/01_evidence_map.md`](docs/01_evidence_map.md), claim-to-script-to-result mapping.
3. [`docs/02_reproducibility.md`](docs/02_reproducibility.md), where each analysis lives.
4. [`docs/03_dataset_and_splits.md`](docs/03_dataset_and_splits.md), datasets, eligibility rules, and sample counts.
5. [`figures/README.md`](figures/README.md), saved figures and their plotting scripts.

## Experimental story

The repository now follows the order of the current report rather than the earlier CI-circuit-first organization.

| Stage | Question | Main evidence |
|---|---|---|
| 1 | How large is the behavioral change? | On controlled D cases, accuracy rises from **33.2% in Base to 95.7% in CI**. |
| 2 | Did Base simply lack the needed contextual information? | Within-model patching shows recipient- and purpose-related states in Base already move the decision margin strongly. |
| 3 | Are the checkpoints using incompatible representations? | Privacy-related directions remain closely aligned, and Base-produced semantic states can be used by CI. |
| 4 | Where does the checkpoint difference become decision-relevant? | Same-prompt cross-checkpoint transfer becomes sharply effective around **L18** and nearly exchanges late decisions. |
| 5 | What computation is concentrated near that transition? | L18 attention has a sharp intervention effect, while late MLP writing is broader across roughly L18 to L22. |
| 6 | Can the pathway be localized further? | L18 heads H15, H18, H4, H13, H20 and the late writer set, especially **L22 N13149**, provide strong localized handles. |
| 7 | Does the mechanism transfer beyond controlled templates? | Fixed CLEAN304-derived L18/L22 components remain behaviorally active on all four PrivacyLens prompt levels. |
| 8 | Was this machinery already active before CI tuning? | Targeted L18/L22 remove and rescue interventions work directly inside Base, far above matched random controls. |
| 9 | What remains different between checkpoints? | Same-prompt correction cases show a pronounced downstream difference at N13149, but do not isolate whether the origin is upstream routing, downstream calibration, or both. The 27 matched rows are exported directly in `results/privacylens/same_prompt_correction_analysis.csv`. |

## Repository structure

```text
contextual-integrity-circuit/
  README.md
  requirements.txt

  docs/
    report/                     # current full report
    results/                    # result notes in report order
    appendix/                   # controls and robustness notes
    00_project_overview.md
    01_evidence_map.md
    02_reproducibility.md
    03_dataset_and_splits.md

  data/
    raw/PrivacyLens/
    final/

  scripts/
    clean304/                   # controlled discovery and model-diffing analyses
    privacylens/                # transfer, propagation, and Base tests
    figures/                    # plotting scripts for saved figures

  figures/
    summary/                    # executive-summary synthesis figure
    clean304/                   # controlled/model-diffing figures
    privacylens/                # transfer figures

  results/
    clean304/                   # controlled discovery/model-diffing outputs
    privacylens/                # out-of-discovery PrivacyLens outputs

  tables/
    clean304/
    privacylens/
    table_index.csv
```

## Key result folders

Controlled discovery and model diffing:

```text
results/clean304/within_model_patching/
results/clean304/activation_similarity/
results/clean304/cross_model_transfer/
results/clean304/final_direction_ablation/
results/clean304/component_direction_ablation/
results/clean304/writer_neuron_scan/
```

PrivacyLens transfer and the pre-existing-machinery test:

```text
results/privacylens/ci_l22_writer_transfer/
results/privacylens/ci_l18_head_transfer/
results/privacylens/ci_l18_to_l22_propagation/
results/privacylens/base_l22_remove_rescue/
results/privacylens/base_l18_remove_rescue/
results/privacylens/same_prompt_correction_analysis.csv
```

Supporting CLEAN304 robustness and writer-overlap analyses are kept under:

```text
results/clean304/supporting/
```

## Reproducibility

The repository includes the final input CSVs, saved result tables, detailed run outputs, saved PDF/PNG figures, and the scripts used for the reported analyses and plots. Large model checkpoints are not redistributed.

The main controlled dataset is CLEAN304. PrivacyLens is used as an out-of-discovery transfer distribution. Writer rankings and the L18 head ranking are fixed before the PrivacyLens validation tests.

See [`docs/02_reproducibility.md`](docs/02_reproducibility.md) for the exact script and result mapping.

## Scope

This work supports a **candidate privacy-decision pathway**, not an exhaustive explanation of contextual privacy reasoning. Whole-state patching can move many latent variables at once, some interventions use large strengths, and generated rationales are evaluated only qualitatively. The strongest conclusions are about intervention-based control of the first Yes/No decision.
