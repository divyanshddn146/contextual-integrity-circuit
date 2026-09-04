#!/usr/bin/env python
"""
mine_ci_improvement_cases.py

Find scenarios where base Qwen fails but CI-tuned Qwen succeeds.

Inputs:
  data/behavior_results_large_180.csv
  data/processed/validation_summary_large_180.csv

Outputs:
  data/ci_improvement_cases_large_180.csv
  data/ci_improvement_eligibility_large_180.csv

The eligibility file is shaped so run_patching.py can use it directly.
"""

import argparse
from pathlib import Path

import pandas as pd


BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
CI_MODEL = "huseyinatahaninan/Qwen2.5-7B-Instruct-CI"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail", default="data/behavior_results_large_180.csv")
    parser.add_argument("--validation", default="data/processed/validation_summary_large_180.csv")
    parser.add_argument("--out-cases", default="data/ci_improvement_cases_large_180.csv")
    parser.add_argument("--out-eligibility", default="data/ci_improvement_eligibility_large_180.csv")
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--ci-model", default=CI_MODEL)
    args = parser.parse_args()

    detail = pd.read_csv(args.detail)
    val = pd.read_csv(args.validation)

    # Make model aliases robust.
    detail["model_kind"] = detail["model"].map({
        args.base_model: "base",
        args.ci_model: "ci",
    })
    if detail["model_kind"].isna().any():
        print("WARNING: some model names did not match base/CI IDs.")
        print(detail[detail["model_kind"].isna()]["model"].unique())

    # Pivot correctness, decisions, margins.
    rows = []
    for sid, g in detail.groupby("scenario_id"):
        row = {"scenario_id": int(sid)}

        for model_kind in ["base", "ci"]:
            gm = g[g["model_kind"] == model_kind]
            for v in ["A", "B", "C", "D"]:
                gv = gm[gm["version"] == v]
                if len(gv) != 1:
                    raise ValueError(f"Missing/duplicate row for sid={sid}, model={model_kind}, version={v}")
                r = gv.iloc[0]
                row[f"{model_kind}_{v}_correct"] = bool(r["correct"])
                row[f"{model_kind}_{v}_decision"] = r["decision"]
                row[f"{model_kind}_{v}_margin"] = float(r["margin"])

        rows.append(row)

    m = pd.DataFrame(rows)

    # Require A correct in both models so A is a clean allowed anchor.
    a_clean_both = m["base_A_correct"] & m["ci_A_correct"]

    # Base-fail / CI-success by variant.
    m["improve_B"] = a_clean_both & (~m["base_B_correct"]) & m["ci_B_correct"]
    m["improve_C"] = a_clean_both & (~m["base_C_correct"]) & m["ci_C_correct"]
    m["improve_D"] = a_clean_both & (~m["base_D_correct"]) & m["ci_D_correct"]

    # Also useful: CI all clean while base fails something.
    m["ci_AB_clean_base_B_fail"] = m["ci_A_correct"] & m["ci_B_correct"] & (~m["base_B_correct"])
    m["ci_AC_clean_base_C_fail"] = m["ci_A_correct"] & m["ci_C_correct"] & (~m["base_C_correct"])
    m["ci_AD_clean_base_D_fail"] = m["ci_A_correct"] & m["ci_D_correct"] & (~m["base_D_correct"])

    print("\n" + "=" * 72)
    print("BASE-FAIL / CI-SUCCESS COUNTS")
    print("=" * 72)
    print(f"Total scenarios: {len(m)}")
    print()
    print(f"Recipient improvement B: {int(m['improve_B'].sum())} / {len(m)}")
    print(f"Purpose improvement C:   {int(m['improve_C'].sum())} / {len(m)}")
    print(f"Full D improvement:      {int(m['improve_D'].sum())} / {len(m)}")
    print()
    print("Scenario IDs:")
    print("  improve_B:", m.loc[m["improve_B"], "scenario_id"].tolist())
    print("  improve_C:", m.loc[m["improve_C"], "scenario_id"].tolist())
    print("  improve_D:", m.loc[m["improve_D"], "scenario_id"].tolist())

    # Save readable improvement cases.
    Path(args.out_cases).parent.mkdir(parents=True, exist_ok=True)
    m.to_csv(args.out_cases, index=False)
    print(f"\nSaved improvement case table: {args.out_cases}")

    # Build compatibility eligibility file for run_patching.py.
    # Start with validation columns.
    elig = val.copy()
    elig["scenario_id"] = elig["scenario_id"].astype(int)
    elig = elig.merge(
        m[[
            "scenario_id",
            "improve_B",
            "improve_C",
            "improve_D",
            "base_A_correct", "base_B_correct", "base_C_correct", "base_D_correct",
            "ci_A_correct", "ci_B_correct", "ci_C_correct", "ci_D_correct",
            "base_A_margin", "base_B_margin", "base_C_margin", "base_D_margin",
            "ci_A_margin", "ci_B_margin", "ci_C_margin", "ci_D_margin",
        ]],
        on="scenario_id",
        how="left",
    )

    for col in ["improve_B", "improve_C", "improve_D"]:
        elig[col] = elig[col].fillna(False).astype(bool)

    # These column names match run_patching.py expectations.
    # For improvement patching, we deliberately replace "both clean" with
    # "base failed but CI succeeded" filters.
    elig["both_clean_AB"] = elig["improve_B"]
    elig["both_clean_AC"] = elig["improve_C"]
    elig["both_clean_AD"] = elig["improve_D"]

    elig["patch_final_AD"] = elig["improve_D"]

    elig["patch_recipient_AB_lasttok"] = elig["improve_B"]
    elig["patch_purpose_AC_lasttok"] = elig["improve_C"]

    elig["patch_recipient_AB_strictspan"] = elig["improve_B"] & elig["recipient_length_matched"].astype(bool)
    elig["patch_purpose_AC_strictspan"] = elig["improve_C"] & elig["purpose_length_matched"].astype(bool)
    elig["patch_both_AD_strictspan"] = elig["improve_D"] & elig["both_length_matched"].astype(bool)

    elig.to_csv(args.out_eligibility, index=False)
    print(f"Saved patching eligibility file: {args.out_eligibility}")

    print("\n" + "=" * 72)
    print("PATCHING ELIGIBILITY COUNTS")
    print("=" * 72)
    print(f"final_AB / recipient_last_AB: {int(elig['both_clean_AB'].sum())}")
    print(f"final_AC / purpose_last_AC:   {int(elig['both_clean_AC'].sum())}")
    print(f"final_AD / both_last_AD:      {int(elig['both_clean_AD'].sum())}")
    print()
    print(f"recipient strict-span:        {int(elig['patch_recipient_AB_strictspan'].sum())}")
    print(f"purpose strict-span:          {int(elig['patch_purpose_AC_strictspan'].sum())}")
    print(f"both strict-span:             {int(elig['patch_both_AD_strictspan'].sum())}")


if __name__ == "__main__":
    main()