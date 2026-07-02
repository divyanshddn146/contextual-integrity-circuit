# Cleanup notes

This public repo was reorganized to show the final research story clearly rather than preserve every scratch note.

## Included

- `docs/main_results/`: cleaned result notes for the six main experiments.
- `docs/appendix_results/`: cleaned appendix notes for supporting analyses.
- `docs/technical_note/`: concise 3-page LaTeX/PDF technical note.
- `scripts/main/`: scripts corresponding to the main causal story.
- `scripts/appendix/`: scripts for supporting appendix analyses.
- `results/main/`: final main result outputs.
- `results/appendix_clean304/`: cleaned supporting results based mostly on the clean304 scenario pool.
- `results/appendix_exploratory/`: exploratory supporting outputs that are not part of the main claim.

## Removed from the public version

The following were intentionally omitted from this GitHub-ready package to avoid clutter:

- nested duplicate repo copies,
- raw scratch notes,
- original unedited `.txt` notes,
- old documentation package duplicates,
- legacy source-capped result dumps,
- duplicate-preserved result folders.

These are not needed for understanding the final result. The cleaned documentation in `docs/main_results/` and `docs/appendix_results/` should be treated as the source of truth.

## Main-vs-appendix rule

The main story is the L18 attention → L22 MLP pathway:

1. CI L22 writer-neuron scan.
2. CI L22 direction ablation across all PrivacyLens levels.
3. CI L18 attention-head scan.
4. CI L18→L22 mediation across all PrivacyLens levels.
5. Base L22 remove/rescue across all PrivacyLens levels.
6. Base L18→L22 remove/rescue across all PrivacyLens levels.

Appendix analyses support the main interpretation but should not be treated as separate central claims.
