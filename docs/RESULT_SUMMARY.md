# Result summary

## Main quantitative checkpoints

### CI L22 direction ablation
| Level | alpha | flips | n | mean shift toward Yes |
|---|---:|---:|---:|---:|
| seed | 4 | 150 | 481 | 23.62 |
| seed | 6 | 481 | 481 | 41.73 |
| vignette | 4 | 164 | 485 | 23.24 |
| vignette | 6 | 485 | 485 | 40.39 |
| trajectory | 4 | 385 | 478 | 22.05 |
| trajectory | 6 | 478 | 478 | 36.95 |
| trajectory_enhancing | 4 | 137 | 493 | 21.90 |
| trajectory_enhancing | 6 | 493 | 493 | 37.02 |
- Overall alpha 4: 836/1937 flips.
- Overall alpha 6: 1937/1937 flips.

### CI L18→L22 mediation
| Level | top L18 flips | random flips | margin shift | L22 shift toward A | corr |
|---|---:|---:|---:|---:|---:|
| seed | 56/481 | 1/481 | 16.94 | 20.77 | 0.816 |
| vignette | 61/485 | 0/485 | 14.98 | 16.73 | 0.911 |
| trajectory | 150/478 | 1/478 | 16.67 | 18.28 | 0.897 |
| trajectory_enhancing | 14/493 | 0/493 | 13.31 | 12.56 | 0.936 |

### Base L22 remove/rescue
| Level | remove top100 a6 No→Yes | rescue top100 a2 Yes→No |
|---|---:|---:|
| seed | 477/477 | 15/16 |
| vignette | 480/480 | 10/13 |
| trajectory | 462/462 | 29/31 |
| trajectory_enhancing | 491/491 | 2/2 |
- Overall remove: 1910/1910; overall rescue: 56/62.

### Base L18→L22 remove/rescue
#### remove
| Level | top L18 success | random success | target-margin shift | L22 target shift |
|---|---:|---:|---:|---:|
| seed | 80/477 | 1/477 | 17.80 | 22.49 |
| vignette | 90/480 | 0/480 | 16.04 | 19.21 |
| trajectory | 214/462 | 0/462 | 16.38 | 19.39 |
| trajectory_enhancing | 69/491 | 0/491 | 15.14 | 15.94 |
- Overall top L18: 453/1910; random: 1/1910.
#### rescue
| Level | top L18 success | random success | target-margin shift | L22 target shift |
|---|---:|---:|---:|---:|
| seed | 5/16 | 1/16 | 4.26 | 4.85 |
| vignette | 4/13 | 0/13 | 5.77 | 5.95 |
| trajectory | 20/31 | 1/31 | 7.51 | 8.00 |
| trajectory_enhancing | 2/2 | 0/2 | 6.59 | 9.16 |
- Overall top L18: 31/62; random: 2/62.

## Recommended narrative

1. **CI L22 writer scan** identifies a compact downstream MLP writer pathway, with L22 N13149 as the strongest neuron.
2. **CI L22 direction ablation** shows this pathway controls PrivacyLens refusals across all four prompt levels.
3. **CI L18 attention scan** finds a small upstream head set: L18H15, L18H18, L18H4, L18H13, L18H20.
4. **CI L18→L22 mediation** shows these heads shift L22 N13149 toward the allowed state and track the Yes/No margin.
5. **Base L22 remove/rescue** shows the downstream machinery already exists in the base model.
6. **Base L18 remove/rescue** shows the base model also has partially usable upstream routing.

## One-sentence claim

CI tuning does not appear to create an entirely new privacy circuit. Instead, the base model already contains compatible privacy-decision machinery, and CI tuning makes privacy-sensitive prompts activate this machinery more reliably.
