# Main and appendix organization

The documentation is organized around a single main causal story, with supporting analyses separated into appendix sections.

## Main results

The main result files in `docs/main_results/` contain the core evidence for the proposed L18 attention → L22 MLP privacy-decision pathway.

The main story is organized as follows:

1. **CI L22 MLP writer-neuron scan**
   Identifies L22 MLP writer neurons, especially L22 neuron 13149, as strongly associated with the privacy refusal direction.

2. **CI L22 direction ablation across PrivacyLens levels**
   Tests whether removing the L22 writer-neuron contribution changes the final Yes/No decision across all four PrivacyLens prompt levels.

3. **CI L18 attention-head scan**
   Identifies upstream L18 attention heads, especially H15, H18, H4, H13, and H20, as candidate routing components.

4. **CI L18→L22 mediation across PrivacyLens levels**
   Tests whether patching the L18 heads shifts both the final Yes/No margin and the downstream activation of L22 neuron 13149.

5. **Base L22 remove/rescue experiments**
   Tests whether the base model already contains compatible downstream L22 privacy-decision machinery.

6. **Base L18→L22 remove/rescue experiments**
   Tests whether the base model also contains a partially usable upstream L18→L22 routing pathway.

Together, these main results support the central interpretation: the CI-tuned model does not appear to create an entirely new privacy circuit from scratch. Instead, the base model already contains compatible privacy-decision machinery, and CI tuning makes privacy-sensitive prompts activate this machinery more reliably.

## Appendix results

The appendix result files in `docs/appendix_results/` contain supporting analyses, controls, and broader checks. These results are important for validating the interpretation, but they are not the main narrative.

The appendix includes:

* **Activation similarity analyses**, showing that base and CI hidden states remain highly aligned.
* **Final-direction ablation and control experiments**, showing that broad D-vs-A directions are causal from mid-to-late layers.
* **Within-model A/B/C/D patching**, showing how recipient, purpose, and final-token interventions affect privacy decisions.
* **Cross-model patching**, showing shared privacy-decision geometry between the base and CI models.
* **Component direction ablation**, localizing causal signal to L18 attention and late MLP components.
* **MLP neuron sufficiency and add-delta controls**, testing whether writer-neuron activations can push allowed prompts toward refusal-like decisions.
* **Base-top vs CI-top writer-neuron overlap**, showing substantial overlap between base and CI writer-neuron sets.
* **Older base-rescue variants and A-baseline ablations**, kept as secondary or exploratory evidence rather than central claims.

## Results highlighted briefly in the main summary

Some appendix results are strong enough to mention briefly in the README or technical note, while keeping their full details in the appendix:

* Cross-model D-final patching shows that CI D activations patched into base D prompts rescue 189/190 base failures, while base D activations patched into CI D prompts destroy 188/190 CI refusals.
* Component direction ablation shows strong causal effects at L18 attention and late MLP components, especially around L20–L22 and L27.
* Base/CI writer-neuron overlap is high; for example, the L22 top-100 writer-neuron sets overlap by 92/100 neurons.

These analyses strengthen the main interpretation but are kept outside the main result sequence to avoid making the core story too broad.

## Source of truth

The public repository uses the cleaned documentation as the source of truth:

```text
docs/main_results/
docs/appendix_results/
docs/technical_note/
```

Scratch notes, raw working notes, and preserved development notes are not part of the public-facing documentation. The cleaned result notes, summary tables, and technical note are the intended entry points for readers.
