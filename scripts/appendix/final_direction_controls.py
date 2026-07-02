"""
final_direction_controls.py

Controls for the final-token D-A direction result.

Experiments:
  1) D_remove_signed
     Remove projection onto d_L from held-out D prompts at final token.
     Main causal-necessity test (replication of earlier result).

  2) A_remove_signed
     Same signed removal applied to A prompts.
     Checks whether the intervention just destroys normal Yes behavior.

  3) A_remove_positive
     Positive-only projection removal applied to A prompts.
     Since A typically has *negative* projection onto d_L, this should do
     very little. Clean specificity control.

  4) A_add_direction
     Add alpha * train_gap_L * d_L to A prompts.
     Sufficiency: does pushing A along the D direction move it toward No?

Direction:
  For each layer L:
    d_L  = mean(h_D_final[L]) - mean(h_A_final[L])
    d_L  = d_L / ||d_L||
    mu_L = mean over A and D train final states

Projection removal:
    h_new = h - alpha * ((h - mu_L) @ d_L) * d_L

Direction addition:
    h_new = h + alpha * train_gap_L * d_L

Usage (smoke test):
  python scripts/final_direction_controls.py \\
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \\
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \\
    --filter-col patch_final_AD \\
    --out-dir results/clean304/final_direction_controls_smoke \\
    --dtype float16 \\
    --device cuda \\
    --layers 18-27 \\
    --alphas 0.25,0.5,1.0 \\
    --max-test 10 \\
    --random-controls 1

Full run:
  python scripts/final_direction_controls.py \\
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \\
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \\
    --filter-col patch_final_AD \\
    --out-dir results/clean304/final_direction_controls \\
    --dtype float16 \\
    --device cuda \\
    --layers 18-27 \\
    --alphas 0.25,0.5,1.0,1.5 \\
    --random-controls 3
"""

from __future__ import annotations

import argparse
import gc
import random
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import torch
from tqdm import tqdm

from ci_dataset import load_seeds, make_variants


CI_MODEL = "huseyinatahaninan/Qwen2.5-7B-Instruct-CI"

YES_VARIANTS = ["Yes", " Yes", "yes", " yes", "YES", " YES"]
NO_VARIANTS  = ["No",  " No",  "no",  " no",  "NO",  " NO"]


# ----------------------- Yes/No helpers -----------------------

def get_yes_no_token_ids(tokenizer) -> Tuple[List[int], List[int]]:
    def collect(words):
        out = []
        for w in words:
            ids = tokenizer.encode(w, add_special_tokens=False)
            if len(ids) == 1:
                out.append(ids[0])
        return list(dict.fromkeys(out))

    yes_ids = collect(YES_VARIANTS)
    no_ids  = collect(NO_VARIANTS)
    if not yes_ids or not no_ids:
        raise RuntimeError(f"Could not find one-token Yes/No IDs: yes={yes_ids}, no={no_ids}")
    return yes_ids, no_ids


def yes_no_margin(logits_last, yes_ids: List[int], no_ids: List[int]):
    yes_logit = max(logits_last[i].item() for i in yes_ids)
    no_logit  = max(logits_last[i].item() for i in no_ids)
    margin = yes_logit - no_logit
    decision = "Yes" if margin > 0 else "No"
    return float(yes_logit), float(no_logit), float(margin), decision


# ----------------------- Model helpers -----------------------

def get_input_device(model):
    return model.get_input_embeddings().weight.device


def get_decoder_layers(model):
    if hasattr(model, "model") and hasattr(model.model, "layers"):
        return model.model.layers
    if hasattr(model, "transformer") and hasattr(model.transformer, "h"):
        return model.transformer.h
    raise RuntimeError("Could not find transformer decoder layers.")


def load_model_and_tokenizer(model_id: str, device: str, dtype):
    from transformers import AutoTokenizer, AutoModelForCausalLM

    print(f"Loading tokenizer: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id)

    print(f"Loading model: {model_id}")
    if device == "cuda":
        model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=dtype, device_map="auto", low_cpu_mem_usage=True,
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=dtype, low_cpu_mem_usage=True,
        )
        model = model.to(device)

    model.eval()
    print("Input device:", get_input_device(model))
    print("Number of layers:", len(get_decoder_layers(model)))
    return model, tokenizer


# ----------------------- argument helpers -----------------------

def parse_layers(layer_arg: str, n_layers: int) -> List[int]:
    if layer_arg == "all":
        return list(range(n_layers))
    if "-" in layer_arg:
        a, b = layer_arg.split("-")
        layers = list(range(int(a), int(b) + 1))
    else:
        layers = [int(x.strip()) for x in layer_arg.split(",") if x.strip()]
    bad = [x for x in layers if x < 0 or x >= n_layers]
    if bad:
        raise ValueError(f"Invalid layers {bad}. Model has layers 0..{n_layers - 1}")
    return layers


def parse_alphas(alpha_arg: str) -> List[float]:
    return [float(x.strip()) for x in alpha_arg.split(",") if x.strip()]


def normalize(x: torch.Tensor, eps: float = 1e-8):
    return x / (x.norm(dim=-1, keepdim=True) + eps)


# ----------------------- dataset filtering -----------------------

def filter_seeds_by_eligibility(seeds: pd.DataFrame, eligibility_path: str, filter_col: str):
    elig = pd.read_csv(eligibility_path)
    if "scenario_id" not in elig.columns:
        raise ValueError("Eligibility file must contain scenario_id column.")
    if filter_col not in elig.columns:
        raise ValueError(
            f"Column {filter_col} not found.\n"
            f"Available columns: {list(elig.columns)}"
        )
    keep_ids = set(
        elig.loc[elig[filter_col].astype(bool), "scenario_id"].astype(int).tolist()
    )
    out = seeds[seeds["scenario_id"].astype(int).isin(keep_ids)].copy()
    print(f"Eligibility filter: {filter_col}")
    print(f"Kept scenarios: {len(out)} / {len(seeds)}")
    if len(out) < 20:
        raise RuntimeError("Too few scenarios after eligibility filtering.")
    return out


def split_train_test(sids: List[int], train_frac: float, seed: int):
    rng = random.Random(seed)
    sids = list(sids)
    rng.shuffle(sids)
    n_train = int(round(len(sids) * train_frac))
    return sorted(sids[:n_train]), sorted(sids[n_train:])


# ----------------------- hidden-state collection -----------------------

@torch.no_grad()
def forward_collect_final_hiddens(model, tokenizer, text: str, yes_ids, no_ids):
    input_device = get_input_device(model)
    enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
    input_ids = enc["input_ids"].to(input_device)

    out = model(input_ids=input_ids, output_hidden_states=True, use_cache=False)

    hidden_by_layer = torch.stack(
        [h[0, -1, :].detach().float().cpu() for h in out.hidden_states[1:]],
        dim=0,
    )

    logits_last = out.logits[0, -1, :]
    y, n, margin, decision = yes_no_margin(logits_last, yes_ids, no_ids)
    return hidden_by_layer, {
        "yes_logit": y, "no_logit": n,
        "margin": margin, "decision": decision,
        "prompt_len_tokens": int(input_ids.shape[1]),
    }


def collect_A_D_cache(model, tokenizer, seeds: pd.DataFrame, yes_ids, no_ids):
    cache: Dict[int, Dict[str, Dict]] = {}
    for _, row in tqdm(seeds.iterrows(), total=len(seeds), desc="Collecting A/D activations"):
        sid = int(row["scenario_id"])
        variants = make_variants(row, tokenizer=tokenizer)
        if "A" not in variants or "D" not in variants:
            raise RuntimeError(f"Scenario {sid} missing A or D variant.")
        cache[sid] = {}
        for version in ["A", "D"]:
            variant = variants[version]
            hidden, info = forward_collect_final_hiddens(
                model=model, tokenizer=tokenizer, text=variant.text,
                yes_ids=yes_ids, no_ids=no_ids,
            )
            cache[sid][version] = {
                "hidden": hidden, "text": variant.text,
                "expected": variant.expected, "condition": variant.condition,
                "margin": info["margin"], "decision": info["decision"],
                "yes_logit": info["yes_logit"], "no_logit": info["no_logit"],
                "prompt_len_tokens": info["prompt_len_tokens"],
            }
    return cache


# ----------------------- direction construction -----------------------

def build_D_minus_A_directions(cache: Dict[int, Dict], train_sids: List[int]):
    """Returns directions [n_layers, d], mus [n_layers, d], train_gaps [n_layers]."""
    A = torch.stack([cache[sid]["A"]["hidden"] for sid in train_sids], dim=0)
    D = torch.stack([cache[sid]["D"]["hidden"] for sid in train_sids], dim=0)

    A_mean = A.mean(dim=0)
    D_mean = D.mean(dim=0)

    directions = normalize(D_mean - A_mean)
    mus = torch.cat([A, D], dim=0).mean(dim=0)

    train_gaps = []
    for L in range(directions.shape[0]):
        d = directions[L]; mu = mus[L]
        A_scores = ((A[:, L, :] - mu) * d).sum(dim=-1)
        D_scores = ((D[:, L, :] - mu) * d).sum(dim=-1)
        train_gaps.append(float((D_scores.mean() - A_scores.mean()).item()))
    train_gaps = torch.tensor(train_gaps, dtype=torch.float32)
    return directions, mus, train_gaps


def random_unit_vector_like(d: torch.Tensor, seed: int):
    gen = torch.Generator(device="cpu"); gen.manual_seed(seed)
    r = torch.randn(d.shape, generator=gen)
    return r / (r.norm() + 1e-8)


# ----------------------- intervention hook -----------------------

def make_final_token_intervention_hook(
    direction_cpu: torch.Tensor,
    mu_cpu: torch.Tensor,
    alpha: float,
    mode: str,
    train_gap: float | None = None,
):
    """
    mode:
      remove_signed:   h_new = h - alpha * ((h - mu) @ d) * d
      remove_positive: h_new = h - alpha * max(((h - mu) @ d), 0) * d
      add_gap:         h_new = h + alpha * train_gap * d
    """
    assert mode in {"remove_signed", "remove_positive", "add_gap"}

    def hook(module, inputs, output):
        if isinstance(output, tuple):
            hidden = output[0]
            rest = output[1:]
        else:
            hidden = output
            rest = None

        d  = direction_cpu.to(device=hidden.device, dtype=hidden.dtype)
        mu = mu_cpu.to(device=hidden.device, dtype=hidden.dtype)

        h_final = hidden[:, -1, :]

        if mode == "remove_signed":
            coeff = ((h_final - mu) * d).sum(dim=-1, keepdim=True)
            new_final = h_final - alpha * coeff * d

        elif mode == "remove_positive":
            coeff = ((h_final - mu) * d).sum(dim=-1, keepdim=True)
            coeff = torch.clamp(coeff, min=0.0)
            new_final = h_final - alpha * coeff * d

        elif mode == "add_gap":
            if train_gap is None:
                raise RuntimeError("train_gap required for add_gap mode.")
            new_final = h_final + alpha * float(train_gap) * d

        else:
            raise RuntimeError(f"Bad mode: {mode}")

        hidden_new = hidden.clone()
        hidden_new[:, -1, :] = new_final

        if rest is not None:
            return (hidden_new,) + rest
        return hidden_new

    return hook


@torch.no_grad()
def forward_with_intervention(
    model, tokenizer, text: str, yes_ids, no_ids,
    layer: int, direction: torch.Tensor, mu: torch.Tensor,
    alpha: float, mode: str, train_gap: float | None = None,
):
    layers = get_decoder_layers(model)
    input_device = get_input_device(model)

    hook = make_final_token_intervention_hook(
        direction_cpu=direction, mu_cpu=mu, alpha=alpha,
        mode=mode, train_gap=train_gap,
    )
    handle = layers[layer].register_forward_hook(hook)
    try:
        enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
        input_ids = enc["input_ids"].to(input_device)
        out = model(input_ids=input_ids, use_cache=False)
        logits_last = out.logits[0, -1, :]
        y, n, margin, decision = yes_no_margin(logits_last, yes_ids, no_ids)
        return {
            "yes_logit": y, "no_logit": n, "margin": margin,
            "decision": decision, "prompt_len_tokens": int(input_ids.shape[1]),
        }
    finally:
        handle.remove()


# ----------------------- main control runner -----------------------

EXPERIMENTS = [
    # Main replication: remove direction from D.
    {"experiment": "D_remove_signed",   "prompt_version": "D", "mode": "remove_signed",   "uses_train_gap": False},

    # Specificity control 1: same signed removal on A.
    {"experiment": "A_remove_signed",   "prompt_version": "A", "mode": "remove_signed",   "uses_train_gap": False},

    # Specificity control 2: positive-only removal on A.
    {"experiment": "A_remove_positive", "prompt_version": "A", "mode": "remove_positive", "uses_train_gap": False},

    # Sufficiency control: add D-A direction to A.
    {"experiment": "A_add_direction",   "prompt_version": "A", "mode": "add_gap",         "uses_train_gap": True},
]


def run_controls(
    model, tokenizer, cache, test_sids,
    directions, mus, train_gaps,
    layers_to_run, alphas,
    yes_ids, no_ids,
    random_controls, max_test,
):
    test_sids_eval = test_sids[:max_test] if max_test is not None else test_sids
    detail_rows = []

    for L in tqdm(layers_to_run, desc="Layers"):
        d = directions[L]; mu = mus[L]; gap = float(train_gaps[L])
        for alpha in alphas:
            for exp in EXPERIMENTS:
                prompt_version = exp["prompt_version"]
                mode = exp["mode"]
                tg = gap if exp["uses_train_gap"] else None

                # Real direction
                for sid in test_sids_eval:
                    normal_margin = float(cache[sid][prompt_version]["margin"])
                    normal_decision = cache[sid][prompt_version]["decision"]
                    out = forward_with_intervention(
                        model=model, tokenizer=tokenizer,
                        text=cache[sid][prompt_version]["text"],
                        yes_ids=yes_ids, no_ids=no_ids,
                        layer=L, direction=d, mu=mu,
                        alpha=alpha, mode=mode, train_gap=tg,
                    )
                    new_margin = float(out["margin"])
                    new_decision = out["decision"]
                    detail_rows.append({
                        "layer": L, "alpha": alpha, "scenario_id": sid,
                        "experiment": exp["experiment"],
                        "prompt_version": prompt_version,
                        "control_type": "real_direction", "mode": mode,
                        "normal_margin": normal_margin,
                        "intervened_margin": new_margin,
                        "delta_margin": new_margin - normal_margin,
                        "delta_toward_yes": new_margin - normal_margin,
                        "delta_toward_no": normal_margin - new_margin,
                        "normal_decision": normal_decision,
                        "intervened_decision": new_decision,
                        "no_to_yes_flip": normal_decision == "No"  and new_decision == "Yes",
                        "yes_to_no_flip": normal_decision == "Yes" and new_decision == "No",
                    })

                # Random controls
                for rc in range(random_controls):
                    rd = random_unit_vector_like(d, seed=1_000_000 + 10_000 * L + 100 * rc)
                    for sid in test_sids_eval:
                        normal_margin = float(cache[sid][prompt_version]["margin"])
                        normal_decision = cache[sid][prompt_version]["decision"]
                        out = forward_with_intervention(
                            model=model, tokenizer=tokenizer,
                            text=cache[sid][prompt_version]["text"],
                            yes_ids=yes_ids, no_ids=no_ids,
                            layer=L, direction=rd, mu=mu,
                            alpha=alpha, mode=mode, train_gap=tg,
                        )
                        new_margin = float(out["margin"])
                        new_decision = out["decision"]
                        detail_rows.append({
                            "layer": L, "alpha": alpha, "scenario_id": sid,
                            "experiment": exp["experiment"],
                            "prompt_version": prompt_version,
                            "control_type": f"random_direction_{rc}", "mode": mode,
                            "normal_margin": normal_margin,
                            "intervened_margin": new_margin,
                            "delta_margin": new_margin - normal_margin,
                            "delta_toward_yes": new_margin - normal_margin,
                            "delta_toward_no": normal_margin - new_margin,
                            "normal_decision": normal_decision,
                            "intervened_decision": new_decision,
                            "no_to_yes_flip": normal_decision == "No"  and new_decision == "Yes",
                            "yes_to_no_flip": normal_decision == "Yes" and new_decision == "No",
                        })

    detail_df = pd.DataFrame(detail_rows)
    summary_df = summarize_controls(detail_df)
    return detail_df, summary_df


def summarize_controls(detail_df: pd.DataFrame):
    rows = []
    for (exp, layer, alpha, control_group), g in detail_df.groupby(
        ["experiment", "layer", "alpha", "control_type"]
    ):
        rows.append({
            "experiment": exp, "layer": int(layer),
            "alpha": float(alpha), "control_type": control_group,
            "n": int(len(g)),
            "normal_margin_mean": g["normal_margin"].mean(),
            "intervened_margin_mean": g["intervened_margin"].mean(),
            "delta_margin_mean": g["delta_margin"].mean(),
            "delta_toward_yes_mean": g["delta_toward_yes"].mean(),
            "delta_toward_no_mean": g["delta_toward_no"].mean(),
            "no_to_yes_flips": int(g["no_to_yes_flip"].sum()),
            "no_to_yes_flip_rate": g["no_to_yes_flip"].mean(),
            "yes_to_no_flips": int(g["yes_to_no_flip"].sum()),
            "yes_to_no_flip_rate": g["yes_to_no_flip"].mean(),
        })
    return pd.DataFrame(rows)


# ----------------------- main -----------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--eligibility", required=True)
    parser.add_argument("--filter-col", default="patch_final_AD")
    parser.add_argument("--out-dir", required=True)

    parser.add_argument("--model", default=CI_MODEL)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu",
                        choices=["cuda", "cpu"])
    parser.add_argument("--dtype", default="float16",
                        choices=["bfloat16", "float16", "float32"])

    parser.add_argument("--train-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--layers", default="18-27")
    parser.add_argument("--alphas", default="0.25,0.5,1.0,1.5")
    parser.add_argument("--random-controls", type=int, default=3)
    parser.add_argument("--max-test", type=int, default=None)

    args = parser.parse_args()

    dtype = {
        "bfloat16": torch.bfloat16,
        "float16":  torch.float16,
        "float32":  torch.float32,
    }[args.dtype]

    alphas = parse_alphas(args.alphas)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("FINAL DIRECTION CONTROLS")
    print("=" * 80)

    print("\nLoading seeds...")
    seeds = load_seeds(args.seeds)

    print("\nFiltering seeds...")
    seeds = filter_seeds_by_eligibility(seeds, args.eligibility, args.filter_col)

    sids = sorted(seeds["scenario_id"].astype(int).tolist())
    train_sids, test_sids = split_train_test(sids, args.train_frac, args.seed)

    print(f"\nTrain scenarios: {len(train_sids)}")
    print(f"Test scenarios:  {len(test_sids)}")

    pd.DataFrame({
        "scenario_id": train_sids + test_sids,
        "split": ["train"] * len(train_sids) + ["test"] * len(test_sids),
    }).to_csv(out_dir / "split.csv", index=False)

    model, tokenizer = load_model_and_tokenizer(args.model, args.device, dtype)
    n_layers = len(get_decoder_layers(model))
    layers_to_run = parse_layers(args.layers, n_layers)
    print(f"\nLayers to run: {layers_to_run}")
    print(f"Alphas: {alphas}")

    yes_ids, no_ids = get_yes_no_token_ids(tokenizer)
    print("Yes token IDs:", yes_ids)
    print("No token IDs:",  no_ids)

    print("\nCollecting A/D hidden states...")
    cache = collect_A_D_cache(model, tokenizer, seeds, yes_ids, no_ids)

    print("\nBuilding D-A final-token directions...")
    directions, mus, train_gaps = build_D_minus_A_directions(cache, train_sids)

    torch.save({
        "directions": directions, "mus": mus, "train_gaps": train_gaps,
        "train_sids": train_sids, "test_sids": test_sids,
        "layers_to_run": layers_to_run, "alphas": alphas,
        "filter_col": args.filter_col,
    }, out_dir / "directions_mus_gaps.pt")

    print("\nRunning controls...")
    detail_df, summary_df = run_controls(
        model=model, tokenizer=tokenizer, cache=cache,
        test_sids=test_sids, directions=directions, mus=mus,
        train_gaps=train_gaps,
        layers_to_run=layers_to_run, alphas=alphas,
        yes_ids=yes_ids, no_ids=no_ids,
        random_controls=args.random_controls, max_test=args.max_test,
    )

    detail_df.to_csv(out_dir / "controls_detail.csv", index=False)
    summary_df.to_csv(out_dir / "controls_summary.csv", index=False)

    print("\nSaved:")
    for fn in ["split.csv", "directions_mus_gaps.pt", "controls_detail.csv", "controls_summary.csv"]:
        print(" ", out_dir / fn)

    real = summary_df[summary_df["control_type"] == "real_direction"].copy()

    print("\nD_remove_signed: top No->Yes flip rates")
    print(
        real[real["experiment"] == "D_remove_signed"]
        .sort_values(["no_to_yes_flip_rate", "delta_toward_yes_mean"], ascending=False)
        .head(20).to_string(index=False)
    )

    print("\nA_remove_signed: top Yes->No flip rates")
    print(
        real[real["experiment"] == "A_remove_signed"]
        .sort_values(["yes_to_no_flip_rate", "delta_toward_no_mean"], ascending=False)
        .head(20).to_string(index=False)
    )

    print("\nA_remove_positive: top Yes->No flip rates")
    print(
        real[real["experiment"] == "A_remove_positive"]
        .sort_values(["yes_to_no_flip_rate", "delta_toward_no_mean"], ascending=False)
        .head(20).to_string(index=False)
    )

    print("\nA_add_direction: top Yes->No flip rates")
    print(
        real[real["experiment"] == "A_add_direction"]
        .sort_values(["yes_to_no_flip_rate", "delta_toward_no_mean"], ascending=False)
        .head(20).to_string(index=False)
    )

    del model, tokenizer
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
