#!/usr/bin/env python3
"""
Base-model PrivacyLens direction tests using CI-discovered writer neurons.

This script tests two complementary questions on real PrivacyLens prompts:

1) Base normal-No cases: does removing the discovered writer neurons' refusal-direction
   contribution break base rejection?  Expected: No -> Yes if base uses same circuit.

2) Base normal-Yes cases: can adding the CI writer-neuron refusal contribution rescue
   base failures?  Expected: Yes -> No on disallowed/privacy prompts.

It reuses helper functions from scripts/privacylens_direction_ablation_generation.py.
So keep that file in the same scripts/ directory.

Recommended first run:

python scripts/base_privacylens_direction_remove_rescue.py \
  --privacy-input data/raw/PrivacyLens/data/main_data.json \
  --direction-cache results/pl_trajectory_direction_ablation_gen/direction_vectors.pt \
  --direction-data data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
  --ci-writer-scores results/clean304/mlp_neuron_writer/mlp_writer_scores.csv \
  --out-dir results/base_pl_trajectory_remove_rescue \
  --model Qwen/Qwen2.5-7B-Instruct \
  --device cuda \
  --dtype float16 \
  --level trajectory \
  --trajectory-style simple \
  --prompt-format yesno_reason \
  --layer 22 \
  --topks 50,100,200,500 \
  --remove-alphas 1,2,4,6 \
  --rescue-alphas 0.25,0.5,1,2,4 \
  --random-controls 1 \
  --n-gen-per-config 5 \
  --max-new-tokens 90

Outputs:
- normal_base_privacylens_scores.csv
- selected_neurons.csv
- selected_neuron_ref_scales.csv
- base_remove_detail.csv / base_remove_summary.csv
- base_rescue_detail.csv / base_rescue_summary.csv
- qualitative_remove_generation.csv/.md
- qualitative_rescue_generation.csv/.md
"""

from __future__ import annotations

import argparse
import math
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from tqdm.auto import tqdm
from transformers import AutoModelForCausalLM, AutoTokenizer

# Import helpers from the previous script. Put both scripts in the same directory.
try:
    from privacylens_direction_ablation_generation import (
        YES_VARIANTS,
        NO_VARIANTS,
        A_VARIANTS,
        B_VARIANTS,
        Selection,
        parse_int_list,
        parse_float_list,
        token_ids_for_variants,
        make_chat_prompt,
        encode_prompt,
        yes_no_scores_from_logits,
        score_prompt,
        generate_text,
        load_writer_scores,
        build_selections,
        get_or_compute_directions,
        load_privacylens_cases,
        build_privacylens_prompt,
        OfficialTrajectoryBuilder,
        prompt_excerpt,
    )
except Exception as e:
    raise SystemExit(
        "Could not import helpers from privacylens_direction_ablation_generation.py.\n"
        "Make sure both scripts are in the same scripts/ directory, and replace that helper script with v2 if needed.\n"
        f"Original error: {type(e).__name__}: {e}"
    )


def text_decision(s: str) -> str:
    t = (s or "").strip().lower()
    t = re.sub(r"^[\s\(]*", "", t)
    if t.startswith("yes") or t.startswith("a"):
        return "Yes"
    if t.startswith("no") or t.startswith("b"):
        return "No"
    return "Other"


def safe_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


# -----------------------------
# Direction-edit hook
# -----------------------------


def install_direction_edit_hook(
    model,
    selection: Selection,
    direction: torch.Tensor,
    alpha: float,
    operation: str,
    add_scale: float = 0.0,
    signed_removal: bool = False,
):
    """Patch only the final position of the selected layer's MLP output.

    operation="remove":
        y_selected = sum_j m_j W_down[:,j]
        p = <y_selected, d>
        out_final <- out_final - alpha * max(p,0) * d

    operation="add":
        out_final <- out_final + alpha * add_scale * d

    The add operation is a rescue test: add the CI selected-neuron D-A contribution
    scale along the refusal direction. It is more artificial than removal, but tests
    whether a CI-like writer contribution can rescue base Yes failures.
    """
    if operation not in {"remove", "add"}:
        raise ValueError(f"operation must be remove or add, got {operation}")

    layer_idx = int(selection.layer)
    mlp = model.model.layers[layer_idx].mlp
    orig_forward = mlp.forward
    neuron_list = [int(x) for x in selection.neurons]
    cache = {"idx": None, "d": None, "W": None, "device": None, "dtype": None}

    def forward(x):
        gate = mlp.gate_proj(x)
        up = mlp.up_proj(x)
        m = mlp.act_fn(gate) * up
        out = mlp.down_proj(m)

        if cache["device"] != m.device or cache["dtype"] != m.dtype:
            idx = torch.tensor(neuron_list, device=m.device, dtype=torch.long)
            d = direction.to(device=m.device, dtype=m.dtype)
            d = d / (d.norm() + torch.tensor(1e-12, device=m.device, dtype=m.dtype))
            Wcols = mlp.down_proj.weight[:, idx].detach().to(device=m.device, dtype=m.dtype)
            cache.update({"idx": idx, "d": d, "W": Wcols, "device": m.device, "dtype": m.dtype})

        d = cache["d"]
        out = out.clone()

        if operation == "remove":
            idx = cache["idx"]
            Wcols = cache["W"]
            m_sel = m[:, -1, :].index_select(dim=-1, index=idx)
            y_sel = torch.matmul(m_sel, Wcols.T)  # [batch, hidden]
            p = (y_sel * d.unsqueeze(0)).sum(dim=-1, keepdim=True)
            if not signed_removal:
                p = torch.clamp(p, min=0)
            out[:, -1, :] = out[:, -1, :] - float(alpha) * p * d.unsqueeze(0)
        else:
            out[:, -1, :] = out[:, -1, :] + float(alpha) * float(add_scale) * d.unsqueeze(0)

        return out

    mlp.forward = forward

    def restore():
        mlp.forward = orig_forward

    return restore


def score_with_edit(
    model,
    tokenizer,
    chat_prompt: str,
    yes_ids: List[int],
    no_ids: List[int],
    max_length: int,
    device: str,
    selection: Selection,
    direction: torch.Tensor,
    alpha: float,
    operation: str,
    add_scale: float = 0.0,
    signed_removal: bool = False,
) -> Dict[str, Any]:
    restore = install_direction_edit_hook(
        model, selection, direction, alpha=alpha, operation=operation,
        add_scale=add_scale, signed_removal=signed_removal,
    )
    try:
        return score_prompt(model, tokenizer, chat_prompt, yes_ids, no_ids, max_length, device)
    finally:
        restore()


def generate_with_edit(
    model,
    tokenizer,
    chat_prompt: str,
    max_length: int,
    max_new_tokens: int,
    device: str,
    selection: Selection,
    direction: torch.Tensor,
    alpha: float,
    operation: str,
    add_scale: float = 0.0,
    signed_removal: bool = False,
    do_sample: bool = False,
    temperature: float = 0.7,
) -> str:
    restore = install_direction_edit_hook(
        model, selection, direction, alpha=alpha, operation=operation,
        add_scale=add_scale, signed_removal=signed_removal,
    )
    try:
        return generate_text(
            model, tokenizer, chat_prompt, max_length, max_new_tokens, device,
            do_sample=do_sample, temperature=temperature,
        )
    finally:
        restore()


# -----------------------------
# Selection scale for rescue
# -----------------------------


def compute_ref_scales(selected_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, g in selected_df.groupby("selection_name"):
        scores = pd.to_numeric(g["writer_score"], errors="coerce").fillna(0.0).to_numpy(float)
        rows.append({
            "selection_name": name,
            "control_type": g["control_type"].iloc[0],
            "layer": int(g["layer"].iloc[0]),
            "k": int(g["k"].iloc[0]),
            "random_id": int(g["random_id"].iloc[0]),
            "score_sum": float(scores.sum()),
            "positive_score_sum": float(np.maximum(scores, 0).sum()),
            "abs_score_sum": float(np.abs(scores).sum()),
            "score_mean": float(scores.mean()) if len(scores) else 0.0,
        })
    return pd.DataFrame(rows)


def get_add_scale(scale_table: pd.DataFrame, selection_name: str, mode: str) -> float:
    r = scale_table[scale_table["selection_name"].eq(selection_name)]
    if r.empty:
        return 0.0
    if mode == "positive_score_sum":
        return float(r["positive_score_sum"].iloc[0])
    if mode == "score_sum":
        return float(r["score_sum"].iloc[0])
    if mode == "abs_score_sum":
        return float(r["abs_score_sum"].iloc[0])
    raise ValueError(f"unknown add scale mode: {mode}")


# -----------------------------
# Summaries and markdown
# -----------------------------


def summarize_remove(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    def agg(g):
        flips = g["normal_decision"].eq("No") & g["patched_decision"].eq("Yes")
        return pd.Series({
            "n": len(g),
            "normal_no_count": int(g["normal_decision"].eq("No").sum()),
            "normal_margin_mean": float(g["normal_yes_minus_no_margin"].mean()),
            "patched_margin_mean": float(g["patched_yes_minus_no_margin"].mean()),
            "delta_toward_yes_mean": float(g["delta_toward_yes"].mean()),
            "no_to_yes_flips": int(flips.sum()),
            "no_to_yes_flip_rate": float(flips.mean()) if len(g) else 0.0,
        })

    return df.groupby(["level", "selection_name", "control_type", "layer", "k", "alpha", "random_id"], dropna=False).apply(agg).reset_index()


def summarize_rescue(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    def agg(g):
        flips = g["normal_decision"].eq("Yes") & g["patched_decision"].eq("No")
        return pd.Series({
            "n": len(g),
            "normal_yes_count": int(g["normal_decision"].eq("Yes").sum()),
            "normal_margin_mean": float(g["normal_yes_minus_no_margin"].mean()),
            "patched_margin_mean": float(g["patched_yes_minus_no_margin"].mean()),
            "delta_toward_no_mean": float((-g["delta_toward_yes"]).mean()),
            "yes_to_no_flips": int(flips.sum()),
            "yes_to_no_flip_rate": float(flips.mean()) if len(g) else 0.0,
        })

    return df.groupby(["level", "selection_name", "control_type", "layer", "k", "alpha", "random_id", "add_scale"], dropna=False).apply(agg).reset_index()


def write_markdown(rows: List[Dict[str, Any]], path: Path, title: str, patched_label: str):
    lines = [f"# {title}\n"]
    if not rows:
        lines.append("No qualitative examples were produced.\n")
    for r in rows:
        lines.append(f"\n## {r['selection_name']} alpha={r['alpha']} case={r['case_index']}\n")
        lines.append(
            f"Source: `{r.get('source','')}` | Data: `{r.get('data_type','')}` | "
            f"normal margin={safe_float(r.get('normal_yes_minus_no_margin')):.3f} | "
            f"patched margin={safe_float(r.get('patched_yes_minus_no_margin')):.3f}\n"
        )
        lines.append("### Prompt excerpt\n")
        lines.append("```text\n" + prompt_excerpt(r.get("user_prompt", "")) + "\n```\n")
        lines.append("### Normal base\n")
        lines.append("```text\n" + r.get("normal_generation", "") + "\n```\n")
        lines.append(f"### {patched_label}\n")
        lines.append("```text\n" + r.get("patched_generation", "") + "\n```\n")
        lines.append("### Random-neuron control\n")
        lines.append("```text\n" + r.get("random_generation", "") + "\n```\n")
    path.write_text("\n".join(lines), encoding="utf-8")


# -----------------------------
# Main
# -----------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--privacy-input", required=True, help="PrivacyLens main_data.json or compatible CSV")
    ap.add_argument("--direction-cache", default=None, help="Recommended: CI direction_vectors.pt from previous CI run")
    ap.add_argument("--direction-data", default=None, help="Curated CLEAN304 CSV; used if direction cache absent")
    ap.add_argument("--ci-writer-scores", required=True, help="mlp_writer_scores.csv from CI writer scan")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct", help="Base model to test")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="float16", choices=["float16", "bfloat16", "float32"])
    ap.add_argument("--level", default="trajectory", choices=["seed", "vignette", "trajectory", "trajectory_enhancing"])
    ap.add_argument("--prompt-format", default="yesno_reason", choices=["yesno_reason", "yesno_only", "official_ab"])
    ap.add_argument("--trajectory-style", default="simple", choices=["simple", "official", "auto"])
    ap.add_argument("--privacylens-root", default=None)
    ap.add_argument("--layer", type=int, default=22)
    ap.add_argument("--topks", default="50,100,200,500")
    ap.add_argument("--remove-alphas", default="1,2,4,6")
    ap.add_argument("--rescue-alphas", default="0.25,0.5,1,2,4")
    ap.add_argument("--random-controls", type=int, default=1)
    ap.add_argument("--random-seed", type=int, default=0)
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--max-length", type=int, default=8192)
    ap.add_argument("--max-direction-pairs", type=int, default=None)
    ap.add_argument("--recompute-directions", action="store_true")
    ap.add_argument("--signed-removal", action="store_true")
    ap.add_argument("--no-chat-template", action="store_true")
    ap.add_argument("--trust-remote-code", action="store_true")
    ap.add_argument("--tasks", default="remove,rescue", help="comma list: remove,rescue")
    ap.add_argument("--rescue-add-scale", default="positive_score_sum", choices=["positive_score_sum", "score_sum", "abs_score_sum"])
    ap.add_argument("--n-gen-per-config", type=int, default=5)
    ap.add_argument("--max-new-tokens", type=int, default=90)
    ap.add_argument("--do-sample", action="store_true")
    ap.add_argument("--temperature", type=float, default=0.7)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    random.seed(args.random_seed)
    np.random.seed(args.random_seed)
    torch.manual_seed(args.random_seed)

    topks = parse_int_list(args.topks)
    remove_alphas = parse_float_list(args.remove_alphas)
    rescue_alphas = parse_float_list(args.rescue_alphas)
    tasks = {x.strip() for x in args.tasks.split(",") if x.strip()}
    layers = [args.layer]

    dtype_map = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=args.trust_remote_code)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=dtype_map[args.dtype],
        device_map="auto" if args.device == "cuda" else None,
        trust_remote_code=args.trust_remote_code,
    )
    if args.device != "cuda":
        model = model.to(args.device)
    model.eval()
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    if args.prompt_format == "official_ab":
        yes_ids = token_ids_for_variants(tokenizer, A_VARIANTS)
        no_ids = token_ids_for_variants(tokenizer, B_VARIANTS)
    else:
        yes_ids = token_ids_for_variants(tokenizer, YES_VARIANTS)
        no_ids = token_ids_for_variants(tokenizer, NO_VARIANTS)
    print("yes_ids:", yes_ids)
    print("no_ids:", no_ids)

    # Use CI direction cache if provided. If not, compute on this target model from curated A/D pairs.
    directions = get_or_compute_directions(args, model, tokenizer, layers)

    writer = load_writer_scores(args.ci_writer_scores)
    selections, selected_df = build_selections(writer, args.layer, topks, args.random_controls, args.random_seed)
    selected_df.to_csv(out_dir / "selected_neurons.csv", index=False)
    scale_df = compute_ref_scales(selected_df)
    scale_df.to_csv(out_dir / "selected_neuron_ref_scales.csv", index=False)
    scale_map = {r.selection_name: get_add_scale(scale_df, r.selection_name, args.rescue_add_scale) for r in scale_df.itertuples(index=False)}

    # Prompts.
    cases = load_privacylens_cases(args.privacy_input)
    cases = cases[args.start:]
    if args.max_rows is not None:
        cases = cases[:args.max_rows]

    traj_style = args.trajectory_style
    traj_builder = None
    if args.level in ["trajectory", "trajectory_enhancing"] and traj_style in ["official", "auto"]:
        try:
            if not args.privacylens_root:
                raise FileNotFoundError("--privacylens-root not provided")
            traj_builder = OfficialTrajectoryBuilder(args.privacylens_root)
            traj_style = "official"
            print(f"Using official trajectory builder from {args.privacylens_root}")
        except Exception as e:
            if args.trajectory_style == "official":
                raise
            traj_style = "simple"
            print(f"[WARN] official trajectory unavailable ({type(e).__name__}: {e}); using simple trajectory prompts")

    prompt_cache: Dict[int, Tuple[str, str]] = {}
    normal_rows = []
    for local_idx, case in enumerate(tqdm(cases, desc=f"Normal base pass ({args.level})")):
        case_index = args.start + local_idx
        try:
            user_prompt = build_privacylens_prompt(args.level, case, args.prompt_format, traj_style, traj_builder)
            chat_prompt = make_chat_prompt(tokenizer, user_prompt, use_chat_template=not args.no_chat_template)
            prompt_cache[case_index] = (user_prompt, chat_prompt)
            res = score_prompt(model, tokenizer, chat_prompt, yes_ids, no_ids, args.max_length, args.device)
            seed = case.get("seed", {})
            normal_rows.append({
                "case_index": case_index,
                "name": case.get("name", f"case_{case_index}"),
                "level": args.level,
                "normal_decision": res["decision"],
                "normal_yes_score": res["yes_score"],
                "normal_no_score": res["no_score"],
                "normal_yes_minus_no_margin": res["yes_minus_no_margin"],
                "source": seed.get("source", ""),
                "data_type": seed.get("data_type", ""),
                "data_subject": seed.get("data_subject", ""),
                "data_sender": seed.get("data_sender", ""),
                "data_recipient": seed.get("data_recipient", ""),
                "transmission_principle": seed.get("transmission_principle", ""),
                "prompt_chars": len(user_prompt),
                "error": "",
            })
        except Exception as e:
            normal_rows.append({
                "case_index": case_index,
                "name": case.get("name", f"case_{case_index}"),
                "level": args.level,
                "normal_decision": "ERROR",
                "normal_yes_score": np.nan,
                "normal_no_score": np.nan,
                "normal_yes_minus_no_margin": np.nan,
                "source": case.get("seed", {}).get("source", ""),
                "data_type": case.get("seed", {}).get("data_type", ""),
                "data_subject": case.get("seed", {}).get("data_subject", ""),
                "data_sender": case.get("seed", {}).get("data_sender", ""),
                "data_recipient": case.get("seed", {}).get("data_recipient", ""),
                "transmission_principle": case.get("seed", {}).get("transmission_principle", ""),
                "prompt_chars": np.nan,
                "error": f"{type(e).__name__}: {e}",
            })

    normal_df = pd.DataFrame(normal_rows)
    normal_df.to_csv(out_dir / "normal_base_privacylens_scores.csv", index=False)
    valid = normal_df[normal_df["normal_decision"].isin(["Yes", "No"])].copy()
    base_no_df = valid[valid["normal_decision"].eq("No")].copy()
    base_yes_df = valid[valid["normal_decision"].eq("Yes")].copy()
    print("\nBase normal summary:")
    print(valid.groupby("normal_decision").size().to_string())
    print(f"Base normal-No cases for destructive remove: {len(base_no_df)}")
    print(f"Base normal-Yes cases for rescue add: {len(base_yes_df)}")

    # ------------------
    # Remove on base No.
    # ------------------
    if "remove" in tasks and not base_no_df.empty:
        detail_rows = []
        total = len(base_no_df) * len(selections) * len(remove_alphas)
        pbar = tqdm(total=total, desc="Base No: remove refusal contribution")
        for r in base_no_df.itertuples(index=False):
            user_prompt, chat_prompt = prompt_cache[int(r.case_index)]
            for sel in selections:
                d = directions[sel.layer]
                for alpha in remove_alphas:
                    try:
                        patched = score_with_edit(
                            model, tokenizer, chat_prompt, yes_ids, no_ids, args.max_length, args.device,
                            sel, d, alpha=alpha, operation="remove", signed_removal=args.signed_removal,
                        )
                        err = ""
                    except Exception as e:
                        patched = {"decision": "ERROR", "yes_score": np.nan, "no_score": np.nan, "yes_minus_no_margin": np.nan}
                        err = f"{type(e).__name__}: {e}"
                    nm = float(r.normal_yes_minus_no_margin)
                    pm = safe_float(patched["yes_minus_no_margin"])
                    detail_rows.append({
                        "case_index": int(r.case_index), "name": r.name, "level": args.level,
                        "source": r.source, "data_type": r.data_type, "data_subject": r.data_subject,
                        "data_sender": r.data_sender, "data_recipient": r.data_recipient,
                        "transmission_principle": r.transmission_principle,
                        "selection_name": sel.name, "control_type": sel.control_type,
                        "layer": sel.layer, "k": sel.k, "random_id": sel.random_id,
                        "alpha": float(alpha), "operation": "remove",
                        "normal_decision": r.normal_decision,
                        "normal_yes_minus_no_margin": nm,
                        "patched_decision": patched["decision"],
                        "patched_yes_minus_no_margin": pm,
                        "delta_toward_yes": pm - nm if np.isfinite(pm) else np.nan,
                        "no_to_yes_flip": int(patched["decision"] == "Yes"),
                        "error": err,
                    })
                    pbar.update(1)
        pbar.close()
        remove_detail = pd.DataFrame(detail_rows)
        remove_detail.to_csv(out_dir / "base_remove_detail.csv", index=False)
        remove_summary = summarize_remove(remove_detail)
        remove_summary.to_csv(out_dir / "base_remove_summary.csv", index=False)
        print("\nBase remove summary (CI-top only):")
        print(remove_summary[remove_summary["control_type"].eq("ci_top_neurons")].to_string(index=False))

        # Generation for successful top flips.
        gen_rows = []
        for sel in [s for s in selections if s.control_type == "ci_top_neurons"]:
            for alpha in remove_alphas:
                sub = remove_detail[
                    remove_detail["selection_name"].eq(sel.name)
                    & remove_detail["alpha"].eq(float(alpha))
                    & remove_detail["no_to_yes_flip"].eq(1)
                ].head(args.n_gen_per_config)
                if sub.empty:
                    continue
                rand_sel = next((s for s in selections if s.control_type == "random_neurons" and s.k == sel.k), None)
                for rr in tqdm(list(sub.itertuples(index=False)), desc=f"Gen remove {sel.name} a={alpha}"):
                    user_prompt, chat_prompt = prompt_cache[int(rr.case_index)]
                    d = directions[sel.layer]
                    normal_gen = generate_text(model, tokenizer, chat_prompt, args.max_length, args.max_new_tokens, args.device, do_sample=args.do_sample, temperature=args.temperature)
                    patched_gen = generate_with_edit(model, tokenizer, chat_prompt, args.max_length, args.max_new_tokens, args.device, sel, d, alpha=float(alpha), operation="remove", signed_removal=args.signed_removal, do_sample=args.do_sample, temperature=args.temperature)
                    random_gen = ""
                    if rand_sel is not None:
                        random_gen = generate_with_edit(model, tokenizer, chat_prompt, args.max_length, args.max_new_tokens, args.device, rand_sel, directions[rand_sel.layer], alpha=float(alpha), operation="remove", signed_removal=args.signed_removal, do_sample=args.do_sample, temperature=args.temperature)
                    gen_rows.append({
                        **rr._asdict(),
                        "user_prompt": user_prompt,
                        "normal_generation": normal_gen,
                        "patched_generation": patched_gen,
                        "random_generation": random_gen,
                        "normal_generated_decision": text_decision(normal_gen),
                        "patched_generated_decision": text_decision(patched_gen),
                        "random_generated_decision": text_decision(random_gen),
                    })
        gen_df = pd.DataFrame(gen_rows)
        gen_df.to_csv(out_dir / "qualitative_remove_generation.csv", index=False)
        write_markdown(gen_rows, out_dir / "qualitative_remove_generation.md", "Base normal-No destructive direction removal", "Writer-neuron refusal contribution removed")

    # ------------------
    # Rescue on base Yes.
    # ------------------
    if "rescue" in tasks and not base_yes_df.empty:
        detail_rows = []
        total = len(base_yes_df) * len(selections) * len(rescue_alphas)
        pbar = tqdm(total=total, desc="Base Yes: add CI writer contribution")
        for r in base_yes_df.itertuples(index=False):
            user_prompt, chat_prompt = prompt_cache[int(r.case_index)]
            for sel in selections:
                d = directions[sel.layer]
                add_scale = scale_map.get(sel.name, 0.0)
                for alpha in rescue_alphas:
                    try:
                        patched = score_with_edit(
                            model, tokenizer, chat_prompt, yes_ids, no_ids, args.max_length, args.device,
                            sel, d, alpha=alpha, operation="add", add_scale=add_scale,
                        )
                        err = ""
                    except Exception as e:
                        patched = {"decision": "ERROR", "yes_score": np.nan, "no_score": np.nan, "yes_minus_no_margin": np.nan}
                        err = f"{type(e).__name__}: {e}"
                    nm = float(r.normal_yes_minus_no_margin)
                    pm = safe_float(patched["yes_minus_no_margin"])
                    detail_rows.append({
                        "case_index": int(r.case_index), "name": r.name, "level": args.level,
                        "source": r.source, "data_type": r.data_type, "data_subject": r.data_subject,
                        "data_sender": r.data_sender, "data_recipient": r.data_recipient,
                        "transmission_principle": r.transmission_principle,
                        "selection_name": sel.name, "control_type": sel.control_type,
                        "layer": sel.layer, "k": sel.k, "random_id": sel.random_id,
                        "alpha": float(alpha), "operation": "add", "add_scale": float(add_scale),
                        "normal_decision": r.normal_decision,
                        "normal_yes_minus_no_margin": nm,
                        "patched_decision": patched["decision"],
                        "patched_yes_minus_no_margin": pm,
                        "delta_toward_yes": pm - nm if np.isfinite(pm) else np.nan,
                        "yes_to_no_flip": int(patched["decision"] == "No"),
                        "error": err,
                    })
                    pbar.update(1)
        pbar.close()
        rescue_detail = pd.DataFrame(detail_rows)
        rescue_detail.to_csv(out_dir / "base_rescue_detail.csv", index=False)
        rescue_summary = summarize_rescue(rescue_detail)
        rescue_summary.to_csv(out_dir / "base_rescue_summary.csv", index=False)
        print("\nBase rescue summary (CI-top only):")
        print(rescue_summary[rescue_summary["control_type"].eq("ci_top_neurons")].to_string(index=False))

        # Generation for successful rescues.
        gen_rows = []
        for sel in [s for s in selections if s.control_type == "ci_top_neurons"]:
            for alpha in rescue_alphas:
                sub = rescue_detail[
                    rescue_detail["selection_name"].eq(sel.name)
                    & rescue_detail["alpha"].eq(float(alpha))
                    & rescue_detail["yes_to_no_flip"].eq(1)
                ].head(args.n_gen_per_config)
                if sub.empty:
                    continue
                rand_sel = next((s for s in selections if s.control_type == "random_neurons" and s.k == sel.k), None)
                for rr in tqdm(list(sub.itertuples(index=False)), desc=f"Gen rescue {sel.name} a={alpha}"):
                    user_prompt, chat_prompt = prompt_cache[int(rr.case_index)]
                    d = directions[sel.layer]
                    add_scale = scale_map.get(sel.name, 0.0)
                    normal_gen = generate_text(model, tokenizer, chat_prompt, args.max_length, args.max_new_tokens, args.device, do_sample=args.do_sample, temperature=args.temperature)
                    patched_gen = generate_with_edit(model, tokenizer, chat_prompt, args.max_length, args.max_new_tokens, args.device, sel, d, alpha=float(alpha), operation="add", add_scale=add_scale, do_sample=args.do_sample, temperature=args.temperature)
                    random_gen = ""
                    if rand_sel is not None:
                        random_add_scale = scale_map.get(rand_sel.name, 0.0)
                        random_gen = generate_with_edit(model, tokenizer, chat_prompt, args.max_length, args.max_new_tokens, args.device, rand_sel, directions[rand_sel.layer], alpha=float(alpha), operation="add", add_scale=random_add_scale, do_sample=args.do_sample, temperature=args.temperature)
                    gen_rows.append({
                        **rr._asdict(),
                        "user_prompt": user_prompt,
                        "normal_generation": normal_gen,
                        "patched_generation": patched_gen,
                        "random_generation": random_gen,
                        "normal_generated_decision": text_decision(normal_gen),
                        "patched_generated_decision": text_decision(patched_gen),
                        "random_generated_decision": text_decision(random_gen),
                    })
        gen_df = pd.DataFrame(gen_rows)
        gen_df.to_csv(out_dir / "qualitative_rescue_generation.csv", index=False)
        write_markdown(gen_rows, out_dir / "qualitative_rescue_generation.md", "Base normal-Yes rescue by CI writer contribution", "CI writer-neuron refusal contribution added")

    print("\nDone. Outputs in:", out_dir)


if __name__ == "__main__":
    main()
