#!/usr/bin/env python3
"""
Base-model L18→L22 mediation/remove-rescue check.

This script tests whether the same discovered L18 heads can route the BASE model
into/out of the downstream L22 MLP writer-neuron state.

Two useful modes:
  remove-like: target_state=A, evaluate normal-No cases, patch L18 heads toward A/allowed, test No→Yes.
  rescue-like: target_state=D, evaluate normal-Yes cases, patch L18 heads toward D/refusal, test Yes→No.

It records final Yes-No margin, target L22 MLP neuron activation, and optional
small qualitative generations. For base rescue, use --target-state D and
--eval-normal-decision Yes.

Outputs:
  - attention_head_writer_scores.csv        if scanning is needed
  - selected_heads.csv
  - mlp_neuron_direction_pair_activations.csv
  - mlp_mediation_detail.csv
  - mlp_mediation_summary.csv
  - qualitative_generation.csv         if --n-gen-per-config > 0
  - qualitative_generation.md          if --n-gen-per-config > 0

Recommended first run:
  python scripts/privacylens_l18_heads_to_l22_mlp_mediation.py \
    --privacy-input data/raw/PrivacyLens/data/main_data.json \
    --direction-data data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
    --head-scores results/pl_attention_head_scan_ablation_L18/attention_head_writer_scores.csv \
    --head-cache results/pl_attention_head_scan_ablation_L18/attention_head_cache.pt \
    --out-dir results/pl_mediation_L18top5_to_L22N13149 \
    --model huseyinatahaninan/Qwen2.5-7B-Instruct-CI \
    --device cuda --dtype float16 \
    --level trajectory --trajectory-style simple --prompt-format yesno_reason \
    --attn-layers 18 --topks 5 --alphas 1.0 \
    --target-layer 22 --target-neuron 13149 \
    --patch-mode mean_patch --selection-mode layerwise \
    --random-controls 3 --only-normal-no
"""

from __future__ import annotations

import argparse
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from tqdm.auto import tqdm
from transformers import AutoModelForCausalLM, AutoTokenizer

try:
    from privacylens_direction_ablation_generation import (
        A_VARIANTS,
        B_VARIANTS,
        OfficialTrajectoryBuilder,
        build_privacylens_prompt,
        encode_prompt,
        load_curated_direction_pairs,
        load_privacylens_cases,
        make_chat_prompt,
        parse_float_list,
        parse_int_list,
        prompt_excerpt,
        score_prompt,
        token_ids_for_variants,
    )
except Exception as e:
    raise RuntimeError(
        "Could not import helpers from privacylens_direction_ablation_generation.py.\n"
        "Put this file in the same scripts/ folder and run from the project root.\n"
        f"Original import error: {e}"
    )


def dtype_from_str(s: str):
    s = str(s).lower()
    if s in {"float16", "fp16", "half"}:
        return torch.float16
    if s in {"bfloat16", "bf16"}:
        return torch.bfloat16
    if s in {"float32", "fp32"}:
        return torch.float32
    raise ValueError(f"Unknown dtype: {s}")


def get_layers(model):
    if hasattr(model, "model") and hasattr(model.model, "layers"):
        return model.model.layers
    if hasattr(model, "transformer") and hasattr(model.transformer, "h"):
        return model.transformer.h
    raise ValueError("Could not locate transformer layers")


def get_self_attn(model, layer: int):
    block = get_layers(model)[int(layer)]
    if hasattr(block, "self_attn"):
        return block.self_attn
    if hasattr(block, "attn"):
        return block.attn
    raise ValueError(f"Layer {layer} has no self_attn/attn module")


def get_o_proj(model, layer: int):
    attn = get_self_attn(model, layer)
    for name in ["o_proj", "out_proj", "c_proj"]:
        if hasattr(attn, name):
            return getattr(attn, name)
    raise ValueError(f"Layer {layer} attention has no o_proj/out_proj/c_proj")


def get_mlp(model, layer: int):
    block = get_layers(model)[int(layer)]
    if hasattr(block, "mlp"):
        return block.mlp
    if hasattr(block, "feed_forward"):
        return block.feed_forward
    raise ValueError(f"Layer {layer} has no mlp/feed_forward module")


def get_mlp_down_proj(model, layer: int):
    mlp = get_mlp(model, layer)
    for name in ["down_proj", "c_proj", "fc2", "dense_4h_to_h"]:
        if hasattr(mlp, name):
            return getattr(mlp, name)
    raise ValueError(f"Layer {layer} MLP has no down_proj/c_proj/fc2/dense_4h_to_h")


def get_head_info(model) -> Tuple[int, int, int]:
    cfg = model.config
    n_heads = int(getattr(cfg, "num_attention_heads", getattr(cfg, "n_head", 0)))
    hidden = int(getattr(cfg, "hidden_size", getattr(cfg, "n_embd", 0)))
    if n_heads <= 0 or hidden <= 0:
        raise ValueError("Could not infer num_attention_heads/hidden_size")
    head_dim = hidden // n_heads
    return n_heads, head_dim, hidden


@dataclass
class HeadSelection:
    name: str
    control_type: str
    k: int
    random_id: int
    heads: List[Tuple[int, int]]  # [(layer, head)]

    @property
    def total_heads(self) -> int:
        return len(self.heads)

    @property
    def layers_name(self) -> str:
        return ",".join(str(x) for x in sorted(set(L for L, _ in self.heads)))

    @property
    def heads_name(self) -> str:
        return ";".join(f"L{L}H{H}" for L, H in self.heads)


class HeadPatch:
    """Patch selected attention heads at final token before o_proj."""

    def __init__(self, model, selection: HeadSelection, target_mean_pre, pre_dirs, alpha: float, patch_mode: str):
        self.model = model
        self.selection = selection
        self.target_mean_pre = target_mean_pre
        self.pre_dirs = pre_dirs
        self.alpha = float(alpha)
        self.patch_mode = patch_mode
        self.handles = []
        self.n_heads, self.head_dim, self.hidden = get_head_info(model)
        self.layer_to_heads: Dict[int, List[int]] = {}
        for L, H in selection.heads:
            self.layer_to_heads.setdefault(int(L), []).append(int(H))

    def __enter__(self):
        for L, heads in self.layer_to_heads.items():
            self.handles.append(get_o_proj(self.model, L).register_forward_pre_hook(self._make_hook(L, heads)))
        return self

    def __exit__(self, exc_type, exc, tb):
        for h in self.handles:
            h.remove()
        self.handles = []
        return False

    def _make_hook(self, L: int, heads: List[int]):
        def hook(module, inputs):
            x = inputs[0]
            y = x.clone()
            dtype = y.dtype
            device = y.device
            for H in heads:
                s = H * self.head_dim
                e = (H + 1) * self.head_dim
                cur = y[:, -1, s:e]
                if self.patch_mode == "mean_patch":
                    target = self.target_mean_pre[int(L)][int(H)].to(device=device, dtype=dtype).view(1, -1)
                    y[:, -1, s:e] = cur + self.alpha * (target - cur)
                elif self.patch_mode == "zero":
                    y[:, -1, s:e] = cur * (1.0 - self.alpha)
                elif self.patch_mode == "pre_direction_remove":
                    d = self.pre_dirs[int(L)][int(H)].to(device=device, dtype=dtype).view(1, -1)
                    proj = (cur * d).sum(dim=-1, keepdim=True)
                    y[:, -1, s:e] = cur - self.alpha * proj * d
                else:
                    raise ValueError(f"Unknown patch_mode: {self.patch_mode}")
            return (y,) + tuple(inputs[1:])
        return hook


def capture_pre_o_final(model, tokenizer, prompt: str, layers: List[int], max_length: int, device: str) -> Tuple[Dict[int, torch.Tensor], Any]:
    cache: Dict[int, torch.Tensor] = {}
    handles = []

    def make_hook(L: int):
        def hook(module, inputs):
            x = inputs[0]
            cache[L] = x[0, -1, :].detach().float().cpu()
            return None
        return hook

    for L in layers:
        handles.append(get_o_proj(model, L).register_forward_pre_hook(make_hook(int(L))))
    try:
        enc = encode_prompt(tokenizer, prompt, max_length=max_length, device=device)
        with torch.no_grad():
            out = model(**enc, output_hidden_states=True)
    finally:
        for h in handles:
            h.remove()
    return cache, out


def build_head_scan_and_cache(model, tokenizer, pairs, layers: List[int], max_length: int, device: str, use_chat_template: bool):
    """Compute L/head writer scores and A-mean head activations for patching."""
    n_heads, head_dim, hidden = get_head_info(model)
    layers = [int(x) for x in layers]

    res_sum = {L: torch.zeros(hidden, dtype=torch.float64) for L in layers}
    pre_delta_sum = {L: torch.zeros(n_heads, head_dim, dtype=torch.float64) for L in layers}
    pre_a_sum = {L: torch.zeros(n_heads, head_dim, dtype=torch.float64) for L in layers}
    pre_d_sum = {L: torch.zeros(n_heads, head_dim, dtype=torch.float64) for L in layers}
    n = 0

    for pair in tqdm(pairs, desc="Scanning A/D head writes"):
        prompt_a = make_chat_prompt(tokenizer, pair.prompt_A, use_chat_template=use_chat_template)
        prompt_d = make_chat_prompt(tokenizer, pair.prompt_D, use_chat_template=use_chat_template)
        pre_a, out_a = capture_pre_o_final(model, tokenizer, prompt_a, layers, max_length, device)
        pre_d, out_d = capture_pre_o_final(model, tokenizer, prompt_d, layers, max_length, device)
        for L in layers:
            ha = out_a.hidden_states[L + 1][0, -1, :].detach().to(torch.float64).cpu()
            hd = out_d.hidden_states[L + 1][0, -1, :].detach().to(torch.float64).cpu()
            res_sum[L] += (hd - ha)
            pa = pre_a[L].to(torch.float64).view(n_heads, head_dim)
            pd_ = pre_d[L].to(torch.float64).view(n_heads, head_dim)
            pre_a_sum[L] += pa
            pre_d_sum[L] += pd_
            pre_delta_sum[L] += (pd_ - pa)
        n += 1

    if n == 0:
        raise ValueError("No A/D direction pairs loaded")

    residual_dirs: Dict[int, torch.Tensor] = {}
    a_mean_pre: Dict[int, torch.Tensor] = {}
    d_mean_pre: Dict[int, torch.Tensor] = {}
    pre_dirs: Dict[int, torch.Tensor] = {}
    rows = []
    for L in layers:
        d = res_sum[L] / float(n)
        d = d / (d.norm() + 1e-12)
        residual_dirs[L] = d.float()
        a_mean = pre_a_sum[L] / float(n)
        d_mean = pre_d_sum[L] / float(n)
        delta = pre_delta_sum[L] / float(n)
        a_mean_pre[L] = a_mean.float()
        d_mean_pre[L] = d_mean.float()
        pre_dirs[L] = (delta / (delta.norm(dim=1, keepdim=True) + 1e-12)).float()

        W = get_o_proj(model, L).weight.detach().float().cpu()
        for h in range(n_heads):
            s = h * head_dim
            e = (h + 1) * head_dim
            delta_h = delta[h].float()
            W_h = W[:, s:e]
            contrib_gap = torch.matmul(W_h, delta_h)
            writer_score = float(torch.dot(contrib_gap, residual_dirs[L]))
            rows.append({
                "layer": int(L),
                "head": int(h),
                "writer_score": writer_score,
                "abs_writer_score": abs(writer_score),
                "pre_delta_norm": float(delta_h.norm()),
                "contrib_gap_norm": float(contrib_gap.norm()),
                "n_pairs": int(n),
            })
    scores = pd.DataFrame(rows).sort_values("writer_score", ascending=False).reset_index(drop=True)
    return scores, residual_dirs, a_mean_pre, d_mean_pre, pre_dirs


def save_head_cache(out_dir: Path, residual_dirs, a_mean_pre, d_mean_pre, pre_dirs, layers):
    torch.save({
        "layers": [int(x) for x in layers],
        "residual_dirs": {int(k): v.cpu() for k, v in residual_dirs.items()},
        "a_mean_pre": {int(k): v.cpu() for k, v in a_mean_pre.items()},
        "d_mean_pre": {int(k): v.cpu() for k, v in d_mean_pre.items()},
        "pre_dirs": {int(k): v.cpu() for k, v in pre_dirs.items()},
    }, out_dir / "attention_head_cache.pt")


def load_head_cache(path: str):
    obj = torch.load(path, map_location="cpu")
    if "d_mean_pre" not in obj:
        raise ValueError(
            f"Head cache {path} has no d_mean_pre. Recompute the cache with this base rescue script "
            "or omit --head-cache for the first run."
        )
    return obj["residual_dirs"], obj["a_mean_pre"], obj["d_mean_pre"], obj["pre_dirs"]


def build_head_selections(scores: pd.DataFrame, layers: List[int], topks: List[int], selection_mode: str, random_controls: int, seed: int) -> Tuple[List[HeadSelection], pd.DataFrame]:
    rng = np.random.default_rng(seed)
    layers = [int(x) for x in layers]
    scores = scores[scores["layer"].astype(int).isin(layers)].copy()
    scores = scores.sort_values("writer_score", ascending=False).reset_index(drop=True)
    max_k = max(topks) if topks else 0
    selections: List[HeadSelection] = []
    selected_rows: List[pd.DataFrame] = []

    if selection_mode == "global":
        if len(scores) < max_k:
            raise ValueError(f"Only {len(scores)} heads available, max_k={max_k}")
        topmax = set((int(r["layer"]), int(r["head"])) for _, r in scores.head(max_k).iterrows())
        for k in topks:
            rows = scores.head(k).copy()
            heads = [(int(r["layer"]), int(r["head"])) for _, r in rows.iterrows()]
            name = f"global_top{k}"
            selections.append(HeadSelection(name, "top_heads", int(k), -1, heads))
            tmp = rows.copy(); tmp["selection_name"] = name; tmp["control_type"] = "top_heads"; tmp["k"] = k; tmp["random_id"] = -1
            selected_rows.append(tmp)
        pool = scores[[((int(r["layer"]), int(r["head"])) not in topmax) for _, r in scores.iterrows()]].copy()
        for k in topks:
            for rid in range(random_controls):
                idx = rng.choice(pool.index.to_numpy(), size=k, replace=False)
                rows = pool.loc[idx].copy().sort_values("writer_score", ascending=False)
                heads = [(int(r["layer"]), int(r["head"])) for _, r in rows.iterrows()]
                name = f"global_random{k}_r{rid}"
                selections.append(HeadSelection(name, "random_heads", int(k), rid, heads))
                tmp = rows.copy(); tmp["selection_name"] = name; tmp["control_type"] = "random_heads"; tmp["k"] = k; tmp["random_id"] = rid
                selected_rows.append(tmp)

    elif selection_mode == "layerwise":
        for k in topks:
            rows_all = []
            heads = []
            for L in layers:
                sL = scores[scores["layer"].astype(int).eq(L)].sort_values("writer_score", ascending=False).head(k).copy()
                rows_all.append(sL)
                heads.extend([(int(r["layer"]), int(r["head"])) for _, r in sL.iterrows()])
            rows = pd.concat(rows_all, ignore_index=True)
            layer_tag = "_".join(str(L) for L in layers)
            name = f"L{layer_tag}_top{k}_per_layer"
            selections.append(HeadSelection(name, "top_heads", int(k), -1, heads))
            tmp = rows.copy(); tmp["selection_name"] = name; tmp["control_type"] = "top_heads"; tmp["k"] = k; tmp["random_id"] = -1
            selected_rows.append(tmp)

        for k in topks:
            for rid in range(random_controls):
                rows_all = []
                heads = []
                for L in layers:
                    sL_all = scores[scores["layer"].astype(int).eq(L)].sort_values("writer_score", ascending=False).reset_index(drop=True)
                    top_excl = set(int(x) for x in sL_all.head(max_k)["head"].tolist())
                    pool = sL_all[~sL_all["head"].astype(int).isin(top_excl)].copy()
                    if len(pool) < k:
                        pool = sL_all.iloc[max_k:].copy()
                    if len(pool) < k:
                        raise ValueError(f"Not enough random heads in layer {L}")
                    idx = rng.choice(pool.index.to_numpy(), size=k, replace=False)
                    sL = pool.loc[idx].copy().sort_values("writer_score", ascending=False)
                    rows_all.append(sL)
                    heads.extend([(int(r["layer"]), int(r["head"])) for _, r in sL.iterrows()])
                rows = pd.concat(rows_all, ignore_index=True)
                layer_tag = "_".join(str(L) for L in layers)
                name = f"L{layer_tag}_random{k}_per_layer_r{rid}"
                selections.append(HeadSelection(name, "random_heads", int(k), rid, heads))
                tmp = rows.copy(); tmp["selection_name"] = name; tmp["control_type"] = "random_heads"; tmp["k"] = k; tmp["random_id"] = rid
                selected_rows.append(tmp)
    else:
        raise ValueError("selection_mode must be global or layerwise")

    sel_df = pd.concat(selected_rows, ignore_index=True) if selected_rows else pd.DataFrame()
    return selections, sel_df


def parse_explicit_heads(heads_str: str) -> List[Tuple[int, int]]:
    """Parse --explicit-heads like '18:15,18:18,18:4'."""
    out = []
    if not heads_str:
        return out
    for part in heads_str.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Bad head spec '{part}', expected layer:head")
        L, H = part.split(":", 1)
        out.append((int(L), int(H)))
    return out


def add_explicit_selection(selections: List[HeadSelection], sel_df: pd.DataFrame, scores: pd.DataFrame, explicit_heads: List[Tuple[int, int]]) -> Tuple[List[HeadSelection], pd.DataFrame]:
    if not explicit_heads:
        return selections, sel_df
    name = "explicit_" + "_".join(f"L{L}H{H}" for L, H in explicit_heads)
    sel = HeadSelection(name, "explicit_heads", len(explicit_heads), -1, explicit_heads)
    selections = [sel] + selections
    rows = []
    for L, H in explicit_heads:
        m = scores[(scores["layer"].astype(int).eq(int(L))) & (scores["head"].astype(int).eq(int(H)))]
        if len(m):
            r = m.iloc[0].to_dict()
        else:
            r = {"layer": int(L), "head": int(H), "writer_score": np.nan}
        r.update({"selection_name": name, "control_type": "explicit_heads", "k": len(explicit_heads), "random_id": -1})
        rows.append(r)
    exp_df = pd.DataFrame(rows)
    sel_df = pd.concat([exp_df, sel_df], ignore_index=True) if len(sel_df) else exp_df
    return selections, sel_df


def score_prompt_and_mlp_act(model, tokenizer, chat_prompt: str, yes_ids: List[int], no_ids: List[int], max_length: int, device: str, target_layer: int, target_neuron: int) -> Tuple[Dict[str, Any], float]:
    cache: Dict[str, float] = {}
    down = get_mlp_down_proj(model, target_layer)

    def hook(module, inputs):
        x = inputs[0]
        if target_neuron < 0 or target_neuron >= x.shape[-1]:
            raise IndexError(f"target_neuron={target_neuron} outside MLP intermediate size {x.shape[-1]}")
        cache["act"] = float(x[0, -1, target_neuron].detach().float().cpu())
        return None

    handle = down.register_forward_pre_hook(hook)
    try:
        sc = score_prompt(model, tokenizer, chat_prompt, yes_ids, no_ids, max_length, device)
    finally:
        handle.remove()
    if "act" not in cache:
        raise RuntimeError("MLP activation hook did not fire")
    return sc, cache["act"]


def build_target_neuron_pair_stats(model, tokenizer, pairs, target_layer: int, target_neuron: int, yes_ids, no_ids, max_length: int, device: str, use_chat_template: bool, out_dir: Path) -> Dict[str, float]:
    rows = []
    for idx, pair in enumerate(tqdm(pairs, desc="Measuring target MLP neuron on A/D pairs")):
        prompt_a = make_chat_prompt(tokenizer, pair.prompt_A, use_chat_template=use_chat_template)
        prompt_d = make_chat_prompt(tokenizer, pair.prompt_D, use_chat_template=use_chat_template)
        sc_a, act_a = score_prompt_and_mlp_act(model, tokenizer, prompt_a, yes_ids, no_ids, max_length, device, target_layer, target_neuron)
        sc_d, act_d = score_prompt_and_mlp_act(model, tokenizer, prompt_d, yes_ids, no_ids, max_length, device, target_layer, target_neuron)
        rows.append({
            "pair_index": idx,
            "A_act": act_a,
            "D_act": act_d,
            "D_minus_A_act": act_d - act_a,
            "A_margin": sc_a["yes_minus_no_margin"],
            "D_margin": sc_d["yes_minus_no_margin"],
        })
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "mlp_neuron_direction_pair_activations.csv", index=False)
    stats = {
        "target_layer": int(target_layer),
        "target_neuron": int(target_neuron),
        "n_pairs": int(len(df)),
        "A_mean_act": float(df["A_act"].mean()),
        "D_mean_act": float(df["D_act"].mean()),
        "D_minus_A_mean_act": float(df["D_minus_A_act"].mean()),
        "A_std_act": float(df["A_act"].std(ddof=1)),
        "D_std_act": float(df["D_act"].std(ddof=1)),
    }
    pd.DataFrame([stats]).to_csv(out_dir / "mlp_neuron_direction_pair_summary.csv", index=False)
    return stats


def corr_safe(a, b) -> float:
    x = pd.Series(a).astype(float)
    y = pd.Series(b).astype(float)
    if len(x) < 2 or x.nunique(dropna=True) < 2 or y.nunique(dropna=True) < 2:
        return float("nan")
    return float(x.corr(y))




def clean_text(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return str(x).strip()


def starts_yes_no(text: str) -> str:
    """Heuristic label for the first generated answer token/text."""
    s = re.sub(r"^\s*[-:*#>\(\[]*\s*", "", clean_text(text))
    low = s.lower()
    if re.match(r"^(\(?a\)?[\.:\)]?\s*)?yes\b", s, flags=re.I):
        return "Yes"
    if re.match(r"^(\(?b\)?[\.:\)]?\s*)?no\b", s, flags=re.I):
        return "No"
    if re.match(r"^\(?a\)?[\.:\)]?\b", s, flags=re.I):
        return "Yes"
    if re.match(r"^\(?b\)?[\.:\)]?\b", s, flags=re.I):
        return "No"
    if "yes" in low[:30] and "no" not in low[:15]:
        return "Yes"
    if "no" in low[:30] and "yes" not in low[:15]:
        return "No"
    return "Other"


def classify_privacy_rationale(text: str) -> Tuple[str, int]:
    """Very lightweight heuristic, only for browsing qualitative examples."""
    s = clean_text(text).lower()
    refusal_terms = [
        "not acceptable", "not appropriate", "should not", "cannot", "must not",
        "without consent", "consent", "privacy", "confidential", "confidentiality",
        "private", "sensitive", "unauthorized", "not share", "shouldn't share",
    ]
    permission_terms = [
        "acceptable", "appropriate", "can share", "may share", "allowed",
        "relevant", "necessary", "helpful", "purpose", "legitimate",
    ]
    has_refusal = any(t in s for t in refusal_terms)
    has_permission = any(t in s for t in permission_terms)
    decision = starts_yes_no(text)
    contradiction = int(decision == "Yes" and has_refusal)
    if has_refusal and not has_permission:
        label = "refusal_like"
    elif has_permission and not has_refusal:
        label = "permission_like"
    elif has_refusal and has_permission:
        label = "mixed"
    else:
        label = "unclear"
    return label, contradiction


def generate_text(
    model,
    tokenizer,
    chat_prompt: str,
    max_length: int,
    max_new_tokens: int,
    device: str,
    do_sample: bool = False,
    temperature: float = 0.0,
) -> str:
    enc = encode_prompt(tokenizer, chat_prompt, max_length=max_length, device=device)
    gen_kwargs = dict(
        max_new_tokens=int(max_new_tokens),
        do_sample=bool(do_sample),
        pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    if do_sample:
        gen_kwargs["temperature"] = float(temperature)
    with torch.no_grad():
        out = model.generate(**enc, **gen_kwargs)
    new_ids = out[0, enc["input_ids"].shape[1]:]
    return tokenizer.decode(new_ids, skip_special_tokens=True).strip()


def choose_generation_detail_rows(detail: pd.DataFrame, n: int) -> pd.DataFrame:
    """Pick successful/strong examples from one selection/alpha detail subset."""
    if detail.empty or n <= 0:
        return detail.iloc[0:0]
    df = detail.copy()
    if "success_flip" in df.columns:
        df["_flip"] = df["success_flip"].astype(int)
    else:
        df["_flip"] = df.get("no_to_yes_flip", pd.Series([0] * len(df), index=df.index)).astype(int)
    sort_cols = ["_flip"]
    for c in ["act_shift_toward_target", "delta_toward_target_decision", "act_shift_toward_A", "delta_toward_yes"]:
        if c in df.columns:
            sort_cols.append(c)
    df = df.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return df.head(int(n)).drop(columns=["_flip"], errors="ignore")


def generate_for_rows(
    model,
    tokenizer,
    rows: pd.DataFrame,
    prompt_map: Dict[int, Tuple[str, str]],
    args,
    condition_name: str,
    selection: Optional[HeadSelection] = None,
    alpha: Optional[float] = None,
    target_mean_pre: Optional[Dict[int, torch.Tensor]] = None,
) -> List[Dict[str, Any]]:
    out_rows: List[Dict[str, Any]] = []
    ctx = HeadPatch(model, selection, target_mean_pre, pre_dirs={}, alpha=float(alpha), patch_mode=args.patch_mode) if selection is not None else None
    if ctx is None:
        manager = None
    else:
        manager = ctx

    def run_one_generation():
        for _, r in tqdm(rows.iterrows(), total=len(rows), desc=f"Generating {condition_name}"):
            case_index = int(r["case_index"])
            user_prompt, chat_prompt = prompt_map[case_index]
            text = generate_text(
                model, tokenizer, chat_prompt, args.max_length, args.max_new_tokens, args.device,
                do_sample=args.do_sample, temperature=args.temperature,
            )
            gen_decision = starts_yes_no(text)
            rationale_label, contradiction = classify_privacy_rationale(text)
            out_rows.append({
                "condition": condition_name,
                "case_index": case_index,
                "level": args.level,
                "selection_name": r.get("selection_name", "normal"),
                "control_type": r.get("control_type", "normal"),
                "heads": r.get("heads", "none"),
                "alpha": float(alpha) if alpha is not None else 0.0,
                "normal_decision": r.get("normal_decision", ""),
                "patched_decision": r.get("patched_decision", ""),
                "normal_margin": float(r.get("normal_margin", np.nan)),
                "patched_margin": float(r.get("patched_margin", np.nan)),
                "delta_toward_yes": float(r.get("delta_toward_yes", np.nan)),
                "normal_mlp_act": float(r.get("normal_mlp_act", np.nan)),
                "patched_mlp_act": float(r.get("patched_mlp_act", np.nan)),
                "act_shift_toward_target": float(r.get("act_shift_toward_target", np.nan)),
                "generated_decision": gen_decision,
                "rationale_label_heuristic": rationale_label,
                "yes_with_refusal_like_rationale_heuristic": contradiction,
                "prompt_excerpt": prompt_excerpt(user_prompt),
                "generation": text,
            })

    if manager is None:
        run_one_generation()
    else:
        with manager:
            run_one_generation()
    return out_rows


def write_generation_md(rows: List[Dict[str, Any]], path: Path):
    lines = ["# Base PrivacyLens L18→L22 remove/rescue qualitative generations\n\n"]
    if not rows:
        lines.append("No qualitative generations saved.\n")
        path.write_text("".join(lines), encoding="utf-8")
        return
    for i, r in enumerate(rows, start=1):
        lines.append(f"## Example {i}: {r['condition']}\n\n")
        lines.append(f"- level: `{r['level']}` case_index: `{r['case_index']}`\n")
        lines.append(f"- selection: `{r['selection_name']}` control_type=`{r['control_type']}` alpha={r['alpha']} heads=`{r['heads']}`\n")
        lines.append(f"- score: normal `{r['normal_decision']}` margin={r['normal_margin']:.4f}; patched `{r['patched_decision']}` margin={r['patched_margin']:.4f}; delta={r['delta_toward_yes']:.4f}\n")
        lines.append(f"- L22 act: normal={r['normal_mlp_act']:.4f}; patched={r['patched_mlp_act']:.4f}; shift_toward_target={r['act_shift_toward_target']:.4f}\n")
        lines.append(f"- generated_decision: `{r['generated_decision']}`; rationale_heuristic=`{r['rationale_label_heuristic']}`; yes/refusal-like contradiction={r['yes_with_refusal_like_rationale_heuristic']}\n\n")
        lines.append("**Prompt excerpt**\n\n```text\n" + str(r["prompt_excerpt"]) + "\n```\n\n")
        lines.append("**Generation**\n\n```text\n" + str(r["generation"]) + "\n```\n\n")
    path.write_text("".join(lines), encoding="utf-8")

def summarise_mediation(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    group_cols = ["selection_name", "control_type", "layers", "heads", "k", "total_heads", "random_id", "patch_mode", "alpha", "target_layer", "target_neuron"]
    for keys, g in df.groupby(group_cols, dropna=False):
        d = dict(zip(group_cols, keys))
        success = g["success_flip"].astype(int) if "success_flip" in g.columns else (g["normal_decision"].eq("No") & g["patched_decision"].eq("Yes")).astype(int)
        d.update({
            "n": int(len(g)),
            "normal_no_count": int(g["normal_decision"].eq("No").sum()),
            "normal_yes_count": int(g["normal_decision"].eq("Yes").sum()),
            "patched_yes_count": int(g["patched_decision"].eq("Yes").sum()),
            "patched_no_count": int(g["patched_decision"].eq("No").sum()),
            "success_flips": int(success.sum()),
            "success_flip_rate": float(success.mean()),
            "no_to_yes_flips": int((g["normal_decision"].eq("No") & g["patched_decision"].eq("Yes")).sum()),
            "yes_to_no_flips": int((g["normal_decision"].eq("Yes") & g["patched_decision"].eq("No")).sum()),
            "normal_margin_mean": float(g["normal_margin"].mean()),
            "patched_margin_mean": float(g["patched_margin"].mean()),
            "delta_margin_mean": float(g["delta_toward_yes"].mean()),
            "A_mean_pair_act": float(g["A_mean_pair_act"].iloc[0]),
            "D_mean_pair_act": float(g["D_mean_pair_act"].iloc[0]),
            "D_minus_A_pair_act": float(g["D_minus_A_pair_act"].iloc[0]),
            "normal_mlp_act_mean": float(g["normal_mlp_act"].mean()),
            "patched_mlp_act_mean": float(g["patched_mlp_act"].mean()),
            "mlp_act_delta_mean": float(g["mlp_act_delta"].mean()),
            "delta_toward_target_decision_mean": float(g["delta_toward_target_decision"].mean()) if "delta_toward_target_decision" in g.columns else float("nan"),
            "act_shift_toward_target_mean": float(g["act_shift_toward_target"].mean()) if "act_shift_toward_target" in g.columns else float("nan"),
            "act_shift_toward_target_rate": float((g["act_shift_toward_target"] > 0).mean()) if "act_shift_toward_target" in g.columns else float("nan"),
            "act_shift_toward_A_mean": float(g["act_shift_toward_A"].mean()) if "act_shift_toward_A" in g.columns else float("nan"),
            "act_shift_toward_A_rate": float((g["act_shift_toward_A"] > 0).mean()) if "act_shift_toward_A" in g.columns else float("nan"),
            "act_dist_to_target_before_mean": float(g["act_dist_to_target_before"].mean()) if "act_dist_to_target_before" in g.columns else float("nan"),
            "act_dist_to_target_after_mean": float(g["act_dist_to_target_after"].mean()) if "act_dist_to_target_after" in g.columns else float("nan"),
            "act_dist_to_A_before_mean": float(g["act_dist_to_A_before"].mean()) if "act_dist_to_A_before" in g.columns else float("nan"),
            "act_dist_to_A_after_mean": float(g["act_dist_to_A_after"].mean()) if "act_dist_to_A_after" in g.columns else float("nan"),
            "act_dist_reduction_mean": float(g["act_dist_reduction"].mean()),
            "corr_delta_margin_with_act_shift_toward_A": corr_safe(g["delta_toward_yes"], g["act_shift_toward_A"]) if "act_shift_toward_A" in g.columns else float("nan"),
            "corr_delta_target_with_act_shift_toward_target": corr_safe(g["delta_toward_target_decision"], g["act_shift_toward_target"]) if "act_shift_toward_target" in g.columns else float("nan"),
            "corr_success_with_act_shift_toward_target": corr_safe(success, g["act_shift_toward_target"]) if "act_shift_toward_target" in g.columns else float("nan"),
            "corr_delta_target_with_dist_reduction": corr_safe(g["delta_toward_target_decision"], g["act_dist_reduction"]) if "delta_toward_target_decision" in g.columns else float("nan"),
            "corr_flip_with_act_shift_toward_A": corr_safe(success, g["act_shift_toward_A"]) if "act_shift_toward_A" in g.columns else float("nan"),
            "corr_delta_margin_with_dist_reduction": corr_safe(g["delta_toward_yes"], g["act_dist_reduction"]),
        })
        rows.append(d)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["control_type", "alpha", "selection_name"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--privacy-input", required=True)
    ap.add_argument("--direction-data", required=True)
    ap.add_argument("--head-scores", default=None, help="Optional attention_head_writer_scores.csv from the head scan")
    ap.add_argument("--head-cache", default=None, help="Optional attention_head_cache.pt from the head scan")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="float16")
    ap.add_argument("--device-map", default=None)
    ap.add_argument("--attn-layers", required=True, help="Attention layers to patch/scan, e.g. 18 or 16,17,18")
    ap.add_argument("--topks", default="5")
    ap.add_argument("--alphas", default="1.0")
    ap.add_argument("--patch-mode", choices=["mean_patch", "zero", "pre_direction_remove"], default="mean_patch")
    ap.add_argument("--selection-mode", choices=["layerwise", "global"], default="layerwise")
    ap.add_argument("--explicit-heads", default="", help="Optional exact heads, e.g. '18:15,18:18,18:4,18:13,18:20'")
    ap.add_argument("--random-controls", type=int, default=3)
    ap.add_argument("--target-layer", type=int, default=22)
    ap.add_argument("--target-neuron", type=int, default=13149)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--level", choices=["seed", "vignette", "trajectory", "trajectory_enhancing"], default="trajectory")
    ap.add_argument("--trajectory-style", choices=["simple", "official"], default="simple")
    ap.add_argument("--privacylens-root", default="raw/PrivacyLens")
    ap.add_argument("--prompt-format", choices=["yesno_reason", "yesno_only", "official_ab"], default="yesno_reason")
    ap.add_argument("--no-chat-template", action="store_true")
    ap.add_argument("--max-direction-pairs", type=int, default=None)
    ap.add_argument("--max-cases", type=int, default=None)
    ap.add_argument("--only-normal-no", action="store_true", help="Backward compatible shortcut for --eval-normal-decision No")
    ap.add_argument("--only-normal-yes", action="store_true", help="Shortcut for --eval-normal-decision Yes")
    ap.add_argument("--target-state", choices=["A", "D"], default="A", help="Mean head state to patch toward: A=allowed/Yes, D=disallowed/No")
    ap.add_argument("--eval-normal-decision", choices=["auto", "No", "Yes", "all"], default="auto", help="Which normal cases to evaluate. auto=No for target-state A, Yes for target-state D")
    ap.add_argument("--max-length", type=int, default=2048)
    ap.add_argument("--n-gen-per-config", type=int, default=0, help="Qualitative generations from strongest successful patched examples. 0 disables generation.")
    ap.add_argument("--max-new-tokens", type=int, default=90)
    ap.add_argument("--do-sample", action="store_true")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--skip-normal-generations", action="store_true")
    ap.add_argument("--generate-random-control", action="store_true", help="Also generate for one random-head control, if available.")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    attn_layers = parse_int_list(args.attn_layers)
    topks = parse_int_list(args.topks)
    alphas = parse_float_list(args.alphas)
    use_chat_template = not args.no_chat_template

    print(f"Loading model: {args.model}")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model_kwargs = dict(torch_dtype=dtype_from_str(args.dtype), trust_remote_code=True)
    if args.device_map:
        model_kwargs["device_map"] = args.device_map
    model = AutoModelForCausalLM.from_pretrained(args.model, **model_kwargs)
    if not args.device_map:
        model.to(args.device)
    model.eval()

    yes_ids = token_ids_for_variants(tokenizer, A_VARIANTS)
    no_ids = token_ids_for_variants(tokenizer, B_VARIANTS)

    pairs = load_curated_direction_pairs(args.direction_data, max_pairs=args.max_direction_pairs)
    print(f"Loaded {len(pairs)} A/D direction pairs")

    loaded_scores = None
    if args.head_scores:
        print(f"Loading head scores for selection: {args.head_scores}")
        loaded_scores = pd.read_csv(args.head_scores)

    if args.head_cache:
        print(f"Loading head cache: {args.head_cache}")
        _, a_mean_pre, d_mean_pre, pre_dirs = load_head_cache(args.head_cache)
        if loaded_scores is None:
            raise ValueError("When using --head-cache, also provide --head-scores or --explicit-heads so selections can be built.")
        scores = loaded_scores
    else:
        print("No --head-cache given; computing A/D L18 head means on the CURRENT model now.")
        scanned_scores, residual_dirs, a_mean_pre, d_mean_pre, pre_dirs = build_head_scan_and_cache(
            model, tokenizer, pairs, attn_layers, args.max_length, args.device, use_chat_template
        )
        scanned_scores.to_csv(out_dir / "attention_head_writer_scores_current_model.csv", index=False)
        save_head_cache(out_dir, residual_dirs, a_mean_pre, d_mean_pre, pre_dirs, attn_layers)
        # Use provided CI/discovery scores for selection if given; otherwise use current-model scan scores.
        scores = loaded_scores if loaded_scores is not None else scanned_scores

    # Normalize cache keys if torch loaded them as strings.
    a_mean_pre = {int(k): v for k, v in a_mean_pre.items()}
    d_mean_pre = {int(k): v for k, v in d_mean_pre.items()}
    pre_dirs = {int(k): v for k, v in pre_dirs.items()}
    target_mean_pre = a_mean_pre if args.target_state == "A" else d_mean_pre

    print("Top available heads:")
    print(scores[scores["layer"].astype(int).isin(attn_layers)].sort_values("writer_score", ascending=False).head(20).to_string(index=False))

    selections, sel_df = build_head_selections(scores, attn_layers, topks, args.selection_mode, args.random_controls, args.seed)
    explicit = parse_explicit_heads(args.explicit_heads)
    selections, sel_df = add_explicit_selection(selections, sel_df, scores, explicit)
    sel_df.to_csv(out_dir / "selected_heads.csv", index=False)

    # Get A/D mean activation for the target downstream MLP neuron.
    pair_stats = build_target_neuron_pair_stats(
        model, tokenizer, pairs, args.target_layer, args.target_neuron,
        yes_ids, no_ids, args.max_length, args.device, use_chat_template, out_dir
    )
    A_mean = pair_stats["A_mean_act"]
    D_mean = pair_stats["D_mean_act"]
    D_minus_A = pair_stats["D_minus_A_mean_act"]
    toward_A_sign = float(np.sign(A_mean - D_mean))
    if toward_A_sign == 0:
        toward_A_sign = 1.0
    target_mlp_mean = A_mean if args.target_state == "A" else D_mean
    source_mlp_mean = D_mean if args.target_state == "A" else A_mean
    toward_target_sign = float(np.sign(target_mlp_mean - source_mlp_mean))
    if toward_target_sign == 0:
        toward_target_sign = 1.0
    target_decision = "Yes" if args.target_state == "A" else "No"
    source_decision = "No" if args.target_state == "A" else "Yes"
    print("Target MLP neuron pair stats:")
    print(pd.DataFrame([pair_stats]).to_string(index=False))

    traj_builder = None
    if args.trajectory_style == "official":
        traj_builder = OfficialTrajectoryBuilder(args.privacylens_root)

    raw_cases = load_privacylens_cases(args.privacy_input)
    if args.max_cases:
        raw_cases = raw_cases[: int(args.max_cases)]

    prompts = []
    prompt_map: Dict[int, Tuple[str, str]] = {}
    normal_rows = []
    for i, case in enumerate(tqdm(raw_cases, desc="Scoring normal cases + target MLP act")):
        user_prompt = build_privacylens_prompt(args.level, case, args.prompt_format, args.trajectory_style, traj_builder)
        chat_prompt = make_chat_prompt(tokenizer, user_prompt, use_chat_template=use_chat_template)
        sc, act = score_prompt_and_mlp_act(
            model, tokenizer, chat_prompt, yes_ids, no_ids, args.max_length, args.device,
            args.target_layer, args.target_neuron
        )
        prompts.append((i, case, user_prompt, chat_prompt, sc, act))
        prompt_map[int(i)] = (user_prompt, chat_prompt)
        normal_rows.append({
            "case_index": i,
            "normal_decision": sc["decision"],
            "normal_margin": sc["yes_minus_no_margin"],
            "normal_mlp_act": act,
            "prompt_excerpt": prompt_excerpt(user_prompt),
        })
    pd.DataFrame(normal_rows).to_csv(out_dir / "normal_privacylens_scores_with_mlp_act.csv", index=False)

    eval_decision = args.eval_normal_decision
    if args.only_normal_no:
        eval_decision = "No"
    if args.only_normal_yes:
        eval_decision = "Yes"
    if eval_decision == "auto":
        eval_decision = source_decision

    eval_prompts = prompts
    if eval_decision in {"No", "Yes"}:
        eval_prompts = [x for x in prompts if x[4]["decision"] == eval_decision]
    print(f"Patch target_state={args.target_state} target_decision={target_decision}; evaluating {len(eval_prompts)} prompts after filter normal_decision={eval_decision}")

    detail_rows = []
    for sel in selections:
        for alpha in alphas:
            print(f"Running mediation: {sel.name} mode={args.patch_mode} alpha={alpha} heads={sel.heads_name}")
            for i, case, user_prompt, chat_prompt, normal_sc, normal_act in tqdm(eval_prompts, desc=f"{sel.name} a={alpha}"):
                with HeadPatch(model, sel, target_mean_pre, pre_dirs, alpha=alpha, patch_mode=args.patch_mode):
                    patched_sc, patched_act = score_prompt_and_mlp_act(
                        model, tokenizer, chat_prompt, yes_ids, no_ids, args.max_length, args.device,
                        args.target_layer, args.target_neuron
                    )
                delta_margin = patched_sc["yes_minus_no_margin"] - normal_sc["yes_minus_no_margin"]
                act_delta = patched_act - normal_act
                act_shift_toward_A = act_delta * toward_A_sign
                act_shift_toward_target = act_delta * toward_target_sign
                dist_before = abs(normal_act - target_mlp_mean)
                dist_after = abs(patched_act - target_mlp_mean)
                dist_to_A_before = abs(normal_act - A_mean)
                dist_to_A_after = abs(patched_act - A_mean)
                delta_toward_target_decision = delta_margin if target_decision == "Yes" else -delta_margin
                success_flip = int(normal_sc["decision"] == source_decision and patched_sc["decision"] == target_decision)
                detail_rows.append({
                    "case_index": i,
                    "level": args.level,
                    "selection_name": sel.name,
                    "control_type": sel.control_type,
                    "layers": sel.layers_name,
                    "heads": sel.heads_name,
                    "k": sel.k,
                    "total_heads": sel.total_heads,
                    "random_id": sel.random_id,
                    "patch_mode": args.patch_mode,
                    "alpha": float(alpha),
                    "target_layer": int(args.target_layer),
                    "target_neuron": int(args.target_neuron),
                    "A_mean_pair_act": A_mean,
                    "D_mean_pair_act": D_mean,
                    "D_minus_A_pair_act": D_minus_A,
                    "toward_A_sign": toward_A_sign,
                    "target_state": args.target_state,
                    "target_decision": target_decision,
                    "source_decision": source_decision,
                    "toward_target_sign": toward_target_sign,
                    "target_mlp_mean": target_mlp_mean,
                    "normal_decision": normal_sc["decision"],
                    "normal_margin": normal_sc["yes_minus_no_margin"],
                    "patched_decision": patched_sc["decision"],
                    "patched_margin": patched_sc["yes_minus_no_margin"],
                    "delta_toward_yes": delta_margin,
                    "delta_toward_target_decision": delta_toward_target_decision,
                    "success_flip": success_flip,
                    "no_to_yes_flip": int(normal_sc["decision"] == "No" and patched_sc["decision"] == "Yes"),
                    "yes_to_no_flip": int(normal_sc["decision"] == "Yes" and patched_sc["decision"] == "No"),
                    "normal_mlp_act": normal_act,
                    "patched_mlp_act": patched_act,
                    "mlp_act_delta": act_delta,
                    "act_shift_toward_A": act_shift_toward_A,
                    "act_shift_toward_target": act_shift_toward_target,
                    "act_dist_to_target_before": dist_before,
                    "act_dist_to_target_after": dist_after,
                    "act_dist_to_A_before": dist_to_A_before,
                    "act_dist_to_A_after": dist_to_A_after,
                    "act_dist_reduction": dist_before - dist_after,
                    "prompt_excerpt": prompt_excerpt(user_prompt),
                })

    detail = pd.DataFrame(detail_rows)
    detail.to_csv(out_dir / "mlp_mediation_detail.csv", index=False)
    summary = summarise_mediation(detail)
    summary.to_csv(out_dir / "mlp_mediation_summary.csv", index=False)

    print("\nMediation summary:")
    if len(summary):
        show_cols = [
            "selection_name", "control_type", "alpha", "n", "success_flips", "success_flip_rate",
            "no_to_yes_flips", "yes_to_no_flips",
            "delta_margin_mean", "delta_toward_target_decision_mean",
            "normal_mlp_act_mean", "patched_mlp_act_mean",
            "act_shift_toward_target_mean", "act_shift_toward_target_rate", "act_dist_reduction_mean",
            "corr_delta_target_with_act_shift_toward_target", "corr_success_with_act_shift_toward_target"
        ]
        print(summary[show_cols].to_string(index=False))
    else:
        print("No rows")
    # Optional qualitative generation examples.
    # These are illustrative only; the causal result is the full scoring/mediation table above.
    if int(args.n_gen_per_config) > 0 and len(detail):
        generation_rows: List[Dict[str, Any]] = []
        selection_by_name = {s.name: s for s in selections}

        # Prefer explicit fixed heads if provided; otherwise use the first top-head condition.
        nonrandom = summary[summary["control_type"].isin(["explicit_heads", "top_heads"])].copy()
        if len(nonrandom):
            nonrandom["_priority"] = nonrandom["control_type"].map({"explicit_heads": 0, "top_heads": 1}).fillna(9)
            nonrandom = nonrandom.sort_values(["_priority", "success_flips", "delta_toward_target_decision_mean"], ascending=[True, False, False])
            best = nonrandom.iloc[0]
            best_name = str(best["selection_name"])
            best_alpha = float(best["alpha"])
            best_detail = detail[(detail["selection_name"].eq(best_name)) & (detail["alpha"].astype(float).eq(best_alpha))]
            gen_cases = choose_generation_detail_rows(best_detail, int(args.n_gen_per_config))
            print(f"Generating qualitative examples for {best_name} alpha={best_alpha}, n={len(gen_cases)}")
            if not args.skip_normal_generations:
                generation_rows.extend(generate_for_rows(
                    model, tokenizer, gen_cases, prompt_map, args,
                    condition_name="normal", selection=None, alpha=None, target_mean_pre=None,
                ))
            generation_rows.extend(generate_for_rows(
                model, tokenizer, gen_cases, prompt_map, args,
                condition_name=f"patched_{best_name}_alpha{best_alpha}",
                selection=selection_by_name[best_name], alpha=best_alpha, target_mean_pre=target_mean_pre,
            ))

        # Optional: one random control generation on the same number of selected cases.
        if args.generate_random_control:
            rand = summary[summary["control_type"].eq("random_heads")].copy()
            if len(rand):
                rand = rand.sort_values(["success_flips", "delta_toward_target_decision_mean"], ascending=[False, False])
                rbest = rand.iloc[0]
                rname = str(rbest["selection_name"])
                ralpha = float(rbest["alpha"])
                rdetail = detail[(detail["selection_name"].eq(rname)) & (detail["alpha"].astype(float).eq(ralpha))]
                rcases = choose_generation_detail_rows(rdetail, int(args.n_gen_per_config))
                print(f"Generating random-control qualitative examples for {rname} alpha={ralpha}, n={len(rcases)}")
                generation_rows.extend(generate_for_rows(
                    model, tokenizer, rcases, prompt_map, args,
                    condition_name=f"random_control_{rname}_alpha{ralpha}",
                    selection=selection_by_name[rname], alpha=ralpha, target_mean_pre=target_mean_pre,
                ))

        gen_df = pd.DataFrame(generation_rows)
        gen_df.to_csv(out_dir / "qualitative_generation.csv", index=False)
        write_generation_md(generation_rows, out_dir / "qualitative_generation.md")
        if len(gen_df):
            gen_summary = gen_df.groupby(["condition", "generated_decision"]).size().reset_index(name="n")
            gen_summary.to_csv(out_dir / "qualitative_generation_summary.csv", index=False)
            print("\nQualitative generation summary:")
            print(gen_summary.to_string(index=False))

    print(f"Saved outputs to {out_dir}")


if __name__ == "__main__":
    main()
