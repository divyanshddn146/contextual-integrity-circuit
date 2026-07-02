"""
mlp_neuron_sufficiency_steer.py

Tests neuron-level sufficiency for the MLP writer neurons.

Previous necessity experiment:
  D prompt normally says No.
  Replace top writer neuron activations with A-mean.
  D flips No -> Yes.

This script:
  A prompt normally says Yes.
  Move top writer neuron activations toward D-mean.
  Test whether A flips Yes -> No.

Smoke:
  python scripts/mlp_neuron_sufficiency_steer.py \
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \
    --filter-col patch_final_AD \
    --out-dir results/clean304/mlp_neuron_sufficiency_smoke \
    --dtype float16 \
    --device cuda \
    --layers 22,20,23 \
    --topks 1,5,10 \
    --alphas 1.0,1.5 \
    --intervention replace \
    --max-test 10 \
    --random-controls 1

Full:
  python scripts/mlp_neuron_sufficiency_steer.py \
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \
    --filter-col patch_final_AD \
    --out-dir results/clean304/mlp_neuron_sufficiency \
    --dtype float16 \
    --device cuda \
    --layers 22,20,23 \
    --topks 1,5,10,20,50 \
    --alphas 0.5,1.0,1.5,2.0 \
    --intervention replace \
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
NO_VARIANTS = ["No", " No", "no", " no", "NO", " NO"]


def get_yes_no_token_ids(tokenizer) -> Tuple[List[int], List[int]]:
    def collect(words):
        ids_out = []
        for w in words:
            ids = tokenizer.encode(w, add_special_tokens=False)
            if len(ids) == 1:
                ids_out.append(ids[0])
        return list(dict.fromkeys(ids_out))

    yes_ids = collect(YES_VARIANTS)
    no_ids = collect(NO_VARIANTS)
    if not yes_ids or not no_ids:
        raise RuntimeError(f"Could not find one-token Yes/No IDs: yes={yes_ids}, no={no_ids}")
    return yes_ids, no_ids


def yes_no_margin(logits_last, yes_ids: List[int], no_ids: List[int]):
    yes_logit = max(logits_last[i].item() for i in yes_ids)
    no_logit = max(logits_last[i].item() for i in no_ids)
    margin = yes_logit - no_logit
    decision = "Yes" if margin > 0 else "No"
    return float(yes_logit), float(no_logit), float(margin), decision


def get_input_device(model):
    return model.get_input_embeddings().weight.device


def get_decoder_layers(model):
    if hasattr(model, "model") and hasattr(model.model, "layers"):
        return model.model.layers
    if hasattr(model, "transformer") and hasattr(model.transformer, "h"):
        return model.transformer.h
    raise RuntimeError("Could not find transformer decoder layers.")


def get_mlp_module(layer_module):
    for name in ["mlp", "feed_forward", "ffn"]:
        if hasattr(layer_module, name):
            return getattr(layer_module, name)
    raise RuntimeError("Could not find MLP module inside decoder layer.")


def get_mlp_act_fn(mlp):
    for name in ["act_fn", "activation_fn", "act"]:
        if hasattr(mlp, name):
            return getattr(mlp, name)
    return torch.nn.functional.silu


def compute_mlp_intermediate(mlp, x_final: torch.Tensor) -> torch.Tensor:
    if not hasattr(mlp, "gate_proj") or not hasattr(mlp, "up_proj") or not hasattr(mlp, "down_proj"):
        raise RuntimeError("This script assumes Qwen/Llama-style gate_proj/up_proj/down_proj MLP.")
    return get_mlp_act_fn(mlp)(mlp.gate_proj(x_final)) * mlp.up_proj(x_final)


def load_model_and_tokenizer(model_id: str, device: str, dtype):
    from transformers import AutoTokenizer, AutoModelForCausalLM

    print(f"Loading tokenizer: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    print(f"Loading model: {model_id}")
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
    print("Model loaded.")
    print("Input device:", get_input_device(model))
    print("Number of layers:", len(get_decoder_layers(model)))
    return model, tokenizer


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


def parse_int_list(x: str) -> List[int]:
    return [int(p.strip()) for p in x.split(",") if p.strip()]


def parse_float_list(x: str) -> List[float]:
    return [float(p.strip()) for p in x.split(",") if p.strip()]


def normalize_rows(x: torch.Tensor, eps: float = 1e-8):
    return x / (x.norm(dim=-1, keepdim=True) + eps)


def filter_seeds_by_eligibility(seeds: pd.DataFrame, eligibility_path: str, filter_col: str):
    elig = pd.read_csv(eligibility_path)
    if "scenario_id" not in elig.columns:
        raise ValueError("Eligibility file must contain scenario_id column.")
    if filter_col not in elig.columns:
        raise ValueError(f"Column {filter_col} not found. Available: {list(elig.columns)}")
    keep_ids = set(elig.loc[elig[filter_col].astype(bool), "scenario_id"].astype(int).tolist())
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


@torch.no_grad()
def forward_collect_resid_and_mlpacts(model, tokenizer, text: str, yes_ids, no_ids, layers_to_run: List[int]):
    decoder_layers = get_decoder_layers(model)
    input_device = get_input_device(model)
    mlp_acts: Dict[int, torch.Tensor] = {}
    handles = []

    def make_mlp_hook(layer_idx: int):
        def hook(module, inputs, output):
            x_final = inputs[0][:, -1, :]
            m = compute_mlp_intermediate(module, x_final)
            mlp_acts[layer_idx] = m[0].detach().float().cpu()
            return output
        return hook

    for L in layers_to_run:
        handles.append(get_mlp_module(decoder_layers[L]).register_forward_hook(make_mlp_hook(L)))

    try:
        enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
        input_ids = enc["input_ids"].to(input_device)
        out = model(input_ids=input_ids, output_hidden_states=True, use_cache=False)
        resid_post = torch.stack([h[0, -1, :].detach().float().cpu() for h in out.hidden_states[1:]], dim=0)
        y, n, margin, decision = yes_no_margin(out.logits[0, -1, :], yes_ids, no_ids)
    finally:
        for h in handles:
            h.remove()

    missing = [L for L in layers_to_run if L not in mlp_acts]
    if missing:
        raise RuntimeError(f"Missing MLP activations for layers: {missing}")

    return resid_post, mlp_acts, {
        "yes_logit": y,
        "no_logit": n,
        "margin": margin,
        "decision": decision,
        "prompt_len_tokens": int(input_ids.shape[1]),
    }


def collect_cache(model, tokenizer, seeds: pd.DataFrame, yes_ids, no_ids, layers_to_run: List[int]):
    cache: Dict[int, Dict[str, Dict]] = {}
    for _, row in tqdm(seeds.iterrows(), total=len(seeds), desc="Collecting A/D states + MLP acts"):
        sid = int(row["scenario_id"])
        variants = make_variants(row, tokenizer=tokenizer)
        if "A" not in variants or "D" not in variants:
            raise RuntimeError(f"Scenario {sid} missing A or D variant.")
        cache[sid] = {}
        for version in ["A", "D"]:
            v = variants[version]
            resid_post, mlp_acts, info = forward_collect_resid_and_mlpacts(
                model, tokenizer, v.text, yes_ids, no_ids, layers_to_run
            )
            cache[sid][version] = {
                "resid_post": resid_post,
                "mlp_acts": mlp_acts,
                "text": v.text,
                "expected": v.expected,
                "condition": v.condition,
                "margin": info["margin"],
                "decision": info["decision"],
                "yes_logit": info["yes_logit"],
                "no_logit": info["no_logit"],
                "prompt_len_tokens": info["prompt_len_tokens"],
            }
    return cache


def build_resid_D_minus_A_directions(cache: Dict[int, Dict], train_sids: List[int]):
    A = torch.stack([cache[sid]["A"]["resid_post"] for sid in train_sids], dim=0)
    D = torch.stack([cache[sid]["D"]["resid_post"] for sid in train_sids], dim=0)
    directions = normalize_rows(D.mean(dim=0) - A.mean(dim=0))
    mus = torch.cat([A, D], dim=0).mean(dim=0)
    return directions, mus


def stack_mlp_acts(cache: Dict[int, Dict], sids: List[int], version: str, layer: int):
    return torch.stack([cache[sid][version]["mlp_acts"][layer] for sid in sids], dim=0)


@torch.no_grad()
def compute_writer_scores_for_layer(model, cache, train_sids: List[int], layer: int, direction: torch.Tensor):
    mlp = get_mlp_module(get_decoder_layers(model)[layer])
    A_m = stack_mlp_acts(cache, train_sids, "A", layer).float()
    D_m = stack_mlp_acts(cache, train_sids, "D", layer).float()
    A_mean = A_m.mean(dim=0)
    D_mean = D_m.mean(dim=0)
    act_gap = D_mean - A_mean
    W_down = mlp.down_proj.weight.detach().float().cpu()  # [d_model, d_mlp]
    d = direction.detach().float().cpu()
    write_coef = W_down.T @ d
    writer_score = act_gap * write_coef
    df = pd.DataFrame({
        "layer": layer,
        "neuron": list(range(writer_score.numel())),
        "A_act_mean": A_mean.numpy(),
        "D_act_mean": D_mean.numpy(),
        "act_gap_D_minus_A": act_gap.numpy(),
        "downproj_dot_direction": write_coef.numpy(),
        "writer_score": writer_score.numpy(),
        "abs_writer_score": writer_score.abs().numpy(),
    })
    df = df.sort_values("writer_score", ascending=False).reset_index(drop=True)
    df["rank_positive"] = range(1, len(df) + 1)
    df_abs = df.sort_values("abs_writer_score", ascending=False).reset_index(drop=True)
    abs_rank = {int(row["neuron"]): i + 1 for i, row in df_abs.iterrows()}
    df["rank_abs"] = df["neuron"].map(abs_rank)
    return df


def compute_mean_acts(cache: Dict[int, Dict], train_sids: List[int], layers_to_run: List[int]):
    A_mean, D_mean, delta = {}, {}, {}
    for L in layers_to_run:
        A_m = stack_mlp_acts(cache, train_sids, "A", L).float()
        D_m = stack_mlp_acts(cache, train_sids, "D", L).float()
        A_mean[L] = A_m.mean(dim=0)
        D_mean[L] = D_m.mean(dim=0)
        delta[L] = D_mean[L] - A_mean[L]
    return A_mean, D_mean, delta


def make_sufficiency_hook(neuron_ids: torch.Tensor, D_mean_cpu: torch.Tensor, delta_cpu: torch.Tensor, alpha: float, intervention: str):
    assert intervention in {"replace", "add_delta"}
    neuron_ids_cpu = neuron_ids.detach().long().cpu()
    D_mean_cpu = D_mean_cpu.detach().float().cpu()
    delta_cpu = delta_cpu.detach().float().cpu()

    def hook(module, inputs, output):
        if isinstance(output, tuple):
            hidden = output[0]
            rest = output[1:]
            tuple_output = True
        else:
            hidden = output
            rest = None
            tuple_output = False

        x_final = inputs[0][:, -1, :]
        m = compute_mlp_intermediate(module, x_final)
        idx_cpu = neuron_ids_cpu
        idx_dev = neuron_ids_cpu.to(device=m.device)

        current = m[:, idx_dev]

        if intervention == "replace":
            target = D_mean_cpu[idx_cpu].to(device=m.device, dtype=m.dtype).unsqueeze(0)
            new_selected = current + alpha * (target - current)
        else:
            delta = delta_cpu[idx_cpu].to(device=m.device, dtype=m.dtype).unsqueeze(0)
            new_selected = current + alpha * delta

        delta_m = new_selected - current

        W = module.down_proj.weight[:, idx_dev].to(device=hidden.device, dtype=hidden.dtype)
        delta_out = delta_m.to(dtype=hidden.dtype) @ W.T
        hidden_new = hidden.clone()
        hidden_new[:, -1, :] = hidden[:, -1, :] + delta_out
        if tuple_output:
            return (hidden_new,) + rest
        return hidden_new

    return hook


@torch.no_grad()
def forward_with_sufficiency(model, tokenizer, text: str, yes_ids, no_ids, layer: int, neuron_ids: List[int], D_mean_values: torch.Tensor, delta_values: torch.Tensor, alpha: float, intervention: str):
    mlp = get_mlp_module(get_decoder_layers(model)[layer])
    handle = mlp.register_forward_hook(make_sufficiency_hook(
        torch.tensor(neuron_ids, dtype=torch.long), D_mean_values, delta_values, alpha, intervention
    ))
    try:
        enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
        input_ids = enc["input_ids"].to(get_input_device(model))
        out = model(input_ids=input_ids, use_cache=False)
        y, n, margin, decision = yes_no_margin(out.logits[0, -1, :], yes_ids, no_ids)
        return {"yes_logit": y, "no_logit": n, "margin": margin, "decision": decision, "prompt_len_tokens": int(input_ids.shape[1])}
    finally:
        handle.remove()


def get_random_neurons(total_neurons: int, k: int, seed: int):
    rng = random.Random(seed)
    return rng.sample(range(total_neurons), k)


def run_neuron_sufficiency(model, tokenizer, cache, test_sids: List[int], writer_scores_by_layer: Dict[int, pd.DataFrame], D_mean_acts_by_layer: Dict[int, torch.Tensor], delta_acts_by_layer: Dict[int, torch.Tensor], layers_to_run: List[int], topks: List[int], alphas: List[float], yes_ids, no_ids, intervention: str, random_controls: int, max_test: int | None):
    sids_eval = test_sids[:max_test] if max_test is not None else test_sids
    rows = []

    for L in tqdm(layers_to_run, desc="MLP neuron sufficiency by layer"):
        scores = writer_scores_by_layer[L]
        total_neurons = len(scores)
        for k in topks:
            if k > total_neurons:
                continue
            top_neurons = scores.head(k)["neuron"].astype(int).tolist()
            for alpha in alphas:
                for control_type, neuron_sets in [("top_writer_neurons", [top_neurons])]:
                    pass

                # Real top-k neurons
                for sid in sids_eval:
                    normal_margin = float(cache[sid]["A"]["margin"])
                    normal_decision = cache[sid]["A"]["decision"]
                    out = forward_with_sufficiency(
                        model, tokenizer, cache[sid]["A"]["text"], yes_ids, no_ids,
                        L, top_neurons, D_mean_acts_by_layer[L], delta_acts_by_layer[L], alpha, intervention
                    )
                    rows.append({
                        "layer": L,
                        "k": k,
                        "alpha": alpha,
                        "scenario_id": sid,
                        "control_type": "top_writer_neurons",
                        "intervention": intervention,
                        "normal_margin": normal_margin,
                        "intervened_margin": float(out["margin"]),
                        "delta_toward_no": normal_margin - float(out["margin"]),
                        "normal_decision": normal_decision,
                        "intervened_decision": out["decision"],
                        "yes_to_no_flip": normal_decision == "Yes" and out["decision"] == "No",
                    })

                # Random controls
                for rc in range(random_controls):
                    rand_neurons = get_random_neurons(total_neurons, k, 1_300_000 + 10_000 * L + 100 * k + 10 * int(alpha * 10) + rc)
                    for sid in sids_eval:
                        normal_margin = float(cache[sid]["A"]["margin"])
                        normal_decision = cache[sid]["A"]["decision"]
                        out = forward_with_sufficiency(
                            model, tokenizer, cache[sid]["A"]["text"], yes_ids, no_ids,
                            L, rand_neurons, D_mean_acts_by_layer[L], delta_acts_by_layer[L], alpha, intervention
                        )
                        rows.append({
                            "layer": L,
                            "k": k,
                            "alpha": alpha,
                            "scenario_id": sid,
                            "control_type": f"random_neurons_{rc}",
                            "intervention": intervention,
                            "normal_margin": normal_margin,
                            "intervened_margin": float(out["margin"]),
                            "delta_toward_no": normal_margin - float(out["margin"]),
                            "normal_decision": normal_decision,
                            "intervened_decision": out["decision"],
                            "yes_to_no_flip": normal_decision == "Yes" and out["decision"] == "No",
                        })

    detail = pd.DataFrame(rows)
    summary_rows = []
    for (L, k, alpha, control_type), g in detail.groupby(["layer", "k", "alpha", "control_type"]):
        summary_rows.append({
            "layer": int(L),
            "k": int(k),
            "alpha": float(alpha),
            "control_type": control_type,
            "n": int(len(g)),
            "normal_margin_mean": g["normal_margin"].mean(),
            "intervened_margin_mean": g["intervened_margin"].mean(),
            "delta_toward_no_mean": g["delta_toward_no"].mean(),
            "yes_to_no_flips": int(g["yes_to_no_flip"].sum()),
            "yes_to_no_flip_rate": g["yes_to_no_flip"].mean(),
        })
    return detail, pd.DataFrame(summary_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--eligibility", required=True)
    parser.add_argument("--filter-col", default="patch_final_AD")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--model", default=CI_MODEL)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu", choices=["cuda", "cpu"])
    parser.add_argument("--dtype", default="float16", choices=["bfloat16", "float16", "float32"])
    parser.add_argument("--train-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--layers", default="22,20,23")
    parser.add_argument("--topks", default="1,5,10,20,50")
    parser.add_argument("--alphas", default="0.5,1.0,1.5,2.0")
    parser.add_argument("--intervention", default="replace", choices=["replace", "add_delta"])
    parser.add_argument("--random-controls", type=int, default=3)
    parser.add_argument("--max-test", type=int, default=None)
    args = parser.parse_args()

    dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}[args.dtype]
    topks = parse_int_list(args.topks)
    alphas = parse_float_list(args.alphas)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("MLP NEURON SUFFICIENCY STEERING")
    print("=" * 80)

    print("\nLoading seeds...")
    seeds = load_seeds(args.seeds)
    print("\nFiltering seeds...")
    seeds = filter_seeds_by_eligibility(seeds, args.eligibility, args.filter_col)

    model, tokenizer = load_model_and_tokenizer(args.model, args.device, dtype)
    layers_to_run = parse_layers(args.layers, len(get_decoder_layers(model)))
    print(f"\nLayers to run: {layers_to_run}")
    print(f"Top-k values: {topks}")
    print(f"Alphas: {alphas}")
    print(f"Intervention: {args.intervention}")

    sids = sorted(seeds["scenario_id"].astype(int).tolist())
    train_sids, test_sids = split_train_test(sids, args.train_frac, args.seed)
    print(f"\nTrain scenarios: {len(train_sids)}")
    print(f"Test scenarios:  {len(test_sids)}")
    pd.DataFrame({"scenario_id": train_sids + test_sids, "split": ["train"] * len(train_sids) + ["test"] * len(test_sids)}).to_csv(out_dir / "split.csv", index=False)

    yes_ids, no_ids = get_yes_no_token_ids(tokenizer)
    print("Yes token IDs:", yes_ids)
    print("No token IDs:", no_ids)

    print("\nCollecting residual states and MLP activations...")
    cache = collect_cache(model, tokenizer, seeds, yes_ids, no_ids, layers_to_run)

    print("\nBuilding residual D-A directions...")
    directions, mus = build_resid_D_minus_A_directions(cache, train_sids)
    torch.save({"directions": directions, "mus": mus, "train_sids": train_sids, "test_sids": test_sids, "layers_to_run": layers_to_run, "topks": topks, "alphas": alphas, "filter_col": args.filter_col, "intervention": args.intervention}, out_dir / "directions.pt")

    print("\nComputing MLP neuron writer scores...")
    writer_scores_by_layer = {}
    frames = []
    for L in layers_to_run:
        df_L = compute_writer_scores_for_layer(model, cache, train_sids, L, directions[L])
        writer_scores_by_layer[L] = df_L
        frames.append(df_L)
    writer_df = pd.concat(frames, ignore_index=True)
    writer_df.to_csv(out_dir / "mlp_writer_scores.csv", index=False)
    print("\nTop writer neurons:")
    print(writer_df.sort_values("writer_score", ascending=False).head(30).to_string(index=False))

    print("\nComputing A/D mean MLP activations...")
    A_mean, D_mean, delta = compute_mean_acts(cache, train_sids, layers_to_run)
    torch.save({"A_mean_acts_by_layer": A_mean, "D_mean_acts_by_layer": D_mean, "delta_acts_by_layer": delta, "layers_to_run": layers_to_run}, out_dir / "mean_mlp_acts.pt")

    print("\nRunning held-out A -> No neuron sufficiency steering...")
    detail, summary = run_neuron_sufficiency(model, tokenizer, cache, test_sids, writer_scores_by_layer, D_mean, delta, layers_to_run, topks, alphas, yes_ids, no_ids, args.intervention, args.random_controls, args.max_test)
    detail.to_csv(out_dir / "neuron_sufficiency_detail.csv", index=False)
    summary.to_csv(out_dir / "neuron_sufficiency_summary.csv", index=False)

    print("\nSaved:")
    for name in ["split.csv", "directions.pt", "mean_mlp_acts.pt", "mlp_writer_scores.csv", "neuron_sufficiency_detail.csv", "neuron_sufficiency_summary.csv"]:
        print(" ", out_dir / name)

    real = summary[summary["control_type"] == "top_writer_neurons"].copy()
    print("\nTop A->No sufficiency steering by Yes->No flip rate:")
    if len(real):
        print(real.sort_values(["yes_to_no_flip_rate", "delta_toward_no_mean"], ascending=False).head(40).to_string(index=False))

    randoms = summary[summary["control_type"].str.startswith("random_neurons")].copy()
    if len(randoms):
        random_mean = randoms.groupby(["layer", "k", "alpha"], as_index=False).agg(
            random_delta_toward_no_mean=("delta_toward_no_mean", "mean"),
            random_yes_to_no_flip_rate_mean=("yes_to_no_flip_rate", "mean"),
        )
        random_mean.to_csv(out_dir / "neuron_sufficiency_random_summary.csv", index=False)
        print("\nRandom control summary saved:")
        print(" ", out_dir / "neuron_sufficiency_random_summary.csv")

    del model, tokenizer
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
