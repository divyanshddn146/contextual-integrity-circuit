# Main results checklist

Use this checklist when writing the paper or application.

## Main causal pathway

1. **CI L22 writer-neuron scan**
   - Folder: `results/main/ci_l22_writer_scan/`
   - Script: `scripts/main/mlp_neuron_writer_scan.py`
   - Key claim: L22 N13149 is the strongest writer neuron.

2. **CI L22 direction ablation across four PrivacyLens levels**
   - Folder: `results/main/ci_l22_direction_ablation/`
   - Script: `scripts/main/privacylens_direction_ablation_generation.py`
   - Key claim: L22 top100 α=6 flips all 1937/1937 normal-No cases; random controls flip zero.

3. **CI L18 attention-head scan**
   - Folder: `results/main/ci_l18_attention_head_scan/`
   - Script: `scripts/main/privacylens_attention_head_writer_scan_ablation.py`
   - Key heads: L18H15, L18H18, L18H4, L18H13, L18H20.

4. **CI L18→L22 mediation across four levels**
   - Folder: `results/main/ci_l18_to_l22_mediation/`
   - Script: `scripts/main/privacylens_l18_heads_to_l22_mlp_mediation_with_generation.py`
   - Key claim: L18 top heads move L22 N13149 toward A/allowed and track Yes/No margin; random controls are near zero.

5. **Base L22 remove/rescue across four levels**
   - Folder: `results/main/base_l22_remove_rescue/`
   - Script: `scripts/main/base_privacylens_direction_remove_rescue.py`
   - Key claim: base already has downstream L22 privacy-decision machinery.

6. **Base L18→L22 remove/rescue across four levels**
   - Folder: `results/main/base_l18_to_l22_remove_rescue/`
   - Script: `scripts/main/base_privacylens_l18_to_l22_rescue_mediation_with_generation.py`
   - Key claim: base has a partially usable upstream L18→L22 routing pathway.

## Optional one-sentence main-text supports

- Cross-model D-final patching: `results/appendix_clean304/cross_model_patch/`
- Base-vs-CI top-neuron overlap: `results/appendix_clean304/base_top_vs_ci_top_neuron_overlap/`
- Component direction ablation: `results/appendix_clean304/component_direction_ablation/`
