
# Does Privacy Post-Training Create New Mechanisms or Reuse Old Ones?

This project investigates **what changes inside a language model when post-training improves its privacy decisions**.

I compare two checkpoints with the same `Qwen2.5-7B-Instruct` architecture:

- **Base:** The original instruction-tuned `Qwen2.5-7B-Instruct` model.
- **CI:** The contextual-integrity post-trained checkpoint released with CI-RL.

The models are evaluated on privacy-sensitive decisions involving whether information should be shared with a particular recipient for a particular purpose.

On controlled cases where both the recipient and purpose are inappropriate, accuracy improves from **33.2% in Base to 95.7% in CI**.

This raises the central research question:

**Does post-training create new privacy-related mechanisms, or does it improve how the model uses information and mechanisms that were already present before training?**

To investigate this, I use activation patching, cross-checkpoint activation transfer, representation analysis, attention-head interventions, and MLP-neuron analysis. Rather than examining only whether the models produce different answers, I investigate which internal computations explain those differences.

## Main findings

**The evidence favors reuse of substantially pre-existing privacy-related machinery rather than the creation of an entirely new circuit.**

The experiments support four main findings:

1. **Base already represents useful privacy information.** Causal interventions show that recipient- and purpose-related information can influence decisions even before contextual-integrity post-training.

2. **Post-training changes how this information affects the final decision.** Cross-checkpoint activation transfers reveal a strong transition around layer 18, where privacy-related information becomes substantially more influential for the output decision. Base and CI also preserve highly aligned privacy-related representations, and late internal states remain functionally usable across checkpoints.

3. **A candidate internal pathway can be localized.** A small set of layer-18 attention heads contributes to the transition, followed by a broader late-MLP writer contribution. The identified components include L18 heads H15, H18, H4, H13, and H20, together with a late writer pathway involving L22 neuron N13149.

4. **The machinery is not exclusive to the post-trained model.** Targeted disruption and rescue experiments inside Base demonstrate that important parts of the identified pathway were already functionally available before CI training. Base and CI also share most of their highest-ranked late writer neurons.

Together, these findings suggest that post-training can improve model behaviour by changing how existing representations and computations are recruited and expressed in decisions.

### Interpretation and limitations

This is evidence for a **candidate privacy-decision pathway**, not a complete recovered circuit.

The L18-to-L22 results support downstream propagation rather than formal blocked mediation, and N13149 is a useful localized intervention target rather than a demonstrated unique bottleneck.

The strongest mechanistic conclusions concern the model's **first Yes/No privacy decision**, not its complete generated reasoning. The study also compares one Base/CI checkpoint pair, so generalization across other models and post-training methods remains open.

## Start here

For a quick understanding of the research:

1. **[Project overview](docs/00_project_overview.md)** — Research question, hypotheses, experimental sequence, and main conclusions.
2. **[Summary figure](figures/summary/executive_summary_mechanism.pdf)** — Visual overview of the main mechanistic findings.
3. **[Full research report](docs/report/Does_Privacy_Post_Training_Create_New_Mechanisms_or_Reuse_Old_Ones.pdf)** — Detailed methodology, experimental results, and limitations.

For technical verification:

- [Evidence map](docs/01_evidence_map.md) — Maps research claims to experimental scripts and saved results.
- [Reproducibility guide](docs/02_reproducibility.md) — Explains where each analysis lives and how results are organized.
- [Datasets and splits](docs/03_dataset_and_splits.md) — Documents the evaluation datasets, eligibility rules, and sample counts.
- [Figures](figures/README.md) — Saved figures and their plotting scripts.

## Experimental story

The experiments follow a sequence designed to distinguish whether CI post-training creates new privacy machinery or changes how existing machinery is used.

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

### Controlled discovery and model diffing

```text
results/clean304/within_model_patching/
results/clean304/activation_similarity/
results/clean304/cross_model_transfer/
results/clean304/final_direction_ablation/
results/clean304/component_direction_ablation/
results/clean304/writer_neuron_scan/
```

### PrivacyLens transfer and pre-existing machinery tests

```text
results/privacylens/ci_l22_writer_transfer/
results/privacylens/ci_l18_head_transfer/
results/privacylens/ci_l18_to_l22_propagation/
results/privacylens/base_l22_remove_rescue/
results/privacylens/base_l18_remove_rescue/
results/privacylens/same_prompt_correction_analysis.csv
```

### Supporting analyses

Supporting CLEAN304 robustness and writer-overlap analyses are kept under:

```text
results/clean304/supporting/
```

## Reproducibility

The repository includes:

- Final input CSVs and evaluation datasets.
- Experimental scripts for causal interventions and model comparisons.
- Saved result tables and detailed experimental outputs.
- PDF/PNG figures and the scripts used to generate them.
- Documentation connecting each reported claim to the corresponding experiment and saved result.

Large model checkpoints are not redistributed.

### Discovery and validation

The main controlled dataset is **CLEAN304**, which is used for mechanistic discovery and model-diffing analyses.

**PrivacyLens** is used as an out-of-discovery transfer distribution to investigate whether previously identified components remain behaviorally relevant beyond the controlled templates.

Writer rankings and the L18 attention-head ranking are fixed before the PrivacyLens validation tests.

This distinction is important: the components evaluated on PrivacyLens are not re-selected from that dataset.

For the exact script-to-result mapping, see the [reproducibility guide](docs/02_reproducibility.md).

For the correspondence between individual research claims and their supporting experiments, see the [evidence map](docs/01_evidence_map.md).

## Scope

This work supports a **candidate privacy-decision pathway**, not an exhaustive explanation of contextual privacy reasoning.

Several limitations remain:

- Whole-state activation patching can change multiple latent variables simultaneously.
- Some interventions use relatively large strengths and should be interpreted as controllability tests rather than naturalistic perturbations.
- The L18-to-L22 analysis demonstrates downstream propagation but not formal blocked mediation.
- The identified L22 writer neuron is not established as a unique or necessary bottleneck.
- Generated rationales are evaluated only qualitatively.
- The study focuses on the first Yes/No privacy decision rather than complete natural-language responses.
- The experiments compare one Base/CI model pair, so broader generalization remains untested.

Within these boundaries, the results provide causal evidence that **privacy-related computations already available in a base language model can be recruited differently after post-training**, offering a mechanistic account of improved privacy-decision behaviour.
