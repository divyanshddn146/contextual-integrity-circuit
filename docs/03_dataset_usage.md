# Dataset usage and prompt counts

## Data vs results convention

Input files should be placed under `data/`:

```text
data/data/raw/PrivacyLens/data/main_data.json
data/final/curated_candidate_pool_source_capped_CLEAN304.csv
```

Experiment outputs should be placed under `results/`:

```text
results/main/
results/appendix_clean304/
```

Do not put scripts, scratch notes, or raw input datasets inside `results/`.

## PrivacyLens all-level experiments

The all-level PrivacyLens experiments use the official PrivacyLens cases from:

```text
data/data/raw/PrivacyLens/data/main_data.json
```

with four prompt levels:

```text
seed
vignette
trajectory
trajectory_enhancing
```

Each level has 493 prompts.

These all-level experiments use simplified Yes/No scoring prompts, not the full ToolEmu/procoder agent-action benchmark.

## Clean304-derived AD experiments

Several appendix and writer-neuron experiments use a clean304-derived A/D subset:

| Subset | Count |
|---|---:|
| AD eligible total | 190 |
| Train | 95 |
| Test | 95 |

Use this wording:

> The MLP writer-neuron scan and several appendix direction-control experiments use the clean304-derived AD-eligible subset: 190 A/D scenarios split into 95 train and 95 held-out test cases.

Do not say these use all 304 prompts.

## Clean304 contrast subsets

For broader patching/activation similarity analyses, the source pool is clean304, but contrast-specific eligibility reduces counts:

| Contrast | Meaning | Count |
|---|---|---:|
| AB | Recipient violation | 49 |
| AC | Purpose violation | 87 |
| AD | Both/final violation | 190 |
| Strict recipient span | Recipient span | 28 |
| Strict purpose span | Purpose span | 65 |
| Strict both span | Both span | 85 |

Correct wording:

> These appendix experiments are based on the clean304 scenario pool. Raw activation similarity uses all 304 scenarios, while contrast/patching experiments use clean304-derived eligible subsets: 49 AB, 87 AC, 190 AD, and strict-span subsets of 28/65/85.
