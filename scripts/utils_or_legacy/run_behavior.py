"""
run_behavior.py

Full behavior evaluation: 28 scenarios × 4 versions × 2 models = 224 prompts.

For each prompt, reads Yes/No logits at the final position (right after the
assistant prefix from the chat template) and classifies the model's decision.

Outputs:
  - data/behavior_results.csv   (224 rows: detailed per-prompt logits + correctness)
  - data/behavior_clean.csv     (28 rows: per-scenario clean flags for patching)

A scenario is "clean" for a given experiment when the involved versions are
all answered correctly above the margin threshold. The patching scripts will
use these flags to filter scenarios down to the behavior-clean subset.

Usage:
  python run_behavior.py --seeds data/processed/manual_seed_selection.csv

Runtime: ~5-10 min on an A100, assuming both models are already cached.
"""

from __future__ import annotations

import argparse
import gc
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

import pandas as pd
import torch
from tqdm import tqdm

from ci_dataset import load_seeds, make_variants


# ---------------------------------------------------------------------------
# Model identifiers
# ---------------------------------------------------------------------------

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
CI_MODEL = "huseyinatahaninan/Qwen2.5-7B-Instruct-CI"


# ---------------------------------------------------------------------------
# Yes/No token lookup (same logic as the format pilot)
# ---------------------------------------------------------------------------

YES_VARIANTS = ["Yes", " Yes", "yes", " yes", "YES", " YES"]
NO_VARIANTS  = ["No",  " No",  "no",  " no",  "NO",  " NO"]


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
    return yes_max, no_max, yes_max - no_max


# ---------------------------------------------------------------------------
# Per-model evaluation
# ---------------------------------------------------------------------------

@dataclass
class BehaviorRow:
    scenario_id: int
    version: str
    condition: str
    expected: str
    model: str
    yes_logit: float
    no_logit: float
    margin: float
    decision: str
    correct: bool
    prompt_len_tokens: int


def evaluate_model(model_id, seeds_df, device, dtype) -> List[BehaviorRow]:
    from transformers import AutoTokenizer, AutoModelForCausalLM

    short = model_id.split("/")[-1]

    print(f"\n[{short}] Loading tokenizer ...")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    yes_ids, no_ids = get_yes_no_token_ids(tokenizer)
    print(f"  Yes token IDs: {yes_ids}")
    print(f"  No  token IDs: {no_ids}")

    print(f"[{short}] Loading model weights ...")
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
    print(f"[{short}] Loaded on {model.device}")

    rows: List[BehaviorRow] = []
    total = len(seeds_df) * 4
    pbar = tqdm(total=total, desc=f"{short:35s}", unit="prompt")

    for _, seed in seeds_df.iterrows():
        variants = make_variants(seed, tokenizer=tokenizer)
        for v_name, variant in variants.items():
            enc = tokenizer(variant.text, return_tensors="pt", add_special_tokens=False)
            input_ids = enc["input_ids"].to(model.device)

            with torch.no_grad():
                out = model(input_ids=input_ids)
            logits_last = out.logits[0, -1, :]

            y, n, m = yes_no_margin(logits_last, yes_ids, no_ids)
            decision = "Yes" if m > 0 else "No"

            rows.append(BehaviorRow(
                scenario_id=int(seed["scenario_id"]),
                version=v_name,
                condition=variant.condition,
                expected=variant.expected,
                model=model_id,
                yes_logit=float(y),
                no_logit=float(n),
                margin=float(m),
                decision=decision,
                correct=(decision == variant.expected),
                prompt_len_tokens=int(input_ids.shape[1]),
            ))
            pbar.update(1)

    pbar.close()
    del model, tokenizer
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()
    return rows


# ---------------------------------------------------------------------------
# Clean-flag computation (the filter downstream patching uses)
# ---------------------------------------------------------------------------

def per_scenario_clean(df: pd.DataFrame, margin_threshold: float) -> pd.DataFrame:
    """
    Per (scenario_id, model), check which versions are clean. A version is
    clean if the decision is correct AND |margin| >= threshold (confident).
    """
    rows = []
    for (sid, model), g in df.groupby(["scenario_id", "model"]):
        by_v = {row["version"]: row for _, row in g.iterrows()}
        if not all(v in by_v for v in "ABCD"):
            continue

        def is_clean(v):
            r = by_v[v]
            return bool(r["correct"]) and abs(r["margin"]) >= margin_threshold

        rows.append({
            "scenario_id": sid,
            "model": model,
            "clean_A": is_clean("A"),
            "clean_B": is_clean("B"),
            "clean_C": is_clean("C"),
            "clean_D": is_clean("D"),
            "clean_AD": is_clean("A") and is_clean("D"),
            "clean_AB": is_clean("A") and is_clean("B"),
            "clean_AC": is_clean("A") and is_clean("C"),
            "clean_ABCD": all(is_clean(v) for v in "ABCD"),
            "margin_A": by_v["A"]["margin"],
            "margin_B": by_v["B"]["margin"],
            "margin_C": by_v["C"]["margin"],
            "margin_D": by_v["D"]["margin"],
        })
    return pd.DataFrame(rows)


def cross_model_summary(per_model: pd.DataFrame,
                        base_model: str, ci_model: str) -> pd.DataFrame:
    """
    Merge base/CI per-scenario flags so each row tells you whether a scenario
    is clean on base, on CI, and on BOTH (which is what the patching
    comparison needs).
    """
    base = per_model[per_model["model"] == base_model].set_index("scenario_id")
    ci = per_model[per_model["model"] == ci_model].set_index("scenario_id")
    sids = sorted(set(base.index) & set(ci.index))

    rows = []
    for sid in sids:
        b = base.loc[sid]
        c = ci.loc[sid]
        row = {"scenario_id": int(sid)}
        for flag in ["clean_A", "clean_B", "clean_C", "clean_D",
                     "clean_AD", "clean_AB", "clean_AC", "clean_ABCD"]:
            row[f"base_{flag}"] = bool(b[flag])
            row[f"ci_{flag}"] = bool(c[flag])
            row[f"both_{flag}"] = bool(b[flag] and c[flag])
        for v in "ABCD":
            row[f"base_margin_{v}"] = float(b[f"margin_{v}"])
            row[f"ci_margin_{v}"] = float(c[f"margin_{v}"])
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(detail_df: pd.DataFrame, clean_df: pd.DataFrame,
           base_model: str, ci_model: str, margin_threshold: float):
    print("\n" + "=" * 78)
    print("BEHAVIOR EVALUATION — PER-MODEL OVERALL ACCURACY")
    print("=" * 78)

    for model in [base_model, ci_model]:
        sub = detail_df[detail_df["model"] == model]
        if len(sub) == 0:
            continue
        acc = sub["correct"].mean()
        per_v = {v: sub[sub["version"] == v]["correct"].mean() for v in "ABCD"}
        margins = {v: sub[sub["version"] == v]["margin"].mean() for v in "ABCD"}
        short = model.split("/")[-1]
        print(f"\n  {short}")
        print(f"    overall accuracy: {acc:.0%}  ({int(sub['correct'].sum())}/{len(sub)})")
        print(f"    A=Yes  {per_v['A']:>5.0%}   mean margin = {margins['A']:+7.2f}")
        print(f"    B=No   {per_v['B']:>5.0%}   mean margin = {margins['B']:+7.2f}")
        print(f"    C=No   {per_v['C']:>5.0%}   mean margin = {margins['C']:+7.2f}")
        print(f"    D=No   {per_v['D']:>5.0%}   mean margin = {margins['D']:+7.2f}")

    print("\n" + "=" * 78)
    print(f"BEHAVIOR-CLEAN SCENARIOS (margin threshold = {margin_threshold})")
    print("=" * 78)
    print("\nPer-experiment counts of scenarios where BOTH models behave correctly:\n")
    n = len(clean_df)
    print(f"  Total scenarios:                  {n}")
    print(f"  Both models clean on A↔D:         {clean_df['both_clean_AD'].sum():>2} / {n}"
          f"   <-- main final-token patching")
    print(f"  Both models clean on A↔B:         {clean_df['both_clean_AB'].sum():>2} / {n}"
          f"   <-- recipient patching")
    print(f"  Both models clean on A↔C:         {clean_df['both_clean_AC'].sum():>2} / {n}"
          f"   <-- purpose patching")
    print(f"  Both models clean on A,B,C,D:     {clean_df['both_clean_ABCD'].sum():>2} / {n}"
          f"   <-- strictest (everything works)")
    print()
    print(f"  Base-only clean on ABCD:          {clean_df['base_clean_ABCD'].sum():>2} / {n}")
    print(f"  CI-only clean on ABCD:            {clean_df['ci_clean_ABCD'].sum():>2} / {n}")

    # Per-scenario detail
    print("\n" + "-" * 78)
    print("Per-scenario detail (✓ = clean):\n")
    print(f"  {'sid':>3}  {'base_AD':>7}  {'ci_AD':>5}  {'both_AD':>7}  "
          f"{'base_ABCD':>9}  {'ci_ABCD':>7}  {'both_ABCD':>9}")
    for _, row in clean_df.sort_values("scenario_id").iterrows():
        tick = lambda b: "✓" if b else " "
        print(f"  {int(row['scenario_id']):>3}  "
              f"{tick(row['base_clean_AD']):>7}  {tick(row['ci_clean_AD']):>5}  "
              f"{tick(row['both_clean_AD']):>7}  "
              f"{tick(row['base_clean_ABCD']):>9}  {tick(row['ci_clean_ABCD']):>7}  "
              f"{tick(row['both_clean_ABCD']):>9}")

    print("\n" + "=" * 78)
    print("NEXT STEP")
    print("=" * 78)
    n_ad = int(clean_df['both_clean_AD'].sum())
    print(f"\nThe patching scripts will filter scenarios using these flags:")
    print(f"  - Final-token A↔D patching uses scenarios with both_clean_AD = True  ({n_ad}/{n})")
    print(f"  - Recipient A↔B patching uses scenarios with both_clean_AB = True   "
          f"({int(clean_df['both_clean_AB'].sum())}/{n})")
    print(f"  - Purpose A↔C patching uses scenarios with both_clean_AC = True     "
          f"({int(clean_df['both_clean_AC'].sum())}/{n})")
    print()
    print("Cross-reference with validation_summary.csv to also apply the strict-")
    print("span (Option B) length-matching filter on top of behavior cleanliness.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Full behavior eval on base + CI Qwen2.5-7B for all 28 scenarios."
    )
    parser.add_argument("--seeds", default="data/processed/manual_seed_selection.csv")
    parser.add_argument("--out-detail", default="data/behavior_results.csv")
    parser.add_argument("--out-clean", default="data/behavior_clean.csv")
    parser.add_argument("--margin-threshold", type=float, default=0.0,
                        help="A version is 'clean' only if |margin| >= this. "
                             "0 means correct sign is enough; try 1.0 or 2.0 "
                             "if you want to keep only confidently-classified rows.")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu",
                        choices=["cuda", "cpu"])
    parser.add_argument("--dtype", default="bfloat16",
                        choices=["bfloat16", "float16", "float32"])
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--ci-model", default=CI_MODEL)
    parser.add_argument("--base-only", action="store_true",
                        help="Skip the CI model (smoke test).")
    args = parser.parse_args()

    dtype = {"bfloat16": torch.bfloat16,
             "float16": torch.float16,
             "float32": torch.float32}[args.dtype]

    print(f"Device: {args.device}   dtype: {args.dtype}")
    if args.device == "cuda":
        print(f"CUDA device: {torch.cuda.get_device_name(0)}  "
              f"({torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB)")

    print(f"\nLoading seeds from {args.seeds} ...")
    seeds = load_seeds(args.seeds)
    print(f"  -> {len(seeds)} scenarios")

    models_to_run = [args.base_model]
    if not args.base_only:
        models_to_run.append(args.ci_model)

    all_rows: List[BehaviorRow] = []
    for mid in models_to_run:
        rows = evaluate_model(mid, seeds, args.device, dtype)
        all_rows.extend(rows)

    detail_df = pd.DataFrame([asdict(r) for r in all_rows])
    Path(args.out_detail).parent.mkdir(parents=True, exist_ok=True)
    detail_df.to_csv(args.out_detail, index=False)
    print(f"\nSaved per-prompt detail: {args.out_detail}  ({len(detail_df)} rows)")

    if not args.base_only:
        per_model = per_scenario_clean(detail_df, args.margin_threshold)
        clean_df = cross_model_summary(per_model, args.base_model, args.ci_model)
        clean_df.to_csv(args.out_clean, index=False)
        print(f"Saved per-scenario clean flags: {args.out_clean}  ({len(clean_df)} rows)")
        report(detail_df, clean_df, args.base_model, args.ci_model, args.margin_threshold)
    else:
        print("\n(--base-only set; skipping cross-model clean flags and report.)")


if __name__ == "__main__":
    main()
