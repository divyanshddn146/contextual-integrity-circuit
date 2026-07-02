# Dataset usage and prompt counts

## Repository data convention

The repository separates **input data** from **experiment outputs**.

Input datasets and curated prompt pools are stored under:

```text
data/
```

The main input paths are:

```text
data/raw/PrivacyLens/data/main_data.json
data/final/curated_candidate_pool_source_capped_CLEAN304.csv
data/final/source_capped_CLEAN304_improvement_eligibility.csv
data/final/curated_candidate_pool_source_capped_for_patching.csv
data/final/curated_improvement_eligibility_source_capped.csv
```

Experiment outputs are stored under:

```text
results/main/
results/appendix_clean304/
```

The intended convention is:

```text
data/     = input datasets and curated prompt pools
results/  = generated experiment outputs
scripts/  = code used to run experiments
docs/     = write-ups and result explanations
tables/   = compact summary tables
```

## PrivacyLens all-level experiments

The all-level PrivacyLens experiments use PrivacyLens cases from:

```text
data/raw/PrivacyLens/data/main_data.json
```

These experiments evaluate four prompt levels:

```text
seed
vignette
trajectory
trajectory_enhancing
```

Each level contains 493 prompts.

These experiments use simplified Yes/No privacy-decision prompts derived from the PrivacyLens cases. They do not use the full ToolEmu/procoder agent-action benchmark format.

## Clean304-derived A/D experiments

Some writer-neuron and direction-control experiments use a clean304-derived A/D subset rather than all 304 scenarios.

| Subset              | Count |
| ------------------- | ----: |
| AD-eligible total   |   190 |
| Train split         |    95 |
| Held-out test split |    95 |

> The MLP writer-neuron scan and several appendix direction-control experiments use the clean304-derived AD-eligible subset: 190 A/D scenarios split into 95 training cases and 95 held-out test cases.

These experiments do not use all 304 prompts.

## Clean304 contrast subsets

Some appendix analyses start from the clean304 scenario pool, but the usable number of examples depends on the contrast being tested.

| Contrast              | Meaning                              | Count |
| --------------------- | ------------------------------------ | ----: |
| AB                    | Recipient violation                  |    49 |
| AC                    | Purpose violation                    |    87 |
| AD                    | Both recipient and purpose violation |   190 |
| Strict recipient span | Recipient-span intervention subset   |    28 |
| Strict purpose span   | Purpose-span intervention subset     |    65 |
| Strict both span      | Both-span intervention subset        |    85 |

> These appendix experiments are based on the clean304 scenario pool. Raw activation-similarity analyses use all 304 scenarios, while contrast-specific patching analyses use eligible clean304-derived subsets: 49 AB cases, 87 AC cases, 190 AD cases, and strict-span subsets of 28, 65, and 85 cases.
