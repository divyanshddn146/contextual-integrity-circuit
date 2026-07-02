# Data CSV Audit
This audit classifies the CSV files from the older `data/` folder for the cleaned GitHub repo.
## Summary
- **KEEP**: included in the cleaned repo.
- **OPTIONAL**: useful provenance, but not required to run the final scripts.
- **DROP**: old development, duplicate, or pilot file; keep locally only.

| Decision | Path | Rows | Columns | Reason |
|---|---|---:|---:|---|
| KEEP | `data/final/curated_candidate_pool_source_capped_CLEAN304.csv` | 304 | 11 | Essential main + clean304 appendix input |
| KEEP | `data/final/curated_candidate_pool_source_capped_for_patching.csv` | 391 | 16 | Essential broader 391-pool appendix input |
| KEEP | `data/final/curated_improvement_eligibility_source_capped.csv` | 391 | 52 | Essential broader 391-pool appendix eligibility metadata |
| KEEP | `data/final/source_capped_CLEAN304_improvement_eligibility.csv` | 304 | 49 | Essential clean304 eligibility/behavior metadata |
| OPTIONAL | `data/final/source_capped_CLEAN304_behavior_clean.csv` | 304 | 33 | Provenance only; not read by final scripts |
| OPTIONAL | `data/final/source_capped_CLEAN304_behavior_results.csv` | 2432 | 11 | Provenance only; not read by final scripts |
| OPTIONAL | `data/final/source_capped_CLEAN304_improvement_cases.csv` | 304 | 31 | Provenance only; not read by final scripts |
| OPTIONAL | `data/final/source_capped_CLEAN304_validation_summary.csv` | 304 | 21 | Subset of eligibility; redundant for scripts |
| DROP | `data/behavior_clean.csv` | 28 | 33 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/behavior_clean_candidate_7344.csv` | 7344 | 33 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/behavior_clean_hard_600.csv` | 600 | 33 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/behavior_clean_large_180.csv` | 180 | 33 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/behavior_results.csv` | 224 | 11 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/behavior_results_candidate_7344.csv` | 58752 | 11 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/behavior_results_hard_600.csv` | 4800 | 11 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/behavior_results_large_180.csv` | 1440 | 11 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/ci_improvement_cases_candidate_7344.csv` | 7344 | 31 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/ci_improvement_cases_hard_600.csv` | 600 | 31 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/ci_improvement_cases_large_180.csv` | 180 | 31 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/ci_improvement_eligibility_candidate_7344.csv` | 7344 | 49 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/ci_improvement_eligibility_hard_600.csv` | 600 | 49 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/ci_improvement_eligibility_large_180.csv` | 180 | 49 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/curated_improvement_eligibility_source_capped.csv` | 391 | 52 | Duplicate of data/final/curated_improvement_eligibility_source_capped.csv |
| DROP | `data/final/source_capped_validation_summary.csv` | 391 | 21 | Redundant 391 validation-only file; eligibility file is better |
| DROP | `data/patching_eligibility.csv` | 28 | 59 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/processed/candidate_pool_7344.csv` | 7344 | 16 | Older development/pilot/intermediate file; not needed for final GitHub repo |
| DROP | `data/processed/curated_candidate_pool_source_capped_for_patching.csv` | 391 | 16 | Duplicate of data/final/curated_candidate_pool_source_capped_for_patching.csv |
| DROP | `data/processed/fixed_paired_scenarios_6000.csv` | 5979 | 17 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/processed/hard_seed_pool_600_for_behavior.csv` | 600 | 16 | Older development/pilot/intermediate file; not needed for final GitHub repo |
| DROP | `data/processed/large_seed_pool_180_for_behavior.csv` | 204 | 19 | Older development/pilot/intermediate file; not needed for final GitHub repo |
| DROP | `data/processed/manual_seed_selection.csv` | 28 | 14 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/processed/privacylens_seeds.csv` | 565 | 10 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/processed/validation_summary_candidate_7344.csv` | 7344 | 21 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/processed/validation_summary_hard_5990.csv` | 5979 | 21 | Older development/pilot/intermediate file; not needed for final GitHub repo |
| DROP | `data/processed/validation_summary_hard_5991.csv` | 7344 | 21 | Older development/pilot/intermediate file; not needed for final GitHub repo |
| DROP | `data/processed/validation_summary_hard_600.csv` | 600 | 21 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/processed/validation_summary_large_180.csv` | 180 | 21 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/prompt_format_pilot_results.csv` | 120 | 12 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
| DROP | `data/validation_summary.csv` | 28 | 21 | Development/pilot dataset or early behavior result; not part of final main/appendix story |
