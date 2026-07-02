# Project overview

## Core hypothesis

The project asks whether contextual-integrity (CI) tuning creates a new privacy mechanism, or instead makes the model use machinery that is already present in the base model.

The current evidence supports the second interpretation:

> CI tuning does not appear to create an entirely new privacy circuit. Instead, the base model already contains compatible privacy-decision machinery, and CI tuning makes privacy-sensitive prompts activate this machinery more reliably.

## Mechanistic picture

The strongest current pathway hypothesis is:

```text
L18 attention heads → L22 MLP writer-neuron pathway → final Yes/No privacy decision
```

The main components are:

- **Upstream routing heads:** L18H15, L18H18, L18H4, L18H13, L18H20.
- **Downstream writer pathway:** L22 MLP writer neurons, especially **L22 N13149**.
- **Decision direction:** D/disallowed/refusal vs A/allowed/permission direction.

## High-level results

1. **CI L22 writer-neuron scan:** L22 N13149 is the strongest writer neuron. On the clean304-derived AD split, ablating its writer contribution flips 95/95 held-out D prompts from No to Yes.
2. **CI L22 direction ablation across all PrivacyLens levels:** L22 top100 α=4 flips 836/1937 normal-No cases; α=6 flips 1937/1937. Random controls flip 0.
3. **CI L18 attention-head scan:** L18 top5 patch shifts the Yes margin by +16.67 and flips 150/478 CI trajectory refusals; random heads flip only 1–4.
4. **CI L18→L22 mediation across all levels:** L18 top5 consistently shifts L22 N13149 toward A/allowed and has strong correlation between L22 shift and margin shift.
5. **Base L22 remove/rescue:** removing L22 refusal contribution flips 1910/1910 base No cases at α=6; adding CI-like L22 contribution rescues 56/62 base Yes failures at α=2.
6. **Base L18→L22 remove/rescue:** patching L18 heads toward A flips 453/1910 base No cases; patching toward D rescues 31/62 base Yes failures. Random controls are near zero.

## What to claim carefully

Safe claim:

> The base model already contains compatible L18→L22 privacy-decision machinery, and CI tuning appears to make privacy-sensitive contexts route into this machinery more reliably.

Avoid overclaiming:

- Do not say the circuit is complete or exhaustive.
- Do not say L18 fully controls the decision.
- Do not say rationale generation is fully localized; final decision is more localized than full rationale.
