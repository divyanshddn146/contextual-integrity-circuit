#!/usr/bin/env python3
"""
cross_model_DD_final_both.py

Same-D final-token cross-model patching for base Qwen2.5-7B-Instruct and
CI-finetuned Qwen.

This file runs BOTH complementary D->D tests on improvement-D scenarios:

1) Destructive test: base D final -> CI D final
   donor:    base model on D prompt
   receiver: CI model on D prompt
   question: does replacing CI's correct D final-token state with base's D
             final-token state destroy CI's correct No answer?

2) Rescue test: CI D final -> base D final
   donor:    CI model on D prompt
   receiver: base model on D prompt
   question: does replacing base's wrong D final-token state with CI's D
             final-token state rescue base's answer from Yes to No?

Outputs detail/summary/peaks CSV.
"""

from __future__ import annotations

import argparse
import gc
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


def load_model(model_id: str, dtype, device: str):
    from transformers import AutoModelForCausalLM
    print(f"\nLoading {model_id}")
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
def collect_D_final_cache(model, tokenizer, seeds_by_sid: Dict[int, pd.Series], layers: List[int], label: str):
    """Collect D-prompt final-token activations from one donor model."""
    cache: Dict[Tuple[int, int], torch.Tensor] = {}
    for sid, row in tqdm(seeds_by_sid.items(), desc=f"collect {label} D final activations"):
        toks = build_tokenized_scenario(row, tokenizer)
        tokD = toks["D"]
        input_ids = torch.tensor([tokD.input_ids], dtype=torch.long, device=first_device(model))
        out = model(input_ids=input_ids, output_hidden_states=True, use_cache=False)
        pos = tokD.final_answer_idx
        for layer in layers:
            # hidden_states[layer + 1] is residual stream after transformer block `layer`.
            act = out.hidden_states[layer + 1][0, pos, :].detach().cpu().to(torch.float16)
            cache[(sid, layer)] = act
        del out, input_ids
    return cache


@torch.no_grad()
def forward_margin_D(receiver_model, tokenizer, tokD, yes_ids, no_ids, patch_layer=None, patch_act_cpu=None):
    """
    Run receiver model on D prompt. Optionally replace final-token activation at one layer.
    """
    input_ids = torch.tensor([tokD.input_ids], dtype=torch.long, device=first_device(receiver_model))
    handle = None

    if patch_layer is not None:
        final_pos = tokD.final_answer_idx

        def hook_fn(module, inputs, output):
            if isinstance(output, tuple):
                h = output[0].clone()
                extra = output[1:]
                h[:, final_pos, :] = patch_act_cpu.to(device=h.device, dtype=h.dtype).unsqueeze(0)
                return (h,) + extra
            h = output.clone()
            h[:, final_pos, :] = patch_act_cpu.to(device=h.device, dtype=h.dtype).unsqueeze(0)
            return h

        handle = receiver_model.model.layers[int(patch_layer)].register_forward_hook(hook_fn)

    try:
        out = receiver_model(input_ids=input_ids, use_cache=False)
    finally:
        if handle is not None:
            handle.remove()

    logits_last = out.logits[0, -1, :]
    y, n, m = yes_no_margin(logits_last, yes_ids, no_ids)
    del out, input_ids
    return y, n, m


def run_destructive_base_to_ci(
    ci_model,
    tokenizer,
    seeds_by_sid: Dict[int, pd.Series],
    base_cache: Dict[Tuple[int, int], torch.Tensor],
    layers: List[int],
    yes_ids,
    no_ids,
):
    """Patch base D final activations into CI D forward passes."""
    rows = []
    original_cache: Dict[int, Tuple[float, float, float]] = {}

    for sid, row in tqdm(seeds_by_sid.items(), desc="destructive: patch base D final into CI D"):
        toks = build_tokenized_scenario(row, tokenizer)
        tokD = toks["D"]

        if sid not in original_cache:
            original_cache[sid] = forward_margin_D(ci_model, tokenizer, tokD, yes_ids, no_ids)
        oy, on, om = original_cache[sid]
        original_decision = decision_from_margin(om)

        for layer in layers:
            act = base_cache[(sid, layer)]
            py, pn, pm = forward_margin_D(
                ci_model,
                tokenizer,
                tokD,
                yes_ids,
                no_ids,
                patch_layer=layer,
                patch_act_cpu=act,
            )
            patched_decision = decision_from_margin(pm)
            effect = pm - om  # positive means more Yes / less No
            rows.append({
                "experiment": "baseD_final_to_ciD_final_destructive",
                "pair": "base_to_ci_same_D",
                "source_model": "base",
                "receiver_model": "ci",
                "scenario_id": sid,
                "source_version": "D",
                "target_version": "D",
                "site": "final",
                "layer": layer,
                "target_expected": "No",
                "original_yes_logit": oy,
                "original_no_logit": on,
                "original_margin": om,
                "original_decision": original_decision,
                "patched_yes_logit": py,
                "patched_no_logit": pn,
                "patched_margin": pm,
                "patched_decision": patched_decision,
                "effect": effect,
                # Destructive metric: positive means base patch pushed CI D toward Yes.
                "destructive_effect": effect,
                "rescue_effect": float("nan"),
                "flipped": patched_decision != original_decision,
                "destroyed_no": (original_decision == "No" and patched_decision == "Yes"),
                "rescued_yes": False,
                "patched_is_yes": patched_decision == "Yes",
                "patched_is_no": patched_decision == "No",
            })
    return rows


def run_rescue_ci_to_base(
    base_model,
    tokenizer,
    seeds_by_sid: Dict[int, pd.Series],
    ci_cache: Dict[Tuple[int, int], torch.Tensor],
    layers: List[int],
    yes_ids,
    no_ids,
):
    """Patch CI D final activations into base D forward passes."""
    rows = []
    original_cache: Dict[int, Tuple[float, float, float]] = {}

    for sid, row in tqdm(seeds_by_sid.items(), desc="rescue: patch CI D final into base D"):
        toks = build_tokenized_scenario(row, tokenizer)
        tokD = toks["D"]

        if sid not in original_cache:
            original_cache[sid] = forward_margin_D(base_model, tokenizer, tokD, yes_ids, no_ids)
        oy, on, om = original_cache[sid]
        original_decision = decision_from_margin(om)

        for layer in layers:
            act = ci_cache[(sid, layer)]
            py, pn, pm = forward_margin_D(
                base_model,
                tokenizer,
                tokD,
                yes_ids,
                no_ids,
                patch_layer=layer,
                patch_act_cpu=act,
            )
            patched_decision = decision_from_margin(pm)
            effect = pm - om  # negative means more No / rescue direction
            rows.append({
                "experiment": "ciD_final_to_baseD_final_rescue",
                "pair": "ci_to_base_same_D",
                "source_model": "ci",
                "receiver_model": "base",
                "scenario_id": sid,
                "source_version": "D",
                "target_version": "D",
                "site": "final",
                "layer": layer,
                "target_expected": "No",
                "original_yes_logit": oy,
                "original_no_logit": on,
                "original_margin": om,
                "original_decision": original_decision,
                "patched_yes_logit": py,
                "patched_no_logit": pn,
                "patched_margin": pm,
                "patched_decision": patched_decision,
                "effect": effect,
                "destructive_effect": float("nan"),
                # Rescue metric: positive means CI patch pushed base D toward No.
                "rescue_effect": -effect,
                "flipped": patched_decision != original_decision,
                "destroyed_no": False,
                "rescued_yes": (original_decision == "Yes" and patched_decision == "No"),
                "patched_is_yes": patched_decision == "Yes",
                "patched_is_no": patched_decision == "No",
            })
    return rows


def summarize(detail: pd.DataFrame):
    summary = detail.groupby(["experiment", "pair", "layer"], as_index=False).agg(
        n=("scenario_id", "nunique"),
        mean_original_margin=("original_margin", "mean"),
        mean_patched_margin=("patched_margin", "mean"),
        mean_effect=("effect", "mean"),
        mean_destructive_effect=("destructive_effect", "mean"),
        mean_rescue_effect=("rescue_effect", "mean"),
        flip_rate=("flipped", "mean"),
        destroyed_no_rate=("destroyed_no", "mean"),
        rescued_yes_rate=("rescued_yes", "mean"),
        patched_yes_rate=("patched_is_yes", "mean"),
        patched_no_rate=("patched_is_no", "mean"),
    )

    peak_rows = []
    for exp, g in summary.groupby("experiment"):
        if "destructive" in exp:
            gg = g.sort_values(["destroyed_no_rate", "mean_destructive_effect"], ascending=[False, False])
        elif "rescue" in exp:
            gg = g.sort_values(["rescued_yes_rate", "mean_rescue_effect"], ascending=[False, False])
        else:
            gg = g.sort_values(["flip_rate", "mean_effect"], ascending=[False, False])
        peak_rows.append(gg.iloc[0].to_dict())
    peaks = pd.DataFrame(peak_rows)
    return summary, peaks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--eligibility", required=True)
    ap.add_argument("--flag", default="improve_D")
    ap.add_argument("--mode", default="both", choices=["destructive", "rescue", "both"],
                    help="destructive=base D -> CI D, rescue=CI D -> base D, both=run both")
    ap.add_argument("--layers", default="18-27")
    ap.add_argument("--dtype", default="float16", choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu", choices=["cuda", "cpu"])
    ap.add_argument("--tokenizer", default=BASE_MODEL)
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--ci-model", default=CI_MODEL)
    ap.add_argument("--max-scenarios", type=int, default=None)
    ap.add_argument("--out-detail", required=True)
    ap.add_argument("--out-summary", required=True)
    ap.add_argument("--out-peaks", required=True)
    args = ap.parse_args()

    from transformers import AutoTokenizer

    layers = parse_layers(args.layers)
    dtype = dtype_from_name(args.dtype)

    seeds = load_seeds(args.seeds)
    elig = pd.read_csv(args.eligibility)
    elig = elig[elig[args.flag].astype(bool)].copy()
    keep = set(elig["scenario_id"].astype(int))
    seeds = seeds[seeds["scenario_id"].astype(int).isin(keep)].copy()
    if args.max_scenarios is not None:
        seeds = seeds.head(args.max_scenarios).copy()
    seeds_by_sid = {int(r["scenario_id"]): r for _, r in seeds.iterrows()}

    print(f"Scenarios: {len(seeds_by_sid)}")
    print(f"Layers: {layers}")
    print(f"Mode: {args.mode}")
    print("Experiments:")
    if args.mode in ("destructive", "both"):
        print("  destructive: base D final -> CI D final")
    if args.mode in ("rescue", "both"):
        print("  rescue:      CI D final -> base D final")

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)
    yes_ids, no_ids = get_yes_no_token_ids(tokenizer)

    all_rows = []

    # Collect donor cache(s). We load one model at a time to reduce GPU memory pressure.
    base_cache = None
    ci_cache = None

    if args.mode in ("destructive", "both"):
        base = load_model(args.base_model, dtype, args.device)
        base_cache = collect_D_final_cache(base, tokenizer, seeds_by_sid, layers, label="base")
        free_model(base)

    if args.mode in ("rescue", "both"):
        ci = load_model(args.ci_model, dtype, args.device)
        ci_cache = collect_D_final_cache(ci, tokenizer, seeds_by_sid, layers, label="CI")

        # If destructive is requested too, use the already-loaded CI as receiver before freeing it.
        if args.mode in ("destructive", "both"):
            all_rows.extend(run_destructive_base_to_ci(ci, tokenizer, seeds_by_sid, base_cache, layers, yes_ids, no_ids))
        free_model(ci)

    # If only destructive was requested, we have not loaded CI yet as receiver.
    if args.mode == "destructive":
        ci = load_model(args.ci_model, dtype, args.device)
        all_rows.extend(run_destructive_base_to_ci(ci, tokenizer, seeds_by_sid, base_cache, layers, yes_ids, no_ids))
        free_model(ci)

    if args.mode in ("rescue", "both"):
        base = load_model(args.base_model, dtype, args.device)
        all_rows.extend(run_rescue_ci_to_base(base, tokenizer, seeds_by_sid, ci_cache, layers, yes_ids, no_ids))
        free_model(base)

    detail = pd.DataFrame(all_rows)
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

    print("\nPeaks:")
    cols = [
        "experiment", "pair", "layer", "n", "mean_original_margin", "mean_patched_margin",
        "mean_effect", "mean_destructive_effect", "mean_rescue_effect",
        "flip_rate", "destroyed_no_rate", "rescued_yes_rate", "patched_no_rate",
    ]
    print(peaks[cols].to_string(index=False))


if __name__ == "__main__":
    main()
