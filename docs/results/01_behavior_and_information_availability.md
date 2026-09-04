# 1. Behavioral gap and information availability

## Behavioral starting point

The project begins with a controlled A/B/C/D dataset in which recipient and purpose appropriateness are varied while the underlying scenario is held fixed.

The cleanest behavioral contrast is D, where both recipient and purpose are inappropriate:

| Checkpoint | Correct D decisions |
|---|---:|
| Base | 101/304 = 33.2% |
| CI | 291/304 = 95.7% |

This gives 190 A/D improvement cases where Base remains wrong on D while CI is correct. Those cases are split 95/95 for discovery and held-out evaluation in the later direction and writer analyses.

## First model-diffing question

A simple explanation would be that Base never represented the recipient or purpose information needed for the privacy decision. The patching results argue against that explanation.

### Recipient information

On the 49 eligible A/B cases, patching the Base recipient-aligned state from A toward the B condition at the recipient position produces a large average decision-margin movement. At the strongest recipient-last site, the Base mean aligned effect is about 6.33 logit units even though it does not usually cross Base's decision boundary.

CI shows a comparable local margin movement, but because its downstream decision process is already privacy-sensitive, the same kind of patch is much more likely to change the final answer.

### Purpose information

The same pattern appears for purpose. On the 87 eligible A/C cases, the Base purpose-position patch reaches a mean aligned effect of about 7.73 logit units while changing only 2/87 final decisions. CI reaches a similar local effect and changes 84/87 decisions at the corresponding purpose-last site.

### Strict span controls

Length-matched span interventions confirm that the effect is not restricted to a single token heuristic. Base recipient, purpose, and combined spans all produce large margin movements even when the final decision often remains unchanged.

## Interpretation

Base already computes context-sensitive information that can influence the privacy decision. The behavioral difference is therefore not well described as "CI learned the recipient and purpose concepts while Base lacked them." The more important difference lies in how this information is integrated into the final Yes/No state.

Saved outputs: `results/clean304/within_model_patching/`.
