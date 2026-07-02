# Main story

## One-paragraph version

The experiments identify a candidate privacy-decision pathway in Qwen2.5-7B-Instruct-CI. A scan over MLP writer neurons finds a downstream L22 pathway, led by L22 neuron 13149, whose contribution is causally necessary for PrivacyLens refusals. Direct L22 direction ablation flips all normal-No cases across four PrivacyLens prompt levels at sufficient strength, while random-neuron controls have no effect. A separate attention-head scan identifies upstream L18 heads, especially H15, H18, H4, H13, and H20. Patching these heads toward the allowed state shifts L22 N13149 toward its allowed activation state and moves the final Yes/No margin across all prompt levels. Base-model remove/rescue experiments show that the base model already contains compatible L22 writer machinery and a partially usable L18→L22 routing pathway. Together, the evidence suggests that CI tuning makes privacy-sensitive prompts activate compatible privacy-decision machinery that is already partly present in the base model.

## Main causal chain

```text
Privacy-sensitive context
        ↓
L18 attention heads
        ↓
L22 MLP writer-neuron pathway, especially N13149
        ↓
Final Yes/No privacy decision
```

## What each main result contributes

1. **MLP writer scan**: identifies the downstream writer neurons.
2. **L22 direction ablation**: shows downstream writer contribution controls PrivacyLens refusals.
3. **L18 attention-head scan**: identifies candidate upstream routing heads.
4. **L18→L22 mediation**: links upstream L18 heads to downstream L22 N13149 activation and margin shifts.
5. **Base L22 remove/rescue**: shows downstream pathway exists in the base model.
6. **Base L18 remove/rescue**: shows upstream routing is also partly present in the base model.

## Recommended main-text wording

> CI tuning does not appear to create a wholly new privacy circuit. Instead, the base model already contains compatible L18→L22 privacy-decision machinery, while CI tuning appears to make privacy-sensitive contexts route into this machinery more reliably.

## Caveat

The final Yes/No decision is easier to localize than the full generated rationale. Rationale generation remains more distributed and can be less transferable across datasets.
