"""
base_top_vs_ci_top_neuron_steering.py

Compare CI-top writer neurons vs BASE-top writer neurons for base-model rescue steering.

Question:
  Are the CI-discovered writer neurons special, or do the base model's own
  strongest D-A writer neurons work similarly?

Receiver model:
  Base Qwen/Qwen2.5-7B-Instruct

Prompt:
  D prompts only, usually the held-out D-improvement cases where base says Yes
  and CI says No.

Intervention:
  For a selected neuron set S, at the final token MLP output site:

      base_m_j <- base_m_j + alpha * (D_mean_j - A_mean_j)

  implemented equivalently by adding down_proj(delta_m) to the MLP output.

Selection sources:
  1. ci_top_neurons:
       select top-k neurons from the CI writer-score file;
       use CI D-A deltas for those neurons.

  2. base_top_neurons:
       select top-k neurons from the base writer-score file;
       use base D-A deltas for those neurons.

  3. random_ci_source / random_base_source:
       random same-layer/count controls, using deltas from the matching source.

Why this comparison:
  - CI-top works > random: CI writer neurons are causally meaningful.
  - base-top also works: base already has overlapping/usable latent writer machinery.
  - CI-top > base-top: CI selected/strengthened a more behaviorally relevant set.
  - CI-top ~= base-top: base and CI top writer structures are highly overlapping.

Smoke:
  python scripts/base_top_vs_ci_top_neuron_steering.py \
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \
    --filter-col patch_final_AD \
    --ci-writer-scores results/clean304/mlp_neuron_writer/mlp_writer_scores.csv \
    --base-writer-scores results/clean304/mlp_neuron_writer_base/mlp_writer_scores.csv \
    --ci-split results/clean304/mlp_neuron_writer/split.csv \
    --out-dir results/clean304/base_top_vs_ci_top_steer_smoke \
    --base-model Qwen/Qwen2.5-7B-Instruct \
    --dtype float16 \
    --device cuda \
    --layers 20,22,23,26,27 \
    --topks 50,100 \
    --alphas 0.25,0.5,1.0 \
    --selection global \
    --random-controls 1 \
    --max-eval 10

Full-ish final run:
  python scripts/base_top_vs_ci_top_neuron_steering.py \
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \
    --filter-col patch_final_AD \
    --ci-writer-scores results/clean304/mlp_neuron_writer/mlp_writer_scores.csv \
    --base-writer-scores results/clean304/mlp_neuron_writer_base/mlp_writer_scores.csv \
    --ci-split results/clean304/mlp_neuron_writer/split.csv \
    --out-dir results/clean304/base_top_vs_ci_top_steer \
    --base-model Qwen/Qwen2.5-7B-Instruct \
    --dtype float16 \
    --device cuda \
    --layers 20,22,23,26,27 \
    --topks 50,100,200 \
    --alphas 0.25,0.5,1.0 \
    --selection both \
    --random-controls 3

Outputs:
  split_used.csv
  normal_base_D_margins.csv
  selected_neurons.csv
  selection_overlap_summary.csv
  base_top_vs_ci_top_steer_detail.csv
  base_top_vs_ci_top_steer_summary.csv
  base_top_vs_ci_top_steer_random_summary.csv
"""

from __future__ import annotations

import argparse
import gc
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import torch
from tqdm import tqdm

from ci_dataset import load_seeds, make_variants

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
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


def load_model_and_tokenizer(model_id: str, device: str, dtype):
    from transformers import AutoModelForCausalLM, AutoTokenizer

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


# ---------------------------------------------------------------------
# Args / loading helpers
# ---------------------------------------------------------------------

def parse_layers(layer_arg: str, n_layers: int) -> List[int]:
    if layer_arg == "all":
        layers = list(range(n_layers))
    elif "-" in layer_arg:
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


def parse_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    if pd.api.types.is_numeric_dtype(s):
        return s.fillna(0).astype(float) != 0
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "yes", "y", "t"])


def filter_seeds_by_eligibility(seeds: pd.DataFrame, eligibility_path: str, filter_col: str):
    elig = pd.read_csv(eligibility_path)
    if "scenario_id" not in elig.columns:
        raise ValueError("Eligibility file must contain scenario_id column.")
    if filter_col not in elig.columns:
        raise ValueError(f"Column {filter_col} not found in eligibility file. Available: {list(elig.columns)}")

    keep_ids = set(elig.loc[parse_bool_series(elig[filter_col]), "scenario_id"].astype(int).tolist())
    out = seeds[seeds["scenario_id"].astype(int).isin(keep_ids)].copy()
    print(f"Eligibility filter: {filter_col}")
    print(f"Kept scenarios: {len(out)} / {len(seeds)}")
    if len(out) < 5:
        raise RuntimeError("Too few scenarios after eligibility filtering.")
    return out


def split_train_test(sids: List[int], train_frac: float, seed: int):
    rng = random.Random(seed)
    sids = list(sids)
    rng.shuffle(sids)
    n_train = int(round(len(sids) * train_frac))
    return sorted(sids[:n_train]), sorted(sids[n_train:])


def load_or_make_split(seeds: pd.DataFrame, ci_split_path: Optional[str], train_frac: float, seed: int):
    sids_all = sorted(seeds["scenario_id"].astype(int).tolist())
    if ci_split_path:
        split_df = pd.read_csv(ci_split_path)
        if "scenario_id" not in split_df.columns or "split" not in split_df.columns:
            raise ValueError("--ci-split must have columns: scenario_id, split")
        split_df = split_df[split_df["scenario_id"].astype(int).isin(sids_all)].copy()
        train_sids = sorted(split_df.loc[split_df["split"].astype(str).str.lower() == "train", "scenario_id"].astype(int).tolist())
        test_sids = sorted(split_df.loc[split_df["split"].astype(str).str.lower() == "test", "scenario_id"].astype(int).tolist())
        if not test_sids:
            raise RuntimeError("No test scenarios found in --ci-split after eligibility filtering.")
        return train_sids, test_sids, split_df

    train_sids, test_sids = split_train_test(sids_all, train_frac, seed)
    split_df = pd.DataFrame({
        "scenario_id": train_sids + test_sids,
        "split": ["train"] * len(train_sids) + ["test"] * len(test_sids),
    })
    return train_sids, test_sids, split_df


# ---------------------------------------------------------------------
# Writer score loading / standardization
# ---------------------------------------------------------------------

def standardize_writer_df(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Accept raw mlp_writer_scores.csv or prefixed comparison CSV columns."""
    prefix = f"{source_name}_"
    generic_renames = {
        "ci_A_mean": "A_act_mean",
        "ci_D_mean": "D_act_mean",
        "ci_gap": "act_gap_D_minus_A",
        "ci_gap_D_minus_A": "act_gap_D_minus_A",
        "ci_downproj_dot": "downproj_dot_direction",
        "ci_writer_score": "writer_score",
        "base_A_mean": "A_act_mean",
        "base_D_mean": "D_act_mean",
        "base_gap": "act_gap_D_minus_A",
        "base_gap_D_minus_A": "act_gap_D_minus_A",
        "base_downproj_dot": "downproj_dot_direction",
        "base_writer_score": "writer_score",
    }
    # Also handle exact source prefix in case user has source-specific columns.
    prefixed_renames = {
        f"{prefix}A_mean": "A_act_mean",
        f"{prefix}D_mean": "D_act_mean",
        f"{prefix}gap": "act_gap_D_minus_A",
        f"{prefix}gap_D_minus_A": "act_gap_D_minus_A",
        f"{prefix}downproj_dot": "downproj_dot_direction",
        f"{prefix}writer_score": "writer_score",
    }
    rename = {}
    for k, v in {**generic_renames, **prefixed_renames}.items():
        if k in df.columns and v not in df.columns:
            rename[k] = v
    df = df.rename(columns=rename).copy()

    required = ["layer", "neuron", "A_act_mean", "D_act_mean", "writer_score"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Writer score file for {source_name} missing columns {missing}. "
            f"Need full mlp_writer_scores.csv. Found: {list(df.columns)}"
        )

    df["layer"] = df["layer"].astype(int)
    df["neuron"] = df["neuron"].astype(int)
    df["A_act_mean"] = df["A_act_mean"].astype(float)
    df["D_act_mean"] = df["D_act_mean"].astype(float)
    if "act_gap_D_minus_A" not in df.columns:
        df["act_gap_D_minus_A"] = df["D_act_mean"] - df["A_act_mean"]
    df["D_minus_A_delta"] = df["D_act_mean"] - df["A_act_mean"]
    df["writer_score"] = df["writer_score"].astype(float)
    df["score_source"] = source_name
    return df


def load_writer_scores(path: str, layers: List[int], source_name: str) -> pd.DataFrame:
    df = standardize_writer_df(pd.read_csv(path), source_name=source_name)
    df = df[df["layer"].isin(layers)].copy()
    if df.empty:
        raise RuntimeError(f"No {source_name} writer score rows found for layers {layers}")
    return df


# ---------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------

def rows_to_delta_patch_dict(rows: pd.DataFrame) -> Dict[int, Tuple[List[int], torch.Tensor]]:
    out: Dict[int, Tuple[List[int], torch.Tensor]] = {}
    for L, g in rows.groupby("layer"):
        neurons = g["neuron"].astype(int).tolist()
        deltas = torch.tensor(g["D_minus_A_delta"].astype(float).tolist(), dtype=torch.float32)
        out[int(L)] = (neurons, deltas)
    return out


def select_layerwise_rows(writer_df: pd.DataFrame, layer: int, k: int) -> pd.DataFrame:
    g = writer_df[writer_df["layer"] == layer].sort_values("writer_score", ascending=False)
    if len(g) < k:
        raise ValueError(f"Layer {layer} has only {len(g)} neurons in writer df, cannot select k={k}")
    return g.head(k).copy()


def select_global_rows(writer_df: pd.DataFrame, k: int) -> pd.DataFrame:
    g = writer_df.sort_values("writer_score", ascending=False)
    if len(g) < k:
        raise ValueError(f"Writer df has only {len(g)} rows, cannot select global k={k}")
    return g.head(k).copy()


def sample_random_like(selected_rows: pd.DataFrame, writer_df: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    parts = []
    for L, g_sel in selected_rows.groupby("layer"):
        n = len(g_sel)
        universe = writer_df[writer_df["layer"] == int(L)].copy()
        if len(universe) < n:
            raise ValueError(f"Layer {L} has only {len(universe)} neurons, cannot sample {n}")
        idxs = rng.sample(list(universe.index), n)
        parts.append(universe.loc[idxs])
    return pd.concat(parts, ignore_index=True)


def neuron_key_set(rows: pd.DataFrame) -> set:
    return set(zip(rows["layer"].astype(int).tolist(), rows["neuron"].astype(int).tolist()))


def overlap_record(selection_name: str, layer_label: str, k: int, ci_rows: pd.DataFrame, base_rows: pd.DataFrame):
    ci_set = neuron_key_set(ci_rows)
    base_set = neuron_key_set(base_rows)
    inter = ci_set & base_set
    return {
        "selection_name": selection_name,
        "layer": layer_label,
        "k": int(k),
        "ci_count": int(len(ci_set)),
        "base_count": int(len(base_set)),
        "overlap_count": int(len(inter)),
        "overlap_frac_of_ci": float(len(inter) / max(1, len(ci_set))),
        "overlap_frac_of_base": float(len(inter) / max(1, len(base_set))),
    }


# ---------------------------------------------------------------------
# Forward / steering
# ---------------------------------------------------------------------

def make_delta_steer_hook(neuron_ids: List[int], delta_values_cpu: torch.Tensor, alpha: float):
    neuron_ids_cpu = torch.tensor(neuron_ids, dtype=torch.long).cpu()
    delta_values_cpu = delta_values_cpu.detach().float().cpu()

    def hook(module, inputs, output):
        if isinstance(output, tuple):
            hidden = output[0]
            rest = output[1:]
            is_tuple = True
        else:
            hidden = output
            rest = None
            is_tuple = False

        idx = neuron_ids_cpu.to(device=hidden.device)
        delta_m = (alpha * delta_values_cpu).to(device=hidden.device, dtype=hidden.dtype).unsqueeze(0)

        # down_proj weight shape for Qwen/Llama: [d_model, d_mlp]
        W = module.down_proj.weight[:, idx].to(device=hidden.device, dtype=hidden.dtype)
        delta_out = delta_m @ W.T  # [1, d_model]

        hidden_new = hidden.clone()
        hidden_new[:, -1, :] = hidden[:, -1, :] + delta_out

        if is_tuple:
            return (hidden_new,) + rest
        return hidden_new

    return hook


@torch.no_grad()
def forward_margin(model, tokenizer, text: str, yes_ids, no_ids):
    enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
    input_ids = enc["input_ids"].to(get_input_device(model))
    out = model(input_ids=input_ids, use_cache=False)
    y, n, margin, decision = yes_no_margin(out.logits[0, -1, :], yes_ids, no_ids)
    return {
        "yes_logit": y,
        "no_logit": n,
        "margin": margin,
        "decision": decision,
        "prompt_len_tokens": int(input_ids.shape[1]),
    }


@torch.no_grad()
def forward_with_delta_steering(
    model,
    tokenizer,
    text: str,
    yes_ids,
    no_ids,
    patch_dict: Dict[int, Tuple[List[int], torch.Tensor]],
    alpha: float,
):
    layers = get_decoder_layers(model)
    handles = []
    try:
        for L, (neuron_ids, delta_values) in patch_dict.items():
            mlp = get_mlp_module(layers[int(L)])
            handles.append(mlp.register_forward_hook(make_delta_steer_hook(neuron_ids, delta_values, alpha)))
        return forward_margin(model, tokenizer, text, yes_ids, no_ids)
    finally:
        for h in handles:
            h.remove()


def make_D_prompt_by_sid(seeds: pd.DataFrame, tokenizer) -> Dict[int, str]:
    out = {}
    for _, row in seeds.iterrows():
        sid = int(row["scenario_id"])
        variants = make_variants(row, tokenizer=tokenizer)
        if "D" not in variants:
            raise RuntimeError(f"Scenario {sid} missing D variant")
        out[sid] = variants["D"].text
    return out


# ---------------------------------------------------------------------
# Experiment runners
# ---------------------------------------------------------------------

def run_selection_source(
    model,
    tokenizer,
    D_text_by_sid: Dict[int, str],
    normal_by_sid: Dict[int, Dict],
    sids_eval: List[int],
    yes_ids,
    no_ids,
    selection_name: str,
    layer_label: str,
    k: int,
    source_label: str,
    selected_rows: pd.DataFrame,
    writer_df_for_random: pd.DataFrame,
    alphas: List[float],
    random_controls: int,
    base_random_seed: int,
):
    selected_patch = rows_to_delta_patch_dict(selected_rows)
    selected_log = selected_rows.copy()
    selected_log["selection_name"] = selection_name
    selected_log["k"] = int(k)
    selected_log["layer_label"] = layer_label
    selected_log["control_type"] = f"{source_label}_top_neurons"
    selected_log["selection_source"] = source_label
    selected_log["delta_source"] = source_label

    selections_to_run = [(f"{source_label}_top_neurons", selected_patch, selected_log)]

    for rc in range(random_controls):
        rand_rows = sample_random_like(selected_rows, writer_df_for_random, seed=base_random_seed + rc)
        rand_patch = rows_to_delta_patch_dict(rand_rows)
        rand_log = rand_rows.copy()
        rand_log["selection_name"] = selection_name
        rand_log["k"] = int(k)
        rand_log["layer_label"] = layer_label
        rand_log["control_type"] = f"random_{source_label}_source_{rc}"
        rand_log["selection_source"] = f"random_{source_label}"
        rand_log["delta_source"] = source_label
        rand_log["random_control_id"] = rc
        selections_to_run.append((f"random_{source_label}_source_{rc}", rand_patch, rand_log))

    detail_rows = []
    selected_logs = []
    for control_type, patch_dict, log_df in selections_to_run:
        selected_logs.append(log_df)
        for alpha in alphas:
            for sid in sids_eval:
                normal = normal_by_sid[sid]
                patched = forward_with_delta_steering(
                    model, tokenizer, D_text_by_sid[sid], yes_ids, no_ids, patch_dict, alpha
                )
                detail_rows.append({
                    "selection_name": selection_name,
                    "layer": layer_label,
                    "k": int(k),
                    "alpha": float(alpha),
                    "scenario_id": int(sid),
                    "control_type": control_type,
                    "selection_source": source_label if not control_type.startswith("random") else f"random_{source_label}",
                    "delta_source": source_label,
                    "intervention": "add_source_D_minus_A_neuron_delta_to_base",
                    "normal_margin": float(normal["margin"]),
                    "patched_margin": float(patched["margin"]),
                    "delta_toward_no": float(normal["margin"]) - float(patched["margin"]),
                    "normal_decision": normal["decision"],
                    "patched_decision": patched["decision"],
                    "yes_to_no_flip": normal["decision"] == "Yes" and patched["decision"] == "No",
                    "patched_no": patched["decision"] == "No",
                    "normal_yes_logit": float(normal["yes_logit"]),
                    "normal_no_logit": float(normal["no_logit"]),
                    "patched_yes_logit": float(patched["yes_logit"]),
                    "patched_no_logit": float(patched["no_logit"]),
                    "num_layers_patched": len(patch_dict),
                    "num_neurons_patched": int(sum(len(v[0]) for v in patch_dict.values())),
                })
    return pd.DataFrame(detail_rows), pd.concat(selected_logs, ignore_index=True)


def summarize_detail(detail: pd.DataFrame) -> pd.DataFrame:
    summary_rows = []
    group_cols = [
        "selection_name", "layer", "k", "alpha", "control_type",
        "selection_source", "delta_source", "intervention"
    ]
    for keys, g in detail.groupby(group_cols, dropna=False):
        row = dict(zip(group_cols, keys))
        row.update({
            "n": int(len(g)),
            "normal_margin_mean": float(g["normal_margin"].mean()),
            "patched_margin_mean": float(g["patched_margin"].mean()),
            "delta_toward_no_mean": float(g["delta_toward_no"].mean()),
            "delta_toward_no_median": float(g["delta_toward_no"].median()),
            "yes_to_no_flips": int(g["yes_to_no_flip"].sum()),
            "yes_to_no_flip_rate": float(g["yes_to_no_flip"].mean()),
            "patched_no_count": int(g["patched_no"].sum()),
            "patched_no_rate": float(g["patched_no"].mean()),
            "normal_yes_rate": float((g["normal_decision"] == "Yes").mean()),
            "num_layers_patched": int(g["num_layers_patched"].iloc[0]),
            "num_neurons_patched": int(g["num_neurons_patched"].iloc[0]),
        })
        summary_rows.append(row)
    return pd.DataFrame(summary_rows).sort_values(
        ["yes_to_no_flip_rate", "delta_toward_no_mean"], ascending=False
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--eligibility", required=True)
    parser.add_argument("--filter-col", default="patch_final_AD")
    parser.add_argument("--ci-writer-scores", required=True, help="Full CI mlp_writer_scores.csv")
    parser.add_argument("--base-writer-scores", required=True, help="Full BASE mlp_writer_scores.csv")
    parser.add_argument("--ci-split", default=None, help="Optional split.csv from CI writer scan; recommended")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu", choices=["cuda", "cpu"])
    parser.add_argument("--dtype", default="float16", choices=["bfloat16", "float16", "float32"])
    parser.add_argument("--train-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--layers", default="20,22,23,26,27")
    parser.add_argument("--topks", default="50,100,200")
    parser.add_argument("--alphas", default="0.25,0.5,1.0")
    parser.add_argument("--selection", default="both", choices=["layerwise", "global", "both"])
    parser.add_argument("--sources", default="both", choices=["ci", "base", "both"], help="Which top-neuron sources to run")
    parser.add_argument("--random-controls", type=int, default=3)
    parser.add_argument("--max-eval", type=int, default=None)
    args = parser.parse_args()

    dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}[args.dtype]
    topks = parse_int_list(args.topks)
    alphas = parse_float_list(args.alphas)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("BASE-TOP VS CI-TOP NEURON STEERING COMPARISON")
    print("=" * 80)
    print("Receiver model:", args.base_model)
    print("CI writer score file:", args.ci_writer_scores)
    print("Base writer score file:", args.base_writer_scores)
    print("Intervention:")
    print("  CI-top:   base m_j += alpha * CI(D_mean_j - A_mean_j)")
    print("  Base-top: base m_j += alpha * BASE(D_mean_j - A_mean_j)")
    print("Selection:", args.selection)
    print("Sources:", args.sources)

    print("\nLoading seeds...")
    seeds = load_seeds(args.seeds)
    print("Filtering seeds...")
    seeds = filter_seeds_by_eligibility(seeds, args.eligibility, args.filter_col)

    print("\nLoading base model...")
    model, tokenizer = load_model_and_tokenizer(args.base_model, args.device, dtype)
    layers_to_run = parse_layers(args.layers, len(get_decoder_layers(model)))
    print("Layers:", layers_to_run)
    print("Top-k:", topks)
    print("Alphas:", alphas)

    print("\nLoading writer scores...")
    ci_df = load_writer_scores(args.ci_writer_scores, layers_to_run, source_name="ci")
    base_df = load_writer_scores(args.base_writer_scores, layers_to_run, source_name="base")
    print("CI writer rows:", len(ci_df))
    print("Base writer rows:", len(base_df))

    for name, df in [("CI", ci_df), ("BASE", base_df)]:
        cols = [c for c in ["layer", "neuron", "A_act_mean", "D_act_mean", "D_minus_A_delta", "downproj_dot_direction", "writer_score"] if c in df.columns]
        print(f"\nTop {name} writer rows in selected layers:")
        print(df.sort_values("writer_score", ascending=False).head(15)[cols].to_string(index=False))

    print("\nLoading/synchronizing split...")
    train_sids, test_sids, split_df = load_or_make_split(seeds, args.ci_split, args.train_frac, args.seed)
    sids_eval = test_sids[:args.max_eval] if args.max_eval is not None else test_sids
    print("Train scenarios:", len(train_sids))
    print("Test scenarios:", len(test_sids))
    print("Eval scenarios:", len(sids_eval))
    split_df.to_csv(out_dir / "split_used.csv", index=False)

    yes_ids, no_ids = get_yes_no_token_ids(tokenizer)
    print("Yes token IDs:", yes_ids)
    print("No token IDs:", no_ids)

    print("\nBuilding D prompts...")
    D_text_by_sid = make_D_prompt_by_sid(seeds, tokenizer)

    print("\nComputing normal base D margins once...")
    normal_by_sid = {}
    for sid in tqdm(sids_eval, desc="Normal base D"):
        normal_by_sid[sid] = forward_margin(model, tokenizer, D_text_by_sid[sid], yes_ids, no_ids)
    pd.DataFrame([
        {
            "scenario_id": sid,
            "normal_margin": normal_by_sid[sid]["margin"],
            "normal_decision": normal_by_sid[sid]["decision"],
            "normal_yes_logit": normal_by_sid[sid]["yes_logit"],
            "normal_no_logit": normal_by_sid[sid]["no_logit"],
        }
        for sid in sids_eval
    ]).to_csv(out_dir / "normal_base_D_margins.csv", index=False)

    run_ci = args.sources in ["ci", "both"]
    run_base = args.sources in ["base", "both"]

    all_details = []
    all_selected_logs = []
    overlap_rows = []

    print("\nRunning CI-top vs base-top steering interventions...")

    # Layerwise selections
    if args.selection in ["layerwise", "both"]:
        for L in tqdm(layers_to_run, desc="Layerwise selections"):
            for k in topks:
                if len(ci_df[ci_df["layer"] == L]) < k or len(base_df[base_df["layer"] == L]) < k:
                    continue
                ci_rows = select_layerwise_rows(ci_df, L, k)
                base_rows = select_layerwise_rows(base_df, L, k)
                overlap_rows.append(overlap_record("layerwise_top_delta_steer", str(L), k, ci_rows, base_rows))

                if run_ci:
                    detail, selected_log = run_selection_source(
                        model=model,
                        tokenizer=tokenizer,
                        D_text_by_sid=D_text_by_sid,
                        normal_by_sid=normal_by_sid,
                        sids_eval=sids_eval,
                        yes_ids=yes_ids,
                        no_ids=no_ids,
                        selection_name="layerwise_top_delta_steer",
                        layer_label=str(L),
                        k=k,
                        source_label="ci",
                        selected_rows=ci_rows,
                        writer_df_for_random=ci_df,
                        alphas=alphas,
                        random_controls=args.random_controls,
                        base_random_seed=110_000 + 1000 * L + k,
                    )
                    all_details.append(detail)
                    all_selected_logs.append(selected_log)

                if run_base:
                    detail, selected_log = run_selection_source(
                        model=model,
                        tokenizer=tokenizer,
                        D_text_by_sid=D_text_by_sid,
                        normal_by_sid=normal_by_sid,
                        sids_eval=sids_eval,
                        yes_ids=yes_ids,
                        no_ids=no_ids,
                        selection_name="layerwise_top_delta_steer",
                        layer_label=str(L),
                        k=k,
                        source_label="base",
                        selected_rows=base_rows,
                        writer_df_for_random=base_df,
                        alphas=alphas,
                        random_controls=args.random_controls,
                        base_random_seed=210_000 + 1000 * L + k,
                    )
                    all_details.append(detail)
                    all_selected_logs.append(selected_log)

    # Global selections
    if args.selection in ["global", "both"]:
        for k in tqdm(topks, desc="Global selections"):
            if len(ci_df) < k or len(base_df) < k:
                continue
            ci_rows = select_global_rows(ci_df, k)
            base_rows = select_global_rows(base_df, k)
            overlap_rows.append(overlap_record("global_multilayer_top_delta_steer", "multi", k, ci_rows, base_rows))

            if run_ci:
                detail, selected_log = run_selection_source(
                    model=model,
                    tokenizer=tokenizer,
                    D_text_by_sid=D_text_by_sid,
                    normal_by_sid=normal_by_sid,
                    sids_eval=sids_eval,
                    yes_ids=yes_ids,
                    no_ids=no_ids,
                    selection_name="global_multilayer_top_delta_steer",
                    layer_label="multi",
                    k=k,
                    source_label="ci",
                    selected_rows=ci_rows,
                    writer_df_for_random=ci_df,
                    alphas=alphas,
                    random_controls=args.random_controls,
                    base_random_seed=310_000 + k,
                )
                all_details.append(detail)
                all_selected_logs.append(selected_log)

            if run_base:
                detail, selected_log = run_selection_source(
                    model=model,
                    tokenizer=tokenizer,
                    D_text_by_sid=D_text_by_sid,
                    normal_by_sid=normal_by_sid,
                    sids_eval=sids_eval,
                    yes_ids=yes_ids,
                    no_ids=no_ids,
                    selection_name="global_multilayer_top_delta_steer",
                    layer_label="multi",
                    k=k,
                    source_label="base",
                    selected_rows=base_rows,
                    writer_df_for_random=base_df,
                    alphas=alphas,
                    random_controls=args.random_controls,
                    base_random_seed=410_000 + k,
                )
                all_details.append(detail)
                all_selected_logs.append(selected_log)

    if not all_details:
        raise RuntimeError("No interventions were run. Check --layers, --topks, and writer score files.")

    detail = pd.concat(all_details, ignore_index=True)
    selected_logs = pd.concat(all_selected_logs, ignore_index=True)
    summary = summarize_detail(detail)
    overlap = pd.DataFrame(overlap_rows)

    detail_path = out_dir / "base_top_vs_ci_top_steer_detail.csv"
    summary_path = out_dir / "base_top_vs_ci_top_steer_summary.csv"
    selected_path = out_dir / "selected_neurons.csv"
    overlap_path = out_dir / "selection_overlap_summary.csv"

    detail.to_csv(detail_path, index=False)
    summary.to_csv(summary_path, index=False)
    selected_logs.to_csv(selected_path, index=False)
    overlap.to_csv(overlap_path, index=False)

    randoms = summary[summary["control_type"].astype(str).str.startswith("random_")].copy()
    if len(randoms):
        random_summary = randoms.groupby(
            ["selection_name", "layer", "k", "alpha", "delta_source", "intervention"],
            as_index=False,
        ).agg(
            random_delta_toward_no_mean=("delta_toward_no_mean", "mean"),
            random_yes_to_no_flip_rate_mean=("yes_to_no_flip_rate", "mean"),
            random_patched_no_rate_mean=("patched_no_rate", "mean"),
        )
        random_summary.to_csv(out_dir / "base_top_vs_ci_top_steer_random_summary.csv", index=False)

    print("\nSaved:")
    print(" ", selected_path)
    print(" ", overlap_path)
    print(" ", detail_path)
    print(" ", summary_path)
    if len(randoms):
        print(" ", out_dir / "base_top_vs_ci_top_steer_random_summary.csv")

    real = summary[summary["control_type"].isin(["ci_top_neurons", "base_top_neurons"])].copy()
    print("\nTop real CI-top / base-top steering results:")
    show_cols = [
        "selection_name", "layer", "k", "alpha", "control_type",
        "n", "normal_margin_mean", "patched_margin_mean", "delta_toward_no_mean",
        "yes_to_no_flips", "yes_to_no_flip_rate", "num_neurons_patched",
    ]
    print(real.sort_values(["yes_to_no_flip_rate", "delta_toward_no_mean"], ascending=False).head(80)[show_cols].to_string(index=False))

    print("\nTop selection overlaps:")
    if len(overlap):
        print(overlap.sort_values(["selection_name", "layer", "k"]).to_string(index=False))

    del model, tokenizer
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
