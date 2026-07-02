#!/usr/bin/env python3
"""
activation_similarity.py

Compare base vs CI-Qwen activations on the same CI scenarios.

This script reports two things:
  1. raw activation cosine: cos(h_base(version), h_ci(version))
  2. contrast-direction cosine: cos((h_base(B/C/D)-h_base(A)),
                                    (h_ci(B/C/D)-h_ci(A)))

The contrast-direction cosine is the more meaningful diagnostic. Raw cosine can
be high simply because the two models share architecture/checkpoint and receive
nearly identical prompts.

Expected use:
  python scripts/activation_similarity.py \
    --seeds data/final/curated_candidate_pool_source_capped_for_patching.csv \
    --eligibility data/final/curated_improvement_eligibility_source_capped.csv \
    --subset D \
    --layers 0-26 \
    --dtype float16 \
    --out-prefix results/source_capped_D_activation_similarity

Outputs:
  <out-prefix>_raw.csv
  <out-prefix>_raw_summary.csv
  <out-prefix>_contrast.csv
  <out-prefix>_contrast_summary.csv
"""

from __future__ import annotations

import argparse
import gc
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import torch
import torch.nn.functional as F
from tqdm import tqdm

from ci_dataset import load_seeds, build_tokenized_scenario

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
CI_MODEL = "huseyinatahaninan/Qwen2.5-7B-Instruct-CI"

SITES = ["recipient_last", "purpose_last", "final"]
VERSIONS = ["A", "B", "C", "D"]
CONTRASTS = {
    "AB_B_minus_A": ("B", "A", "improve_B"),
    "AC_C_minus_A": ("C", "A", "improve_C"),
    "AD_D_minus_A": ("D", "A", "improve_D"),
}


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


def site_index(tok, site: str) -> int:
    if site == "recipient_last":
        return tok.recipient_last_idx
    if site == "purpose_last":
        return tok.purpose_last_idx
    if site == "final":
        return tok.final_answer_idx
    raise ValueError(f"Unknown site: {site}")


def filter_seed_rows(seeds: pd.DataFrame, eligibility: pd.DataFrame | None, subset: str) -> pd.DataFrame:
    if eligibility is None or subset == "all":
        return seeds.copy()

    flag = {
        "B": "improve_B",
        "C": "improve_C",
        "D": "improve_D",
        "ABC": None,
    }[subset]

    if subset == "ABC":
        keep = eligibility[
            eligibility.get("improve_B", False) |
            eligibility.get("improve_C", False) |
            eligibility.get("improve_D", False)
        ]["scenario_id"]
    else:
        if flag not in eligibility.columns:
            raise ValueError(f"Eligibility file missing required column {flag!r}")
        keep = eligibility[eligibility[flag].astype(bool)]["scenario_id"]

    keep = set(int(x) for x in keep)
    return seeds[seeds["scenario_id"].astype(int).isin(keep)].copy()


@torch.no_grad()
def collect_model_activations(
    model_id: str,
    seeds: pd.DataFrame,
    tokenizer,
    layers: List[int],
    dtype,
    device: str,
) -> Dict[Tuple[int, str, str, int], torch.Tensor]:
    """Return CPU float16 activations keyed by (scenario_id, version, site, layer)."""
    from transformers import AutoModelForCausalLM

    name = short_name(model_id)
    print(f"\n[{name}] loading model: {model_id}")
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

    acts: Dict[Tuple[int, str, str, int], torch.Tensor] = {}

    for _, row in tqdm(seeds.iterrows(), total=len(seeds), desc=f"collect {name}"):
        sid = int(row["scenario_id"])
        toks = build_tokenized_scenario(row, tokenizer)
        for version in VERSIONS:
            tok = toks[version]
            input_ids = torch.tensor([tok.input_ids], dtype=torch.long, device=first_device(model))
            out = model(input_ids=input_ids, output_hidden_states=True, use_cache=False)
            # hidden_states[0] is embedding output. hidden_states[layer+1] is post-block layer.
            for layer in layers:
                hs = out.hidden_states[layer + 1][0]  # [seq, hidden]
                for site in SITES:
                    idx = site_index(tok, site)
                    acts[(sid, version, site, layer)] = hs[idx].detach().cpu().to(torch.float16)

            del out, input_ids

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return acts


def cosine(a: torch.Tensor, b: torch.Tensor) -> float:
    return float(F.cosine_similarity(a.float(), b.float(), dim=0).item())


def norm(x: torch.Tensor) -> float:
    return float(x.float().norm().item())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--eligibility", default=None)
    ap.add_argument("--subset", default="D", choices=["B", "C", "D", "ABC", "all"],
                    help="Which scenario subset to analyze. D = improve_D, etc.")
    ap.add_argument("--layers", default="0-26")
    ap.add_argument("--dtype", default="float16", choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu", choices=["cuda", "cpu"])
    ap.add_argument("--tokenizer", default=BASE_MODEL)
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--ci-model", default=CI_MODEL)
    ap.add_argument("--max-scenarios", type=int, default=None)
    ap.add_argument("--out-prefix", required=True)
    args = ap.parse_args()

    from transformers import AutoTokenizer

    layers = parse_layers(args.layers)
    dtype = dtype_from_name(args.dtype)

    seeds = load_seeds(args.seeds)
    eligibility = pd.read_csv(args.eligibility) if args.eligibility else None
    seeds = filter_seed_rows(seeds, eligibility, args.subset)
    seeds = seeds.sort_values("scenario_id").reset_index(drop=True)
    if args.max_scenarios is not None:
        seeds = seeds.head(args.max_scenarios).copy()

    print(f"Loaded {len(seeds)} scenarios for subset={args.subset}")
    print(f"Layers: {layers[0]}..{layers[-1]} ({len(layers)} layers)")

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)

    base_acts = collect_model_activations(args.base_model, seeds, tokenizer, layers, dtype, args.device)
    ci_acts = collect_model_activations(args.ci_model, seeds, tokenizer, layers, dtype, args.device)

    raw_rows = []
    for _, row in seeds.iterrows():
        sid = int(row["scenario_id"])
        for version in VERSIONS:
            for site in SITES:
                for layer in layers:
                    b = base_acts[(sid, version, site, layer)]
                    c = ci_acts[(sid, version, site, layer)]
                    raw_rows.append({
                        "scenario_id": sid,
                        "version": version,
                        "site": site,
                        "layer": layer,
                        "cosine_base_ci": cosine(b, c),
                        "base_norm": norm(b),
                        "ci_norm": norm(c),
                        "norm_ratio_ci_over_base": norm(c) / max(norm(b), 1e-12),
                    })

    contrast_rows = []
    for _, row in seeds.iterrows():
        sid = int(row["scenario_id"])
        for contrast_name, (pos_v, neg_v, flag_col) in CONTRASTS.items():
            # If an eligibility file is present, only compute contrasts relevant for this row.
            if eligibility is not None and flag_col in eligibility.columns:
                eg = eligibility[eligibility["scenario_id"].astype(int) == sid]
                if len(eg) and not bool(eg.iloc[0][flag_col]):
                    continue
            for site in SITES:
                for layer in layers:
                    b_dir = base_acts[(sid, pos_v, site, layer)].float() - base_acts[(sid, neg_v, site, layer)].float()
                    c_dir = ci_acts[(sid, pos_v, site, layer)].float() - ci_acts[(sid, neg_v, site, layer)].float()
                    contrast_rows.append({
                        "scenario_id": sid,
                        "contrast": contrast_name,
                        "site": site,
                        "layer": layer,
                        "direction_cosine_base_ci": cosine(b_dir, c_dir),
                        "base_direction_norm": norm(b_dir),
                        "ci_direction_norm": norm(c_dir),
                        "direction_norm_ratio_ci_over_base": norm(c_dir) / max(norm(b_dir), 1e-12),
                    })

    raw_df = pd.DataFrame(raw_rows)
    contrast_df = pd.DataFrame(contrast_rows)

    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    raw_path = f"{args.out_prefix}_raw.csv"
    raw_sum_path = f"{args.out_prefix}_raw_summary.csv"
    contrast_path = f"{args.out_prefix}_contrast.csv"
    contrast_sum_path = f"{args.out_prefix}_contrast_summary.csv"

    raw_df.to_csv(raw_path, index=False)
    raw_summary = raw_df.groupby(["version", "site", "layer"], as_index=False).agg(
        n=("cosine_base_ci", "size"),
        mean_cosine=("cosine_base_ci", "mean"),
        median_cosine=("cosine_base_ci", "median"),
        std_cosine=("cosine_base_ci", "std"),
        mean_base_norm=("base_norm", "mean"),
        mean_ci_norm=("ci_norm", "mean"),
        mean_norm_ratio=("norm_ratio_ci_over_base", "mean"),
    )
    raw_summary.to_csv(raw_sum_path, index=False)

    contrast_df.to_csv(contrast_path, index=False)
    contrast_summary = contrast_df.groupby(["contrast", "site", "layer"], as_index=False).agg(
        n=("direction_cosine_base_ci", "size"),
        mean_direction_cosine=("direction_cosine_base_ci", "mean"),
        median_direction_cosine=("direction_cosine_base_ci", "median"),
        std_direction_cosine=("direction_cosine_base_ci", "std"),
        mean_base_direction_norm=("base_direction_norm", "mean"),
        mean_ci_direction_norm=("ci_direction_norm", "mean"),
        mean_direction_norm_ratio=("direction_norm_ratio_ci_over_base", "mean"),
    )
    contrast_summary.to_csv(contrast_sum_path, index=False)

    print("\nSaved:")
    for p in [raw_path, raw_sum_path, contrast_path, contrast_sum_path]:
        print(" ", p)

    print("\nUseful columns:")
    print("  mean_direction_cosine near 1 => base/CI contextual contrast direction is similar")
    print("  mean_direction_norm_ratio > 1 => CI contrast direction has larger norm")


if __name__ == "__main__":
    main()
