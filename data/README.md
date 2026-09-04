# Data

This folder contains the input data needed for the reported controlled and transfer analyses.

## Controlled data

`data/final/curated_candidate_pool_source_capped_CLEAN304.csv` is the curated 304-scenario pool used for the controlled A/B/C/D model-diffing analyses.

`data/final/source_capped_CLEAN304_improvement_eligibility.csv` stores the corresponding Base/CI behavior, margins, eligibility flags, and patching metadata.

The repository also retains the broader 391-case source-capped patching pool and its eligibility file because some full patching and similarity sweeps were run on that pool before the final report-specific contrast filters were applied.

## PrivacyLens

`data/raw/PrivacyLens/data/main_data.json` is the PrivacyLens source used to construct the four transfer prompt levels:

```text
seed
vignette
trajectory
trajectory_enhancing
```

Each level contains 493 scenarios before filtering by the model's native Yes/No decision.

## Convention

```text
data/       inputs
scripts/    experiment code
results/    saved outputs
tables/     compact summaries
docs/       current report and evidence map
```

Older development pools that are not needed for the reported analyses are intentionally omitted from the cleaned repository.
