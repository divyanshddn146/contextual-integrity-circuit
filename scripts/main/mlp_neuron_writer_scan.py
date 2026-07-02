"""
mlp_neuron_writer_scan.py

Goal:
  Move from component-level MLP result to neuron-level MLP writer analysis.

Question:
  Which MLP neurons write the final-token D-A / violation / No direction?

For each target layer L:
  1. Build final-token residual direction:
       d_L = mean(resid_post_D[L, final]) - mean(resid_post_A[L, final])

  2. Capture MLP intermediate activations at the final token:
       m = silu(gate_proj(x)) * up_proj(x)

  3. Score each MLP neuron j:
       writer_score_j =
         (mean_D[m_j] - mean_A[m_j]) * dot(W_down[:, j], d_L)

     High positive score means:
       the neuron fires more on D than A
       and writes in the D-A / violation direction.

  4. Causally test top-k writer neurons:
       On held-out D prompts, replace selected neurons' m_j with their A-mean
       and measure whether D flips from No to Yes.

Usage smoke:
  python scripts/mlp_neuron_writer_scan.py \
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \
    --filter-col patch_final_AD \
    --out-dir results/clean304/mlp_neuron_writer_smoke \
    --dtype float16 \
    --device cuda \
    --layers 27,21 \
    --topks 10,50 \
    --max-test 10 \
    --random-controls 1

Usage full:
  python scripts/mlp_neuron_writer_scan.py \
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \
    --filter-col patch_final_AD \
    --out-dir results/clean304/mlp_neuron_writer \
    --dtype float16 \
    --device cuda \
    --layers 27,21,20,22,23,25,26 \
    --topks 1,5,10,20,50,100,200 \
    --random-controls 3

Outputs:
  split.csv
  directions.pt
  mlp_writer_scores.csv
  neuron_ablation_detail.csv
  neuron_ablation_summary.csv
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


# ---------------------------------------------------------------------
# Yes/No helpers
# ---------------------------------------------------------------------

def get_yes_no_token_ids(tokenizer) -> Tuple[List[int], List[int]]:
    def collect(words):
        out = []
        for w in words:
            ids = tokenizer.encode(w, add_special_tokens=False)
            if len(ids) == 1:
                out.append(ids[0])
        return list(dict.fromkeys(out))

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


# ---------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------

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


def compute_qwen_mlp_intermediate(mlp, x_final: torch.Tensor) -> torch.Tensor:
    """
    Qwen/Llama-style gated MLP:
      m = act_fn(gate_proj(x)) * up_proj(x)
      out = down_proj(m)

    x_final: [batch, d_model]
    returns m: [batch, d_mlp]
    """
    if not hasattr(mlp, "gate_proj") or not hasattr(mlp, "up_proj") or not hasattr(mlp, "down_proj"):
        raise RuntimeError(
            "MLP does not expose gate_proj/up_proj/down_proj. "
            "This script assumes Qwen/Llama-style gated MLP."
        )

    act_fn = get_mlp_act_fn(mlp)
    return act_fn(mlp.gate_proj(x_final)) * mlp.up_proj(x_final)


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
        )
        model = model.to(device)

    model.eval()

    print("Model loaded.")
    print("Input device:", get_input_device(model))
    print("Number of layers:", len(get_decoder_layers(model)))

    return model, tokenizer


# ---------------------------------------------------------------------
# Arg helpers
# ---------------------------------------------------------------------

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


def normalize_rows(x: torch.Tensor, eps: float = 1e-8):
    return x / (x.norm(dim=-1, keepdim=True) + eps)


# ---------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------

def filter_seeds_by_eligibility(seeds: pd.DataFrame, eligibility_path: str, filter_col: str):
    elig = pd.read_csv(eligibility_path)

    if "scenario_id" not in elig.columns:
        raise ValueError("Eligibility file must contain scenario_id column.")

    if filter_col not in elig.columns:
        raise ValueError(
            f"Column {filter_col} not found in eligibility file.\n"
            f"Available columns: {list(elig.columns)}"
        )

    keep_ids = set(
        elig.loc[elig[filter_col].astype(bool), "scenario_id"]
        .astype(int)
        .tolist()
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
    train_sids = sorted(sids[:n_train])
    test_sids = sorted(sids[n_train:])

    return train_sids, test_sids


# ---------------------------------------------------------------------
# Forward collection
# ---------------------------------------------------------------------

def _extract_hidden_from_output(output):
    if isinstance(output, tuple):
        return output[0]
    return output


@torch.no_grad()
def forward_collect_resid_and_mlpacts(
    model,
    tokenizer,
    text: str,
    yes_ids,
    no_ids,
    layers_to_run: List[int],
):
    """
    One forward pass.

    Returns:
      resid_post: [n_layers, d_model] CPU float32
      mlp_acts_by_layer: dict L -> [d_mlp] CPU float32
      behavior info
    """
    decoder_layers = get_decoder_layers(model)
    input_device = get_input_device(model)

    mlp_acts: Dict[int, torch.Tensor] = {}
    handles = []

    def make_mlp_hook(layer_idx: int):
        def hook(module, inputs, output):
            # inputs[0]: [batch, seq, d_model]
            x = inputs[0]
            x_final = x[:, -1, :]
            m = compute_qwen_mlp_intermediate(module, x_final)
            mlp_acts[layer_idx] = m[0].detach().float().cpu()
            return output
        return hook

    for L in layers_to_run:
        mlp = get_mlp_module(decoder_layers[L])
        handles.append(mlp.register_forward_hook(make_mlp_hook(L)))

    try:
        enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
        input_ids = enc["input_ids"].to(input_device)

        out = model(
            input_ids=input_ids,
            output_hidden_states=True,
            use_cache=False,
        )

        resid_post = torch.stack(
            [h[0, -1, :].detach().float().cpu() for h in out.hidden_states[1:]],
            dim=0,
        )

        logits_last = out.logits[0, -1, :]
        y, n, margin, decision = yes_no_margin(logits_last, yes_ids, no_ids)

    finally:
        for h in handles:
            h.remove()

    missing = [L for L in layers_to_run if L not in mlp_acts]
    if missing:
        raise RuntimeError(f"Missing MLP activations for layers: {missing}")

    info = {
        "yes_logit": y,
        "no_logit": n,
        "margin": margin,
        "decision": decision,
        "prompt_len_tokens": int(input_ids.shape[1]),
    }

    return resid_post, mlp_acts, info


def collect_cache(model, tokenizer, seeds: pd.DataFrame, yes_ids, no_ids, layers_to_run: List[int]):
    """
    cache[sid]["A" or "D"] contains:
      resid_post: [n_layers, d_model]
      mlp_acts: dict L -> [d_mlp]
      text, margin, decision
    """
    cache: Dict[int, Dict[str, Dict]] = {}

    for _, row in tqdm(seeds.iterrows(), total=len(seeds), desc="Collecting A/D states + MLP acts"):
        sid = int(row["scenario_id"])
        variants = make_variants(row, tokenizer=tokenizer)

        if "A" not in variants or "D" not in variants:
            raise RuntimeError(f"Scenario {sid} missing A or D variant.")

        cache[sid] = {}

        for version in ["A", "D"]:
            variant = variants[version]

            resid_post, mlp_acts, info = forward_collect_resid_and_mlpacts(
                model=model,
                tokenizer=tokenizer,
                text=variant.text,
                yes_ids=yes_ids,
                no_ids=no_ids,
                layers_to_run=layers_to_run,
            )

            cache[sid][version] = {
                "resid_post": resid_post,
                "mlp_acts": mlp_acts,
                "text": variant.text,
                "expected": variant.expected,
                "condition": variant.condition,
                "margin": info["margin"],
                "decision": info["decision"],
                "yes_logit": info["yes_logit"],
                "no_logit": info["no_logit"],
                "prompt_len_tokens": info["prompt_len_tokens"],
            }

    return cache


# ---------------------------------------------------------------------
# Direction and writer score
# ---------------------------------------------------------------------

def build_resid_D_minus_A_directions(cache: Dict[int, Dict], train_sids: List[int]):
    """
    d_L = mean(resid_D[L]) - mean(resid_A[L])
    for every model layer.
    """
    A = torch.stack([cache[sid]["A"]["resid_post"] for sid in train_sids], dim=0)
    D = torch.stack([cache[sid]["D"]["resid_post"] for sid in train_sids], dim=0)

    A_mean = A.mean(dim=0)
    D_mean = D.mean(dim=0)

    directions = normalize_rows(D_mean - A_mean)
    mus = torch.cat([A, D], dim=0).mean(dim=0)

    return directions, mus


def stack_mlp_acts(cache: Dict[int, Dict], sids: List[int], version: str, layer: int):
    return torch.stack([cache[sid][version]["mlp_acts"][layer] for sid in sids], dim=0)


@torch.no_grad()
def compute_writer_scores_for_layer(model, cache, train_sids: List[int], layer: int, direction: torch.Tensor):
    """
    writer_score_j =
      (mean_D[m_j] - mean_A[m_j]) * dot(W_down[:, j], d)

    Returns dataframe sorted by writer_score descending.
    """
    decoder_layers = get_decoder_layers(model)
    mlp = get_mlp_module(decoder_layers[layer])

    if not hasattr(mlp, "down_proj"):
        raise RuntimeError("MLP does not expose down_proj.")

    A_m = stack_mlp_acts(cache, train_sids, "A", layer).float()
    D_m = stack_mlp_acts(cache, train_sids, "D", layer).float()

    A_mean = A_m.mean(dim=0)
    D_mean = D_m.mean(dim=0)
    act_gap = D_mean - A_mean

    # down_proj.weight shape: [d_model, d_mlp]
    W_down = mlp.down_proj.weight.detach().float().cpu()
    d = direction.detach().float().cpu()

    # Each neuron j writes vector W_down[:, j].
    # Its alignment with d is dot(W_down[:, j], d).
    write_coef = W_down.T @ d

    writer_score = act_gap * write_coef
    abs_writer_score = writer_score.abs()

    df = pd.DataFrame({
        "layer": layer,
        "neuron": list(range(writer_score.numel())),
        "A_act_mean": A_mean.numpy(),
        "D_act_mean": D_mean.numpy(),
        "act_gap_D_minus_A": act_gap.numpy(),
        "downproj_dot_direction": write_coef.numpy(),
        "writer_score": writer_score.numpy(),
        "abs_writer_score": abs_writer_score.numpy(),
    })

    df = df.sort_values("writer_score", ascending=False).reset_index(drop=True)
    df["rank_positive"] = range(1, len(df) + 1)

    df_abs = df.sort_values("abs_writer_score", ascending=False).reset_index(drop=True)
    abs_rank_map = {int(row["neuron"]): i + 1 for i, row in df_abs.iterrows()}
    df["rank_abs"] = df["neuron"].map(abs_rank_map)

    return df


def compute_A_mean_acts(cache: Dict[int, Dict], train_sids: List[int], layers_to_run: List[int]):
    """
    A_mean_acts[layer] = mean A final-token MLP activation vector.
    Used for mean-ablation of top D-writer neurons.
    """
    out = {}
    for L in layers_to_run:
        A_m = stack_mlp_acts(cache, train_sids, "A", L).float()
        out[L] = A_m.mean(dim=0)
    return out


# ---------------------------------------------------------------------
# MLP neuron ablation hook
# ---------------------------------------------------------------------

def make_mlp_neuron_ablation_hook(
    neuron_ids: torch.Tensor,
    replacement_cpu: torch.Tensor,
    mode: str,
):
    """
    Replaces selected MLP intermediate neurons at final token only.

    mode:
      mean:
        selected m_j <- A_mean_j
      zero:
        selected m_j <- 0

    Implementation:
      Original MLP output = down_proj(m)
      New output = original_output - down_proj(delta_m_selected)
    """
    assert mode in {"mean", "zero"}

    neuron_ids_cpu = neuron_ids.detach().long().cpu()
    replacement_cpu = replacement_cpu.detach().float().cpu()

    def hook(module, inputs, output):
        if isinstance(output, tuple):
            hidden = output[0]
            rest = output[1:]
            tuple_output = True
        else:
            hidden = output
            rest = None
            tuple_output = False

        x = inputs[0]
        x_final = x[:, -1, :]

        m = compute_qwen_mlp_intermediate(module, x_final)  # [batch, d_mlp]

        idx = neuron_ids_cpu.to(device=m.device)
        if mode == "mean":
            repl = replacement_cpu.to(device=m.device, dtype=m.dtype).unsqueeze(0)
        else:
            repl = torch.zeros((1, idx.numel()), device=m.device, dtype=m.dtype)

        current = m[:, idx]
        delta_m = current - repl

        W = module.down_proj.weight[:, idx].to(device=hidden.device, dtype=hidden.dtype)
        delta_out = delta_m.to(dtype=hidden.dtype) @ W.T

        hidden_new = hidden.clone()
        hidden_new[:, -1, :] = hidden[:, -1, :] - delta_out

        if tuple_output:
            return (hidden_new,) + rest
        return hidden_new

    return hook


@torch.no_grad()
def forward_with_mlp_neuron_ablation(
    model,
    tokenizer,
    text: str,
    yes_ids,
    no_ids,
    layer: int,
    neuron_ids: List[int],
    replacement_values: torch.Tensor,
    mode: str,
):
    decoder_layers = get_decoder_layers(model)
    mlp = get_mlp_module(decoder_layers[layer])
    input_device = get_input_device(model)

    neuron_tensor = torch.tensor(neuron_ids, dtype=torch.long)
    repl = replacement_values[neuron_tensor].float()

    hook = make_mlp_neuron_ablation_hook(
        neuron_ids=neuron_tensor,
        replacement_cpu=repl,
        mode=mode,
    )

    handle = mlp.register_forward_hook(hook)

    try:
        enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
        input_ids = enc["input_ids"].to(input_device)

        out = model(input_ids=input_ids, use_cache=False)

        logits_last = out.logits[0, -1, :]
        y, n, margin, decision = yes_no_margin(logits_last, yes_ids, no_ids)

        return {
            "yes_logit": y,
            "no_logit": n,
            "margin": margin,
            "decision": decision,
            "prompt_len_tokens": int(input_ids.shape[1]),
        }

    finally:
        handle.remove()


# ---------------------------------------------------------------------
# Neuron ablation experiment
# ---------------------------------------------------------------------

def get_random_neurons(total_neurons: int, k: int, seed: int):
    rng = random.Random(seed)
    return rng.sample(range(total_neurons), k)


def run_neuron_ablation(
    model,
    tokenizer,
    cache,
    test_sids: List[int],
    writer_scores_by_layer: Dict[int, pd.DataFrame],
    A_mean_acts_by_layer: Dict[int, torch.Tensor],
    layers_to_run: List[int],
    topks: List[int],
    yes_ids,
    no_ids,
    mode: str,
    random_controls: int,
    max_test: int | None,
):
    if max_test is not None:
        sids_eval = test_sids[:max_test]
    else:
        sids_eval = test_sids

    detail_rows = []

    for L in tqdm(layers_to_run, desc="MLP neuron ablations by layer"):
        scores = writer_scores_by_layer[L]
        total_neurons = len(scores)

        for k in topks:
            if k > total_neurons:
                continue

            top_neurons = scores.head(k)["neuron"].astype(int).tolist()

            # Real top-k writer neurons
            for sid in sids_eval:
                normal_margin = float(cache[sid]["D"]["margin"])
                normal_decision = cache[sid]["D"]["decision"]

                out = forward_with_mlp_neuron_ablation(
                    model=model,
                    tokenizer=tokenizer,
                    text=cache[sid]["D"]["text"],
                    yes_ids=yes_ids,
                    no_ids=no_ids,
                    layer=L,
                    neuron_ids=top_neurons,
                    replacement_values=A_mean_acts_by_layer[L],
                    mode=mode,
                )

                detail_rows.append({
                    "layer": L,
                    "k": k,
                    "scenario_id": sid,
                    "control_type": "top_writer_neurons",
                    "ablation_mode": mode,
                    "normal_margin": normal_margin,
                    "intervened_margin": float(out["margin"]),
                    "delta_toward_yes": float(out["margin"]) - normal_margin,
                    "normal_decision": normal_decision,
                    "intervened_decision": out["decision"],
                    "no_to_yes_flip": normal_decision == "No" and out["decision"] == "Yes",
                })

            # Random controls
            for rc in range(random_controls):
                rand_neurons = get_random_neurons(
                    total_neurons=total_neurons,
                    k=k,
                    seed=900_000 + 10_000 * L + 100 * k + rc,
                )

                for sid in sids_eval:
                    normal_margin = float(cache[sid]["D"]["margin"])
                    normal_decision = cache[sid]["D"]["decision"]

                    out = forward_with_mlp_neuron_ablation(
                        model=model,
                        tokenizer=tokenizer,
                        text=cache[sid]["D"]["text"],
                        yes_ids=yes_ids,
                        no_ids=no_ids,
                        layer=L,
                        neuron_ids=rand_neurons,
                        replacement_values=A_mean_acts_by_layer[L],
                        mode=mode,
                    )

                    detail_rows.append({
                        "layer": L,
                        "k": k,
                        "scenario_id": sid,
                        "control_type": f"random_neurons_{rc}",
                        "ablation_mode": mode,
                        "normal_margin": normal_margin,
                        "intervened_margin": float(out["margin"]),
                        "delta_toward_yes": float(out["margin"]) - normal_margin,
                        "normal_decision": normal_decision,
                        "intervened_decision": out["decision"],
                        "no_to_yes_flip": normal_decision == "No" and out["decision"] == "Yes",
                    })

    detail_df = pd.DataFrame(detail_rows)

    summary_rows = []
    for (L, k, control_type), g in detail_df.groupby(["layer", "k", "control_type"]):
        summary_rows.append({
            "layer": int(L),
            "k": int(k),
            "control_type": control_type,
            "n": int(len(g)),
            "normal_margin_mean": g["normal_margin"].mean(),
            "intervened_margin_mean": g["intervened_margin"].mean(),
            "delta_toward_yes_mean": g["delta_toward_yes"].mean(),
            "no_to_yes_flips": int(g["no_to_yes_flip"].sum()),
            "no_to_yes_flip_rate": g["no_to_yes_flip"].mean(),
        })

    summary_df = pd.DataFrame(summary_rows)
    return detail_df, summary_df


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

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

    parser.add_argument("--layers", default="27,21,20,22,23,25,26",
                        help="all, 18-27, or comma list like 27,21,20")
    parser.add_argument("--topks", default="1,5,10,20,50,100,200")
    parser.add_argument("--ablation-mode", default="mean", choices=["mean", "zero"])

    parser.add_argument("--random-controls", type=int, default=3)
    parser.add_argument("--max-test", type=int, default=None)

    args = parser.parse_args()

    dtype = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[args.dtype]

    topks = parse_int_list(args.topks)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("MLP NEURON WRITER SCAN")
    print("=" * 80)

    print("\nLoading seeds...")
    seeds = load_seeds(args.seeds)

    print("\nFiltering seeds...")
    seeds = filter_seeds_by_eligibility(
        seeds=seeds,
        eligibility_path=args.eligibility,
        filter_col=args.filter_col,
    )

    model, tokenizer = load_model_and_tokenizer(args.model, args.device, dtype)

    n_layers = len(get_decoder_layers(model))
    layers_to_run = parse_layers(args.layers, n_layers)

    print(f"\nLayers to run: {layers_to_run}")
    print(f"Top-k values: {topks}")
    print(f"Ablation mode: {args.ablation_mode}")

    sids = sorted(seeds["scenario_id"].astype(int).tolist())
    train_sids, test_sids = split_train_test(sids, args.train_frac, args.seed)

    print(f"\nTrain scenarios: {len(train_sids)}")
    print(f"Test scenarios:  {len(test_sids)}")

    pd.DataFrame({
        "scenario_id": train_sids + test_sids,
        "split": ["train"] * len(train_sids) + ["test"] * len(test_sids),
    }).to_csv(out_dir / "split.csv", index=False)

    yes_ids, no_ids = get_yes_no_token_ids(tokenizer)
    print("Yes token IDs:", yes_ids)
    print("No token IDs:", no_ids)

    print("\nCollecting residual states and MLP activations...")
    cache = collect_cache(
        model=model,
        tokenizer=tokenizer,
        seeds=seeds,
        yes_ids=yes_ids,
        no_ids=no_ids,
        layers_to_run=layers_to_run,
    )

    print("\nBuilding residual D-A directions...")
    directions, mus = build_resid_D_minus_A_directions(cache, train_sids)

    torch.save(
        {
            "directions": directions,
            "mus": mus,
            "train_sids": train_sids,
            "test_sids": test_sids,
            "layers_to_run": layers_to_run,
            "topks": topks,
            "filter_col": args.filter_col,
        },
        out_dir / "directions.pt",
    )

    print("\nComputing MLP neuron writer scores...")
    writer_scores_by_layer: Dict[int, pd.DataFrame] = {}
    writer_frames = []

    for L in layers_to_run:
        df_L = compute_writer_scores_for_layer(
            model=model,
            cache=cache,
            train_sids=train_sids,
            layer=L,
            direction=directions[L],
        )
        writer_scores_by_layer[L] = df_L
        writer_frames.append(df_L)

    writer_df = pd.concat(writer_frames, ignore_index=True)
    writer_df.to_csv(out_dir / "mlp_writer_scores.csv", index=False)

    print("\nTop writer neurons:")
    print(
        writer_df.sort_values("writer_score", ascending=False)
        .head(30)
        .to_string(index=False)
    )

    print("\nComputing A-mean MLP activations for mean ablation...")
    A_mean_acts_by_layer = compute_A_mean_acts(cache, train_sids, layers_to_run)

    torch.save(
        {
            "A_mean_acts_by_layer": A_mean_acts_by_layer,
            "layers_to_run": layers_to_run,
        },
        out_dir / "A_mean_mlp_acts.pt",
    )

    print("\nRunning held-out top-k neuron ablations...")
    detail_df, summary_df = run_neuron_ablation(
        model=model,
        tokenizer=tokenizer,
        cache=cache,
        test_sids=test_sids,
        writer_scores_by_layer=writer_scores_by_layer,
        A_mean_acts_by_layer=A_mean_acts_by_layer,
        layers_to_run=layers_to_run,
        topks=topks,
        yes_ids=yes_ids,
        no_ids=no_ids,
        mode=args.ablation_mode,
        random_controls=args.random_controls,
        max_test=args.max_test,
    )

    detail_df.to_csv(out_dir / "neuron_ablation_detail.csv", index=False)
    summary_df.to_csv(out_dir / "neuron_ablation_summary.csv", index=False)

    print("\nSaved:")
    print(" ", out_dir / "split.csv")
    print(" ", out_dir / "directions.pt")
    print(" ", out_dir / "A_mean_mlp_acts.pt")
    print(" ", out_dir / "mlp_writer_scores.csv")
    print(" ", out_dir / "neuron_ablation_detail.csv")
    print(" ", out_dir / "neuron_ablation_summary.csv")

    real = summary_df[summary_df["control_type"] == "top_writer_neurons"].copy()
    print("\nTop neuron ablations by No->Yes flip rate:")
    if len(real):
        print(
            real.sort_values(
                ["no_to_yes_flip_rate", "delta_toward_yes_mean"],
                ascending=False,
            )
            .head(30)
            .to_string(index=False)
        )

    randoms = summary_df[summary_df["control_type"].str.startswith("random_neurons")].copy()
    if len(randoms):
        random_mean = (
            randoms
            .groupby(["layer", "k"], as_index=False)
            .agg(
                random_delta_toward_yes_mean=("delta_toward_yes_mean", "mean"),
                random_no_to_yes_flip_rate_mean=("no_to_yes_flip_rate", "mean"),
            )
        )
        random_mean.to_csv(out_dir / "neuron_ablation_random_summary.csv", index=False)
        print("\nRandom control summary saved:")
        print(" ", out_dir / "neuron_ablation_random_summary.csv")

    del model, tokenizer
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
