#!/usr/bin/env python3
"""
Head-level writer scan + causal patching for PrivacyLens.

Why this script exists
----------------------
Your component-direction ablation can say "attention block L18 matters", but it
cannot say which attention head is responsible. This script decomposes the
attention block into heads by using the input to self_attn.o_proj:

    attn_out_pre_o = concat(head_0, head_1, ..., head_H-1)
    residual_write = o_proj(attn_out_pre_o)

For each layer/head, it estimates:

    head_writer_score = < mean_D(head residual write) - mean_A(head residual write),
                          residual_refusal_direction_at_layer >

Then it optionally tests causal effects on real PrivacyLens prompts by patching
selected head activations at the final token during scoring/generation.

Patch modes
-----------
mean_patch:  x_head <- x_head + alpha * (A_mean_head - x_head)
zero:        x_head <- (1 - alpha) * x_head
pre_direction_remove:
             x_head <- x_head - alpha * <x_head, d_pre_hat> d_pre_hat

Recommended first run: scan L18 heads, then mean-patch top heads.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
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
        generate_text,
        load_curated_direction_pairs,
        load_privacylens_cases,
        make_chat_prompt,
        parse_float_list,
        parse_int_list,
        prompt_excerpt,
        score_prompt,
        starts_yes_no,
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
    heads: List[Tuple[int, int]]  # [(layer, head), ...]

    @property
    def total_heads(self) -> int:
        return len(self.heads)

    @property
    def layers_name(self) -> str:
        return ",".join(str(x) for x in sorted(set(L for L, _ in self.heads)))

    @property
    def heads_name(self) -> str:
        return ";".join(f"L{L}H{H}" for L, H in self.heads)


def capture_pre_o_final(model, tokenizer, prompt: str, layers: List[int], max_length: int, device: str) -> Tuple[Dict[int, torch.Tensor], Tuple[Any, ...]]:
    """Return pre-o_proj final-token activations for each target layer.

    Each value is a CPU float32 tensor of shape [hidden_size]. Also returns the
    normal model outputs, so callers can use hidden_states if requested.
    """
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


def build_head_scan_and_cache(
    model,
    tokenizer,
    pairs,
    layers: List[int],
    max_length: int,
    device: str,
    use_chat_template: bool,
) -> Tuple[pd.DataFrame, Dict[int, torch.Tensor], Dict[int, torch.Tensor], Dict[int, torch.Tensor]]:
    """Compute residual directions, A means, and head writer scores.

    Returns:
      scores_df
      residual_dirs[L] = unit D-A residual direction after layer L
      a_mean_pre[L] = mean A pre-o final activation, shape [n_heads, head_dim]
      pre_dirs[L] = unit D-A pre-o direction per head, shape [n_heads, head_dim]
    """
    n_heads, head_dim, hidden = get_head_info(model)
    layers = [int(x) for x in layers]

    # Accumulators.
    res_sum = {L: torch.zeros(hidden, dtype=torch.float64) for L in layers}
    pre_delta_sum = {L: torch.zeros(n_heads, head_dim, dtype=torch.float64) for L in layers}
    pre_a_sum = {L: torch.zeros(n_heads, head_dim, dtype=torch.float64) for L in layers}
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
            pre_delta_sum[L] += (pd_ - pa)
        n += 1

    if n == 0:
        raise ValueError("No A/D direction pairs loaded")

    residual_dirs: Dict[int, torch.Tensor] = {}
    a_mean_pre: Dict[int, torch.Tensor] = {}
    pre_dirs: Dict[int, torch.Tensor] = {}
    rows = []

    for L in layers:
        d = res_sum[L] / float(n)
        d = d / (d.norm() + 1e-12)
        residual_dirs[L] = d.float()

        a_mean = pre_a_sum[L] / float(n)
        delta = pre_delta_sum[L] / float(n)
        a_mean_pre[L] = a_mean.float()
        # Unit D-A direction inside each head's pre-o space.
        pd_unit = delta / (delta.norm(dim=1, keepdim=True) + 1e-12)
        pre_dirs[L] = pd_unit.float()

        W = get_o_proj(model, L).weight.detach().float().cpu()  # [hidden, hidden]
        for h in range(n_heads):
            s = h * head_dim
            e = (h + 1) * head_dim
            delta_h = delta[h].float()  # [head_dim]
            W_h = W[:, s:e]             # [hidden, head_dim]
            contrib_gap = torch.matmul(W_h, delta_h)  # [hidden]
            writer_score = float(torch.dot(contrib_gap, residual_dirs[L]))
            rows.append({
                "layer": int(L),
                "head": int(h),
                "writer_score": writer_score,
                "abs_writer_score": abs(writer_score),
                "pre_delta_norm": float(delta_h.norm()),
                "contrib_gap_norm": float(contrib_gap.norm()),
                "direction_dot": writer_score,
                "n_pairs": int(n),
            })

    scores = pd.DataFrame(rows).sort_values("writer_score", ascending=False).reset_index(drop=True)
    return scores, residual_dirs, a_mean_pre, pre_dirs


def save_head_cache(out_dir: Path, residual_dirs, a_mean_pre, pre_dirs, layers):
    out = {
        "layers": [int(x) for x in layers],
        "residual_dirs": {int(k): v.cpu() for k, v in residual_dirs.items()},
        "a_mean_pre": {int(k): v.cpu() for k, v in a_mean_pre.items()},
        "pre_dirs": {int(k): v.cpu() for k, v in pre_dirs.items()},
    }
    torch.save(out, out_dir / "attention_head_cache.pt")


def load_head_cache(path: str):
    obj = torch.load(path, map_location="cpu")
    return obj["residual_dirs"], obj["a_mean_pre"], obj["pre_dirs"]


def build_head_selections(scores: pd.DataFrame, layers: List[int], topks: List[int], selection_mode: str, random_controls: int, seed: int) -> Tuple[List[HeadSelection], pd.DataFrame]:
    rng = np.random.default_rng(seed)
    layers = [int(x) for x in layers]
    scores = scores[scores["layer"].astype(int).isin(layers)].copy()
    scores = scores.sort_values("writer_score", ascending=False).reset_index(drop=True)
    max_k = max(topks)
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


class HeadPatch:
    def __init__(self, model, selection: HeadSelection, a_mean_pre, pre_dirs, alpha: float, patch_mode: str):
        self.model = model
        self.selection = selection
        self.a_mean_pre = a_mean_pre
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
                    target = self.a_mean_pre[int(L)][int(H)].to(device=device, dtype=dtype).view(1, -1)
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


def score_with_head_patch(model, tokenizer, prompt, yes_ids, no_ids, max_length, device, selection, a_mean_pre, pre_dirs, alpha, patch_mode):
    with HeadPatch(model, selection, a_mean_pre, pre_dirs, alpha=alpha, patch_mode=patch_mode):
        return score_prompt(model, tokenizer, prompt, yes_ids, no_ids, max_length, device)


def generate_with_head_patch(model, tokenizer, prompt, max_length, max_new_tokens, device, selection, a_mean_pre, pre_dirs, alpha, patch_mode, do_sample=False, temperature=0.0):
    with HeadPatch(model, selection, a_mean_pre, pre_dirs, alpha=alpha, patch_mode=patch_mode):
        return generate_text(model, tokenizer, prompt, max_length, max_new_tokens, device, do_sample=do_sample, temperature=temperature)


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    group_cols = ["level", "selection_name", "control_type", "layers", "heads", "k", "total_heads", "random_id", "patch_mode", "alpha"]
    for keys, g in df.groupby(group_cols, dropna=False):
        d = dict(zip(group_cols, keys))
        n = len(g)
        d.update({
            "n": n,
            "normal_no_count": int((g["normal_decision"] == "No").sum()),
            "normal_yes_count": int((g["normal_decision"] == "Yes").sum()),
            "normal_margin_mean": float(g["normal_margin"].mean()),
            "patched_margin_mean": float(g["patched_margin"].mean()),
            "delta_toward_yes_mean": float(g["delta_toward_yes"].mean()),
            "patched_yes_count": int((g["patched_decision"] == "Yes").sum()),
            "patched_yes_rate": float((g["patched_decision"] == "Yes").mean()),
            "no_to_yes_flips": int(((g["normal_decision"] == "No") & (g["patched_decision"] == "Yes")).sum()),
            "no_to_yes_flip_rate": float(((g["normal_decision"] == "No") & (g["patched_decision"] == "Yes")).mean()),
        })
        rows.append(d)
    return pd.DataFrame(rows).sort_values(["control_type", "alpha", "selection_name"]).reset_index(drop=True)


def write_qual_md(path: Path, qdf: pd.DataFrame):
    lines = ["# Attention head patch qualitative generations\n"]
    for _, r in qdf.iterrows():
        lines.append(f"## {r['selection_name']} | mode={r['patch_mode']} alpha={r['alpha']} | case {r['case_index']}\n")
        lines.append(f"- heads: `{r['heads']}`")
        lines.append(f"- normal decision/margin: {r['normal_decision']} / {r['normal_margin']:.3f}")
        lines.append(f"- patched decision/margin: {r['patched_decision']} / {r['patched_margin']:.3f}")
        lines.append(f"- generation starts: {r['patched_generation_starts']}\n")
        lines.append("Prompt excerpt:\n")
        lines.append("```text")
        lines.append(str(r["prompt_excerpt"]))
        lines.append("```\n")
        lines.append("Patched generation:\n")
        lines.append("```text")
        lines.append(str(r["patched_generation"]))
        lines.append("```\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--privacy-input", required=True)
    ap.add_argument("--direction-data", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="float16")
    ap.add_argument("--device-map", default=None)
    ap.add_argument("--layers", required=True, help="Comma-separated attention layers, e.g. 18 or 16,17,18,19")
    ap.add_argument("--topks", default="1,3,5")
    ap.add_argument("--alphas", default="1.0")
    ap.add_argument("--patch-mode", choices=["mean_patch", "zero", "pre_direction_remove"], default="mean_patch")
    ap.add_argument("--selection-mode", choices=["layerwise", "global"], default="layerwise")
    ap.add_argument("--random-controls", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--level", choices=["seed", "vignette", "trajectory", "trajectory_enhancing"], default="trajectory")
    ap.add_argument("--trajectory-style", choices=["simple", "official"], default="simple")
    ap.add_argument("--privacylens-root", default="raw/PrivacyLens")
    ap.add_argument("--prompt-format", choices=["yesno_reason", "yesno_only", "official_ab"], default="yesno_reason")
    ap.add_argument("--no-chat-template", action="store_true")
    ap.add_argument("--max-direction-pairs", type=int, default=None)
    ap.add_argument("--max-cases", type=int, default=None)
    ap.add_argument("--only-normal-no", action="store_true")
    ap.add_argument("--max-length", type=int, default=2048)
    ap.add_argument("--max-new-tokens", type=int, default=70)
    ap.add_argument("--n-gen-per-config", type=int, default=5)
    ap.add_argument("--scan-only", action="store_true")
    ap.add_argument("--do-sample", action="store_true")
    ap.add_argument("--temperature", type=float, default=0.0)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    layers = parse_int_list(args.layers)
    topks = parse_int_list(args.topks)
    alphas = parse_float_list(args.alphas)

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

    pairs = load_curated_direction_pairs(args.direction_data, max_pairs=args.max_direction_pairs)
    print(f"Loaded {len(pairs)} A/D direction pairs")
    scores, residual_dirs, a_mean_pre, pre_dirs = build_head_scan_and_cache(
        model, tokenizer, pairs, layers, args.max_length, args.device,
        use_chat_template=not args.no_chat_template,
    )
    scores.to_csv(out_dir / "attention_head_writer_scores.csv", index=False)
    save_head_cache(out_dir, residual_dirs, a_mean_pre, pre_dirs, layers)
    print("Top heads:")
    print(scores.head(20).to_string(index=False))

    selections, sel_df = build_head_selections(scores, layers, topks, args.selection_mode, args.random_controls, args.seed)
    sel_df.to_csv(out_dir / "selected_heads.csv", index=False)

    if args.scan_only:
        print("Scan-only requested; stopping after attention_head_writer_scores.csv")
        return

    yes_ids = token_ids_for_variants(tokenizer, A_VARIANTS)
    no_ids = token_ids_for_variants(tokenizer, B_VARIANTS)

    traj_builder = None
    if args.trajectory_style == "official":
        traj_builder = OfficialTrajectoryBuilder(args.privacylens_root)

    raw_cases = load_privacylens_cases(args.privacy_input)
    if args.max_cases:
        raw_cases = raw_cases[: int(args.max_cases)]

    prompts = []
    normal_rows = []
    for i, case in enumerate(tqdm(raw_cases, desc="Scoring normal PrivacyLens cases")):
        user_prompt = build_privacylens_prompt(args.level, case, args.prompt_format, args.trajectory_style, traj_builder)
        chat_prompt = make_chat_prompt(tokenizer, user_prompt, use_chat_template=not args.no_chat_template)
        sc = score_prompt(model, tokenizer, chat_prompt, yes_ids, no_ids, args.max_length, args.device)
        prompts.append((i, case, user_prompt, chat_prompt, sc))
        normal_rows.append({
            "case_index": i,
            "level": args.level,
            "normal_decision": sc["decision"],
            "normal_yes_score": sc["yes_score"],
            "normal_no_score": sc["no_score"],
            "normal_margin": sc["yes_minus_no_margin"],
            "prompt_excerpt": prompt_excerpt(user_prompt),
        })
    pd.DataFrame(normal_rows).to_csv(out_dir / "normal_privacylens_scores.csv", index=False)

    eval_prompts = prompts
    if args.only_normal_no:
        eval_prompts = [x for x in prompts if x[4]["decision"] == "No"]
    print(f"Evaluating {len(eval_prompts)} prompts after filtering")

    detail_rows = []
    qual_rows = []
    for sel in selections:
        for alpha in alphas:
            print(f"Running {sel.name} mode={args.patch_mode} alpha={alpha} heads={sel.heads_name}")
            gen_done = 0
            for i, case, user_prompt, chat_prompt, normal_sc in tqdm(eval_prompts, desc=f"{sel.name} a={alpha}"):
                patched = score_with_head_patch(
                    model, tokenizer, chat_prompt, yes_ids, no_ids, args.max_length, args.device,
                    sel, a_mean_pre, pre_dirs, alpha=alpha, patch_mode=args.patch_mode,
                )
                delta = patched["yes_minus_no_margin"] - normal_sc["yes_minus_no_margin"]
                row = {
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
                    "normal_decision": normal_sc["decision"],
                    "normal_margin": normal_sc["yes_minus_no_margin"],
                    "patched_decision": patched["decision"],
                    "patched_margin": patched["yes_minus_no_margin"],
                    "delta_toward_yes": delta,
                    "prompt_excerpt": prompt_excerpt(user_prompt),
                }
                detail_rows.append(row)

                if (
                    gen_done < args.n_gen_per_config
                    and normal_sc["decision"] == "No"
                    and patched["decision"] == "Yes"
                    and sel.control_type == "top_heads"
                ):
                    gen = generate_with_head_patch(
                        model, tokenizer, chat_prompt, args.max_length, args.max_new_tokens, args.device,
                        sel, a_mean_pre, pre_dirs, alpha=alpha, patch_mode=args.patch_mode,
                        do_sample=args.do_sample, temperature=args.temperature,
                    )
                    q = dict(row)
                    q["patched_generation"] = gen
                    q["patched_generation_starts"] = starts_yes_no(gen)
                    qual_rows.append(q)
                    gen_done += 1

    detail = pd.DataFrame(detail_rows)
    detail.to_csv(out_dir / "head_patch_detail.csv", index=False)
    summary = summarise(detail)
    summary.to_csv(out_dir / "head_patch_summary.csv", index=False)
    print("\nSummary:")
    print(summary.to_string(index=False))

    qdf = pd.DataFrame(qual_rows)
    qdf.to_csv(out_dir / "qualitative_generation.csv", index=False)
    write_qual_md(out_dir / "qualitative_generation.md", qdf)
    print(f"Saved outputs to {out_dir}")


if __name__ == "__main__":
    main()
