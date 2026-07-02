#!/usr/bin/env python3
"""
cross_model_patch.py

Cross-model activation patching for base Qwen2.5-7B-Instruct and CI-finetuned Qwen.

Question tested:
  Are CI activations themselves sufficient to rescue the base model, or does the
  CI model's downstream/readout computation matter?

This script patches activations from a donor model into a receiver model:
  - ci_to_base: source activations from CI, forward pass through base
  - base_to_ci: source activations from base, forward pass through CI

Recommended first run:
  python scripts/cross_model_patch.py \
    --seeds data/final/curated_candidate_pool_source_capped_for_patching.csv \
    --eligibility data/final/curated_improvement_eligibility_source_capped.csv \
    --experiments final_AD,both_last_AD \
    --pairs both \
    --layers 0-26 \
    --dtype float16 \
    --out-detail results/source_capped_CROSSMODEL.csv \
    --out-summary results/source_capped_CROSSMODEL_summary.csv \
    --out-peaks results/source_capped_CROSSMODEL_peaks.csv

Interpretation guide:
  - base source -> CI receiver works strongly: base has features CI can use.
  - CI source -> base receiver fails: base downstream/readout cannot use them.
  - CI source -> base receiver works strongly: CI features are causally sufficient.
  - both directions partial: both representation and readout changed.
"""

from __future__ import annotations

import argparse
import gc
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import torch
from tqdm import tqdm

from ci_dataset import load_seeds, build_tokenized_scenario

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
CI_MODEL = "huseyinatahaninan/Qwen2.5-7B-Instruct-CI"

YES_VARIANTS = ["Yes", " Yes", "yes", " yes", "YES", " YES"]
NO_VARIANTS  = ["No",  " No",  "no",  " no",  "NO",  " NO"]

EXPECTED = {"A": "Yes", "B": "No", "C": "No", "D": "No"}

# Each experiment patches source_version into target_version at a token/span site.
# Eligibility is applied in make_trials().
EXPERIMENT_SPECS = {
    "final_AB":       {"versions": ("A", "B"), "site": "final",          "flag": "improve_B"},
    "recipient_last_AB": {"versions": ("A", "B"), "site": "recipient_last", "flag": "patch_recipient_AB_lasttok"},
    "recipient_span_AB": {"versions": ("A", "B"), "site": "recipient_span", "flag": "patch_recipient_AB_strictspan"},

    "final_AC":       {"versions": ("A", "C"), "site": "final",          "flag": "improve_C"},
    "purpose_last_AC": {"versions": ("A", "C"), "site": "purpose_last",   "flag": "patch_purpose_AC_lasttok"},
    "purpose_span_AC": {"versions": ("A", "C"), "site": "purpose_span",   "flag": "patch_purpose_AC_strictspan"},

    "final_AD":       {"versions": ("A", "D"), "site": "final",          "flag": "patch_final_AD"},
    "both_last_AD":   {"versions": ("A", "D"), "site": "both_last",      "flag": "improve_D"},
    "both_span_AD":   {"versions": ("A", "D"), "site": "both_span",      "flag": "patch_both_AD_strictspan"},
}


@dataclass(frozen=True)
class Trial:
    scenario_id: int
    experiment: str
    direction: str
    source_version: str
    target_version: str
    site: str
    expected_direction: int  # +1 means patch should increase Yes-No margin; -1 decrease


def parse_layers(s: str) -> List[int]:
    out: List[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(dict.fromkeys(out))


def dtype_from_name(name: str):
    return {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[name]


def first_device(model) -> torch.device:
    return next(model.parameters()).device


def short_name(model_id: str) -> str:
    if model_id == BASE_MODEL or model_id.endswith("Qwen2.5-7B-Instruct"):
        return "base"
    if model_id == CI_MODEL or model_id.endswith("Qwen2.5-7B-Instruct-CI"):
        return "ci"
    return model_id.split("/")[-1]


def get_yes_no_token_ids(tokenizer):
    def collect(words):
        out = []
        for w in words:
            ids = tokenizer.encode(w, add_special_tokens=False)
            if len(ids) == 1:
                out.append(ids[0])
        return list(dict.fromkeys(out))
    return collect(YES_VARIANTS), collect(NO_VARIANTS)


def yes_no_margin(logits_last, yes_ids, no_ids):
    yes_max = max(logits_last[i].item() for i in yes_ids)
    no_max = max(logits_last[i].item() for i in no_ids)
    return float(yes_max), float(no_max), float(yes_max - no_max)


def decision_from_margin(margin: float) -> str:
    return "Yes" if margin > 0 else "No"


def positions_for(tok, site: str) -> List[int]:
    if site == "final":
        return [tok.final_answer_idx]
    if site == "recipient_last":
        return [tok.recipient_last_idx]
    if site == "purpose_last":
        return [tok.purpose_last_idx]
    if site == "both_last":
        return [tok.recipient_last_idx, tok.purpose_last_idx]
    if site == "recipient_span":
        return list(range(tok.recipient_token_start, tok.recipient_token_end))
    if site == "purpose_span":
        return list(range(tok.purpose_token_start, tok.purpose_token_end))
    if site == "both_span":
        return list(range(tok.recipient_token_start, tok.recipient_token_end)) + \
               list(range(tok.purpose_token_start, tok.purpose_token_end))
    raise ValueError(f"Unknown site: {site}")


def expected_margin_direction(source_version: str, target_version: str) -> int:
    """+1 when source should push target toward Yes; -1 toward No."""
    source_expected = EXPECTED[source_version]
    target_expected = EXPECTED[target_version]
    if source_expected == target_expected:
        raise ValueError(f"No sign convention for same-answer patch {source_version}->{target_version}")
    return +1 if source_expected == "Yes" else -1


def make_trials(seeds: pd.DataFrame, eligibility: pd.DataFrame, experiments: List[str]) -> List[Trial]:
    elig = eligibility.set_index("scenario_id")
    trials: List[Trial] = []
    for _, row in seeds.iterrows():
        sid = int(row["scenario_id"])
        if sid not in elig.index:
            continue
        erow = elig.loc[sid]
        for exp in experiments:
            spec = EXPERIMENT_SPECS[exp]
            flag = spec["flag"]
            if flag in erow.index and not bool(erow[flag]):
                continue
            v1, v2 = spec["versions"]
            site = spec["site"]
            for source_v, target_v in [(v1, v2), (v2, v1)]:
                trials.append(Trial(
                    scenario_id=sid,
                    experiment=exp,
                    direction=f"{source_v}_to_{target_v}",
                    source_version=source_v,
                    target_version=target_v,
                    site=site,
                    expected_direction=expected_margin_direction(source_v, target_v),
                ))
    return trials


def load_model(model_id: str, dtype, device: str):
    from transformers import AutoModelForCausalLM
    name = short_name(model_id)
    print(f"\n[{name}] loading {model_id}")
    if device == "cuda":
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=dtype,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        ).to(device)
    model.eval()
    return model


def free_model(model):
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


@torch.no_grad()
def collect_donor_cache(model, tokenizer, seeds_by_sid: Dict[int, pd.Series], trials: List[Trial], layers: List[int]):
    """Collect source activations from donor model on CPU float16."""
    # Unique source requests by scenario/source_version/site.
    requests = sorted({(t.scenario_id, t.source_version, t.site) for t in trials})
    cache: Dict[Tuple[int, str, str, int], torch.Tensor] = {}

    for sid, source_v, site in tqdm(requests, desc="donor activations"):
        row = seeds_by_sid[sid]
        toks = build_tokenized_scenario(row, tokenizer)
        tok = toks[source_v]
        pos = positions_for(tok, site)
        input_ids = torch.tensor([tok.input_ids], dtype=torch.long, device=first_device(model))
        out = model(input_ids=input_ids, output_hidden_states=True, use_cache=False)
        for layer in layers:
            hs = out.hidden_states[layer + 1][0]  # [seq, hidden]
            cache[(sid, source_v, site, layer)] = hs[pos, :].detach().cpu().to(torch.float16)
        del out, input_ids

    return cache


@torch.no_grad()
def forward_margin(model, tokenizer, tok, yes_ids, no_ids, patch=None):
    """
    patch: None or dict with keys layer, target_positions, activation_cpu.
    activation_cpu shape [n_positions, hidden].
    """
    input_ids = torch.tensor([tok.input_ids], dtype=torch.long, device=first_device(model))
    handle = None

    if patch is not None:
        layer = int(patch["layer"])
        target_positions = list(patch["target_positions"])
        activation_cpu = patch["activation_cpu"]

        def hook_fn(module, inputs, output):
            if isinstance(output, tuple):
                h = output[0].clone()
                extra = output[1:]
                h[:, target_positions, :] = activation_cpu.to(device=h.device, dtype=h.dtype).unsqueeze(0)
                return (h,) + extra
            h = output.clone()
            h[:, target_positions, :] = activation_cpu.to(device=h.device, dtype=h.dtype).unsqueeze(0)
            return h

        handle = model.model.layers[layer].register_forward_hook(hook_fn)

    try:
        out = model(input_ids=input_ids, use_cache=False)
    finally:
        if handle is not None:
            handle.remove()

    logits_last = out.logits[0, -1, :]
    y, n, m = yes_no_margin(logits_last, yes_ids, no_ids)
    del out, input_ids
    return y, n, m


def run_pair(
    donor_model_id: str,
    receiver_model_id: str,
    tokenizer,
    seeds_by_sid: Dict[int, pd.Series],
    trials: List[Trial],
    layers: List[int],
    dtype,
    device: str,
) -> pd.DataFrame:
    donor_name = short_name(donor_model_id)
    receiver_name = short_name(receiver_model_id)
    pair_name = f"{donor_name}_to_{receiver_name}"

    donor = load_model(donor_model_id, dtype, device)
    donor_cache = collect_donor_cache(donor, tokenizer, seeds_by_sid, trials, layers)
    free_model(donor)

    receiver = load_model(receiver_model_id, dtype, device)
    yes_ids, no_ids = get_yes_no_token_ids(tokenizer)

    rows = []
    original_cache: Dict[Tuple[int, str], Tuple[float, float, float]] = {}
    tokenized_cache: Dict[int, Dict[str, object]] = {}

    for t in tqdm(trials, desc=f"patch {pair_name}"):
        if t.scenario_id not in tokenized_cache:
            tokenized_cache[t.scenario_id] = build_tokenized_scenario(seeds_by_sid[t.scenario_id], tokenizer)
        toks = tokenized_cache[t.scenario_id]
        target_tok = toks[t.target_version]
        target_positions = positions_for(target_tok, t.site)

        for layer in layers:
            donor_act = donor_cache[(t.scenario_id, t.source_version, t.site, layer)]
            if donor_act.shape[0] != len(target_positions):
                # Should only happen if a strict span slipped through without length matching.
                continue

            orig_key = (t.scenario_id, t.target_version)
            if orig_key not in original_cache:
                original_cache[orig_key] = forward_margin(receiver, tokenizer, target_tok, yes_ids, no_ids, patch=None)
            oy, on, om = original_cache[orig_key]
            original_decision = decision_from_margin(om)

            py, pn, pm = forward_margin(receiver, tokenizer, target_tok, yes_ids, no_ids, patch={
                "layer": layer,
                "target_positions": target_positions,
                "activation_cpu": donor_act,
            })
            patched_decision = decision_from_margin(pm)
            effect = pm - om
            aligned_effect = effect * t.expected_direction

            rows.append({
                "pair": pair_name,
                "donor_model": donor_model_id,
                "receiver_model": receiver_model_id,
                "donor": donor_name,
                "receiver": receiver_name,
                "scenario_id": t.scenario_id,
                "experiment": t.experiment,
                "direction": t.direction,
                "source_version": t.source_version,
                "target_version": t.target_version,
                "site": t.site,
                "layer": layer,
                "n_positions_patched": len(target_positions),
                "source_expected": EXPECTED[t.source_version],
                "target_expected": EXPECTED[t.target_version],
                "expected_direction": t.expected_direction,
                "original_yes_logit": oy,
                "original_no_logit": on,
                "original_margin": om,
                "original_decision": original_decision,
                "patched_yes_logit": py,
                "patched_no_logit": pn,
                "patched_margin": pm,
                "patched_decision": patched_decision,
                "effect": effect,
                "aligned_effect": aligned_effect,
                "flipped": patched_decision != original_decision,
                "patched_matches_source_answer": patched_decision == EXPECTED[t.source_version],
                "patched_matches_target_answer": patched_decision == EXPECTED[t.target_version],
            })

    free_model(receiver)
    return pd.DataFrame(rows)


def summarize(detail: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    summary = detail.groupby(["pair", "donor", "receiver", "experiment", "direction", "site", "layer"], as_index=False).agg(
        n=("scenario_id", "nunique"),
        mean_effect=("effect", "mean"),
        mean_aligned_effect=("aligned_effect", "mean"),
        median_aligned_effect=("aligned_effect", "median"),
        flip_rate=("flipped", "mean"),
        source_answer_rate=("patched_matches_source_answer", "mean"),
        target_answer_rate=("patched_matches_target_answer", "mean"),
        mean_original_margin=("original_margin", "mean"),
        mean_patched_margin=("patched_margin", "mean"),
    )

    peak_rows = []
    for keys, g in summary.groupby(["pair", "experiment", "direction", "site"]):
        # Choose the layer with highest flip rate; break ties by aligned effect.
        gg = g.sort_values(["flip_rate", "mean_aligned_effect"], ascending=[False, False])
        peak_rows.append(gg.iloc[0].to_dict())
    peaks = pd.DataFrame(peak_rows)
    return summary, peaks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--eligibility", required=True)
    ap.add_argument("--experiments", default="final_AD,both_last_AD",
                    help=f"Comma-separated experiments. Choices: {','.join(EXPERIMENT_SPECS)}")
    ap.add_argument("--pairs", default="both", choices=["ci_to_base", "base_to_ci", "both"])
    ap.add_argument("--layers", default="0-26")
    ap.add_argument("--dtype", default="float16", choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu", choices=["cuda", "cpu"])
    ap.add_argument("--tokenizer", default=BASE_MODEL)
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--ci-model", default=CI_MODEL)
    ap.add_argument("--max-trials", type=int, default=None,
                    help="Debug only: cap number of source/target trial rows before layer sweep.")
    ap.add_argument("--out-detail", required=True)
    ap.add_argument("--out-summary", required=True)
    ap.add_argument("--out-peaks", required=True)
    args = ap.parse_args()

    from transformers import AutoTokenizer

    experiments = [x.strip() for x in args.experiments.split(",") if x.strip()]
    bad = [x for x in experiments if x not in EXPERIMENT_SPECS]
    if bad:
        raise ValueError(f"Unknown experiments: {bad}. Choices: {list(EXPERIMENT_SPECS)}")

    layers = parse_layers(args.layers)
    dtype = dtype_from_name(args.dtype)

    seeds = load_seeds(args.seeds)
    eligibility = pd.read_csv(args.eligibility)

    trials = make_trials(seeds, eligibility, experiments)
    if args.max_trials is not None:
        trials = trials[:args.max_trials]

    needed_sids = sorted({t.scenario_id for t in trials})
    seeds = seeds[seeds["scenario_id"].astype(int).isin(needed_sids)].copy()
    seeds_by_sid = {int(r["scenario_id"]): r for _, r in seeds.iterrows()}

    print(f"Experiments: {experiments}")
    print(f"Trials before layer sweep: {len(trials)}")
    print(f"Scenarios used: {len(seeds_by_sid)}")
    print(f"Layers: {layers[0]}..{layers[-1]} ({len(layers)})")

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)

    pair_list = []
    if args.pairs in ("ci_to_base", "both"):
        pair_list.append((args.ci_model, args.base_model))
    if args.pairs in ("base_to_ci", "both"):
        pair_list.append((args.base_model, args.ci_model))

    detail_parts = []
    for donor_id, receiver_id in pair_list:
        df = run_pair(donor_id, receiver_id, tokenizer, seeds_by_sid, trials, layers, dtype, args.device)
        detail_parts.append(df)

    detail = pd.concat(detail_parts, ignore_index=True) if detail_parts else pd.DataFrame()
    summary, peaks = summarize(detail)

    for p in [args.out_detail, args.out_summary, args.out_peaks]:
        Path(p).parent.mkdir(parents=True, exist_ok=True)

    detail.to_csv(args.out_detail, index=False)
    summary.to_csv(args.out_summary, index=False)
    peaks.to_csv(args.out_peaks, index=False)

    print("\nSaved:")
    print(" ", args.out_detail)
    print(" ", args.out_summary)
    print(" ", args.out_peaks)

    print("\nPeak preview:")
    cols = ["pair", "experiment", "direction", "site", "layer", "n", "mean_aligned_effect", "flip_rate", "source_answer_rate"]
    print(peaks[cols].sort_values(["experiment", "direction", "pair"]).to_string(index=False))


if __name__ == "__main__":
    main()
