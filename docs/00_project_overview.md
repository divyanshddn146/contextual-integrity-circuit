# Project overview

## Research question

Contextual-integrity post-training substantially improves privacy decisions in Qwen2.5-7B-Instruct. This project asks what internal change produced that improvement.

Two broad hypotheses motivated the experimental sequence:

1. **New-mechanism hypothesis.** CI training creates a qualitatively new privacy representation or circuit that Base did not previously contain.
2. **Reuse/recruitment hypothesis.** Base already contains much of the relevant machinery, and CI training changes how reliably that machinery is recruited, integrated, or expressed in the final decision.

The current evidence favors the second hypothesis.

## Experimental sequence

### 1. Establish the behavioral gap

I first use matched A/B/C/D counterfactuals that independently manipulate recipient appropriateness and purpose appropriateness. The cleanest contrast is A versus D. On D, where both recipient and purpose are inappropriate, Base is correct on 101/304 cases while CI is correct on 291/304.

### 2. Ask whether Base already contains useful contextual information

Within-model patching shows that recipient- and purpose-related states in Base can already move the Yes/No margin strongly in the expected direction. This weakens the idea that CI succeeds simply because it learned contextual information that Base never represented.

### 3. Compare the checkpoints directly

Activation similarity shows that Base and CI remain geometrically close, including strongly aligned privacy-related contrast directions in late layers. Cross-model patching then asks a stronger functional question: can a state produced by one checkpoint still be used by the other?

Base-produced semantic states are highly usable by CI. In the reverse direction, CI local semantic states often move Base without fully crossing its native decision boundary. Once a late CI decision state has formed, however, Base can use it reliably.

### 4. Locate where the difference becomes decision-relevant

On identical D prompts, final-position state transfer has modest effects through the earlier network, then changes sharply around L18. By the late layers, swapping the checkpoint state nearly swaps the decision.

A discovery-derived D-minus-A direction shows the same transition. The direction is already readable before L18, but intervention on that direction becomes strongly behavior-changing around L18.

### 5. Decompose the L18 transition

Component-level intervention separates a sharp L18 attention effect from broader late MLP writing. Attention peaks strongly at L18, while MLP contributions remain large across several later layers.

A head-level scan identifies the fixed L18 set H15, H18, H4, H13, and H20. A late writer scan identifies L22 N13149 as the strongest individual writer handle, with a broader set of late writer neurons also contributing.

### 6. Test out-of-discovery transfer

The discovered L18/L22 machinery is then frozen and tested on PrivacyLens rather than re-discovered there. The L22 writer intervention changes decisions across all four prompt levels. The fixed L18 head set also changes decisions and moves downstream N13149 in the predicted direction.

This L18-to-L22 result is best described as **downstream propagation or pathway validation**. It is not formal blocked mediation.

### 7. Test whether the same machinery was already active in Base

This is the key post-training test. I apply the fixed pathway logic directly inside Base.

Targeted L22 removal disrupts native Base No decisions, while the reverse intervention rescues many Base Yes failures. The same two-way logic works upstream at the fixed L18 head set, although the L18 effect is weaker than the direct L22 effect. Matched random controls are near zero.

The result argues against the idea that CI created a completely new pathway that was absent from Base.

### 8. Compare writer identities and naturally occurring correction cases

Base and CI share most of their independently ranked top late-MLP writer neurons. CI-derived writer changes can also be read and used by Base.

Finally, on identical PrivacyLens prompts where Base answers Yes and CI answers No, the corrected CI decision is accompanied by a substantial shift at the previously identified L22 writer neuron N13149. This last comparison is observational and does not establish where the checkpoint difference first originates.

## Current mechanistic picture

```text
recipient, purpose, contextual setting
                |
                v
      L18 attention contribution
       H15 H18 H4 H13 H20
                |
                v
       late MLP writer state
  L22 N13149 + broader writer set
                |
                v
        first Yes/No decision
```

The pathway is substantially shared across Base and CI. The remaining model-diffing question is finer grained: whether post-training primarily changes upstream routing, downstream writer-state calibration, or an interaction between the two.

## What this project does not establish

- It does not identify a complete privacy circuit.
- It does not establish that N13149 is a unique bottleneck or uniquely semantic privacy neuron.
- The L18-to-L22 evidence is not formal blocked mediation.
- Some high-strength interventions are controllability stress tests rather than naturalistic perturbations.
- The strongest mechanistic claims concern the first Yes/No decision, not the full generated rationale.
- The study compares one Base/CI checkpoint pair, so generalization across model families remains open.
