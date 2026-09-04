#!/usr/bin/env python3
"""Reconstruct the 27 same-prompt Base-Yes / CI-No PrivacyLens correction cases.

This is a descriptive convenience export for the report's same-prompt analysis.
It does not run a new intervention. It joins already-saved Base and CI evaluation
outputs by prompt level and case_index, then writes the matched rows and the
summary statistics reported in Appendix N / Table 25.
"""

from pathlib import Path
import json
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
LEVELS = ["seed", "vignette", "trajectory", "trajectory_enhancing"]

BASE_TEMPLATE = (
    ROOT
    / "results/privacylens/base_l18_remove_rescue/remove/{level}/"
    "normal_privacylens_scores_with_mlp_act.csv"
)
CI_TEMPLATE = (
    ROOT
    / "results/privacylens/ci_l18_to_l22_propagation/{level}/"
    "normal_privacylens_scores_with_mlp_act.csv"
)
RAW_PRIVACYLENS = ROOT / "data/raw/PrivacyLens/data/main_data.json"

OUT_ROWS = ROOT / "results/privacylens/same_prompt_correction_analysis.csv"
OUT_SUMMARY = ROOT / "tables/privacylens/same_prompt_correction_summary.csv"


def load_source_metadata():
    with RAW_PRIVACYLENS.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw


def main():
    raw = load_source_metadata()
    rows = []

    for level in LEVELS:
        base_path = Path(str(BASE_TEMPLATE).format(level=level))
        ci_path = Path(str(CI_TEMPLATE).format(level=level))

        base = pd.read_csv(base_path)
        ci = pd.read_csv(ci_path)
        paired = base.merge(
            ci,
            on="case_index",
            suffixes=("_base", "_ci"),
            validate="one_to_one",
        )

        if not (paired["prompt_excerpt_base"] == paired["prompt_excerpt_ci"]).all():
            raise ValueError(f"Prompt mismatch between Base and CI for level={level}")

        corrected = paired[
            (paired["normal_decision_base"] == "Yes")
            & (paired["normal_decision_ci"] == "No")
        ].copy()

        for _, r in corrected.iterrows():
            idx = int(r["case_index"])
            rows.append(
                {
                    "level": level,
                    "case_index": idx,
                    "case_name": raw[idx]["name"],
                    "source": raw[idx]["seed"]["source"],
                    "base_decision": r["normal_decision_base"],
                    "ci_decision": r["normal_decision_ci"],
                    "base_margin": r["normal_margin_base"],
                    "ci_margin": r["normal_margin_ci"],
                    "ci_minus_base_margin": (
                        r["normal_margin_ci"] - r["normal_margin_base"]
                    ),
                    "base_n13149_activation": r["normal_mlp_act_base"],
                    "ci_n13149_activation": r["normal_mlp_act_ci"],
                    "ci_minus_base_n13149_activation": (
                        r["normal_mlp_act_ci"] - r["normal_mlp_act_base"]
                    ),
                    "prompt_excerpt": r["prompt_excerpt_base"],
                }
            )

    out = pd.DataFrame(rows)
    if len(out) != 27:
        raise ValueError(f"Expected 27 correction cases, found {len(out)}")

    OUT_ROWS.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_ROWS, index=False)

    summary = pd.DataFrame(
        [
            {"quantity": "n_correction_cases", "value": len(out)},
            {"quantity": "seed_cases", "value": int((out["level"] == "seed").sum())},
            {"quantity": "vignette_cases", "value": int((out["level"] == "vignette").sum())},
            {"quantity": "trajectory_cases", "value": int((out["level"] == "trajectory").sum())},
            {
                "quantity": "trajectory_enhancing_cases",
                "value": int((out["level"] == "trajectory_enhancing").sum()),
            },
            {"quantity": "literature_cases", "value": int((out["source"] == "literature").sum())},
            {"quantity": "crowdsourcing_cases", "value": int((out["source"] == "crowdsourcing").sum())},
            {"quantity": "regulation_cases", "value": int((out["source"] == "regulation").sum())},
            {"quantity": "mean_base_margin", "value": out["base_margin"].mean()},
            {"quantity": "mean_ci_margin", "value": out["ci_margin"].mean()},
            {
                "quantity": "mean_ci_minus_base_margin",
                "value": out["ci_minus_base_margin"].mean(),
            },
            {
                "quantity": "mean_ci_minus_base_n13149_activation",
                "value": out["ci_minus_base_n13149_activation"].mean(),
            },
        ]
    )
    summary.to_csv(OUT_SUMMARY, index=False)

    print(f"Wrote {len(out)} matched correction cases to {OUT_ROWS.relative_to(ROOT)}")
    print(f"Wrote summary to {OUT_SUMMARY.relative_to(ROOT)}")
    print("\nReport values:")
    print(f"  Base margin: {out['base_margin'].mean():+.3f}")
    print(f"  CI margin: {out['ci_margin'].mean():+.3f}")
    print(f"  CI - Base margin: {out['ci_minus_base_margin'].mean():+.3f}")
    print(
        "  CI - Base N13149 activation: "
        f"{out['ci_minus_base_n13149_activation'].mean():+.3f}"
    )


if __name__ == "__main__":
    main()
