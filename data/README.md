# Data

This folder contains only the input data needed to reproduce the final main and appendix analyses.

## Included

- `raw/PrivacyLens/data/main_data.json`: PrivacyLens prompt data used for all-level PrivacyLens evaluations.
- `final/curated_candidate_pool_source_capped_CLEAN304.csv`: curated 304-scenario pool used for clean304-based writer-neuron, direction, component, sufficiency, and base/CI analyses.
- `final/source_capped_CLEAN304_improvement_eligibility.csv`: clean304 eligibility and behavior metadata used by the clean304 scripts.
- `final/curated_candidate_pool_source_capped_for_patching.csv`: 391-scenario source-capped pool used for broad patching, activation-similarity, and cross-model appendix analyses.
- `final/curated_improvement_eligibility_source_capped.csv`: eligibility and behavior metadata for the 391-scenario source-capped appendix pool.

## Not included

Older development pools, pilot behavior runs, manual 28-case results, candidate_7344, hard_600, and large_180 CSVs are intentionally omitted from the GitHub version. They were useful during dataset construction but are not needed for the final reported analyses.
