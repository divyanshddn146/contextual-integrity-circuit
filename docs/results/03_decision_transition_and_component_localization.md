# 3. Decision transition and component localization

## D-minus-A decision direction

Using the 95-case discovery split, the final-token D-minus-A direction is already highly linearly separable before L18. Separability alone does not mean the model is using that direction to determine the answer, so the key test is intervention.

On the 95 held-out D cases:

| Layer | Held-out AUC | No-to-Yes changes at alpha=1 |
|---|---:|---:|
| 16 | 0.979 | 12/95 |
| 17 | 0.996 | 19/95 |
| 18 | 1.000 | 95/95 |
| 20 | 1.000 | 95/95 |
| 22 | 1.000 | 95/95 |
| 24 | 1.000 | 95/95 |
| 26 | 1.000 | 95/95 |

At L18 the effect is already strong at smaller strengths: 59/95 changes at alpha=0.25, 86/95 at alpha=0.5, and 95/95 at alpha=1. Matched random directions produce only about 0.7 to 1.4 percent changes.

The direction therefore becomes strongly decision-relevant around L18 even though it is readable earlier.

## Component localization

The next step decomposes the residual-stream transition into attention and MLP contributions while intervening only on each component's write along the same discovery-derived direction.

### Attention

Attention is sharply localized:

- L17: 3/95
- **L18: 93/95**
- L19: 7/95
- L20: 36/95
- L21: 29/95

The maximum matched random-attention control is 3/95.

### MLP

The MLP pattern is broader:

- L18: 72/95
- L19: 87/95
- L20: 94/95
- L21: 94/95
- L22: 91/95

The maximum matched random-MLP control is 8/95.

## Mechanistic update

The sharp change in the residual stream around L18 coincides with a highly localized attention contribution, followed by sustained late MLP writing. This motivates the more specific candidate pathway tested next:

```text
L18 attention contribution -> late MLP writer state -> first Yes/No decision
```

Saved outputs: `results/clean304/final_direction_ablation/`, `results/clean304/final_direction_controls/`, and `results/clean304/component_direction_ablation/`.
