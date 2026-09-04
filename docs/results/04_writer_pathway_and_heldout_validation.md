# 4. Writer pathway and held-out validation

## Writer-neuron scan

Qwen's gated MLP writes each intermediate-neuron activation back into the residual stream through its down-projection vector. The writer score combines two terms: how the neuron's activation changes between A and D, and how its down-projection aligns with the fixed D-minus-A direction.

The strongest discovered writer is **L22 neuron N13149**:

- writer score: 8.355,
- mean activation on A: +14.62,
- mean activation on D: -3.34,
- down-projection dot product with the D-minus-A direction: -0.465.

The sign pattern means N13149 is better interpreted as an **A/Yes-supporting writer that is suppressed on D**, not as a literal privacy-refusal neuron.

## Held-out intervention

The neuron ranking is estimated on the 95-case discovery split and then tested on the 95 held-out D cases.

Replacing only N13149's D activation with its A-condition discovery mean changes **95/95** held-out D decisions from No to Yes, with a mean margin movement of +2.71. Larger top-k writer sets also reach 95/95, with gradually larger average margin movement.

A different discovery split again ranks N13149 first, which reduces concern that the result is a single-split accident.

## Sufficiency follow-up

The first replacement-strength sweep through alpha=2 produced large margin shifts but no Yes-to-No changes on held-out A prompts. This was a useful negative result: the natural A-to-D writer difference was not automatically sufficient under that initial intervention.

Stronger additive D-minus-A interventions can become sufficient, for example L20 top-50 and top-100 reach 95/95 at alpha=3, while L22 top-100 reaches 79/95. A later stronger replacement sweep also becomes sufficient at higher strengths.

These stronger runs are best treated as controllability or sufficiency stress tests. They do not imply that natural model computation applies the same large intervention.

## Interpretation

N13149 is a strong localized handle on the downstream decision state, but it is not a unique bottleneck. The broader late MLP result and the effectiveness of larger writer sets indicate substantial redundancy.

Saved outputs: `results/clean304/writer_neuron_scan/` and `results/clean304/supporting/writer_sufficiency/`.
