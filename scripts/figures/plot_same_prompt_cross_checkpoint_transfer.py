from pathlib import Path
import argparse

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


BASE_TO_CI = "baseD_final_to_ciD_final_destructive"
CI_TO_BASE = "ciD_final_to_baseD_final_rescue"


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--csv",
        default=ROOT / "results" / "clean304" / "cross_model_transfer" / "DD_same_final_both_summary.csv",
        type=Path,
        help="Input same-prompt cross-checkpoint summary CSV",
    )

    parser.add_argument(
        "--out",
        default=ROOT / "figures" / "clean304" / "same_prompt_cross_checkpoint_transfer",
        type=Path,
        help="Output path without extension",
    )

    args = parser.parse_args()

    df = pd.read_csv(args.csv)

    required = {
        "experiment",
        "pair",
        "layer",
        "n",
        "flip_rate",
        "destroyed_no_rate",
        "rescued_yes_rate",
        "patched_yes_rate",
        "patched_no_rate",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    # ------------------------------------------------------------
    # Select the two same-prompt D -> D transfer directions
    # ------------------------------------------------------------

    base_to_ci = df[
        df["experiment"] == BASE_TO_CI
    ].copy()

    ci_to_base = df[
        df["experiment"] == CI_TO_BASE
    ].copy()

    if base_to_ci.empty:
        raise ValueError(
            f"No rows found for {BASE_TO_CI}"
        )

    if ci_to_base.empty:
        raise ValueError(
            f"No rows found for {CI_TO_BASE}"
        )

    # IMPORTANT:
    # Exclude L27. Report only valid matched block-output sites L0--L26.
    base_to_ci = base_to_ci[
        base_to_ci["layer"] <= 26
    ].copy()

    ci_to_base = ci_to_base[
        ci_to_base["layer"] <= 26
    ].copy()

    base_to_ci = base_to_ci.sort_values("layer")
    ci_to_base = ci_to_base.sort_values("layer")

    # Direction-specific rates are cleaner than generic flip rate:
    #
    # Base D -> CI D:
    #   CI normally says No.
    #   Success means the Base state destroys that No and makes it Yes.
    #
    # CI D -> Base D:
    #   Base normally says Yes.
    #   Success means the CI state rescues it to No.

    base_to_ci["directional_rate"] = (
        100 * base_to_ci["destroyed_no_rate"]
    )

    ci_to_base["directional_rate"] = (
        100 * ci_to_base["rescued_yes_rate"]
    )

    # ------------------------------------------------------------
    # Extract L26 values for summary panel
    # ------------------------------------------------------------

    b2c_l26 = base_to_ci[
        base_to_ci["layer"] == 26
    ]

    c2b_l26 = ci_to_base[
        ci_to_base["layer"] == 26
    ]

    if b2c_l26.empty or c2b_l26.empty:
        raise ValueError(
            "L26 is missing from one of the two transfer directions."
        )

    b2c_l26 = b2c_l26.iloc[0]
    c2b_l26 = c2b_l26.iloc[0]

    n_b2c = int(b2c_l26["n"])
    n_c2b = int(c2b_l26["n"])

    b2c_rate = float(
        100 * b2c_l26["destroyed_no_rate"]
    )

    c2b_rate = float(
        100 * c2b_l26["rescued_yes_rate"]
    )

    b2c_count = int(
        round(
            b2c_l26["destroyed_no_rate"]
            * n_b2c
        )
    )

    c2b_count = int(
        round(
            c2b_l26["rescued_yes_rate"]
            * n_c2b
        )
    )

    # ------------------------------------------------------------
    # Figure
    # ------------------------------------------------------------

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(11.4, 4.6),
        gridspec_kw={
            "width_ratios": [2.15, 1.0],
        },
    )

    ax = axes[0]

    # Lightly mark the late region implicated by the
    # within-model patching results.
    ax.axvspan(
        18,
        26,
        alpha=0.07,
        zorder=0,
    )

    # L18 transition marker
    ax.axvline(
        18,
        linestyle="--",
        linewidth=1.1,
        alpha=0.7,
        zorder=1,
    )

    # CI-D -> Base-D rescue
    ax.plot(
        ci_to_base["layer"],
        ci_to_base["directional_rate"],
        marker="o",
        markevery=2,
        linewidth=2.3,
        markersize=4.5,
        label="CI-D → Base-D  (Yes → No)",
        zorder=3,
    )

    # Base-D -> CI-D destruction
    ax.plot(
        base_to_ci["layer"],
        base_to_ci["directional_rate"],
        marker="s",
        markevery=2,
        linewidth=2.3,
        markersize=4.5,
        label="Base-D → CI-D  (No → Yes)",
        zorder=3,
    )

    # Mark L26 endpoints
    ax.scatter(
        [26],
        [c2b_rate],
        s=45,
        zorder=4,
    )

    ax.scatter(
        [26],
        [b2c_rate],
        s=45,
        zorder=4,
    )

    # Annotate the transition around L18
    ax.text(
        18.25,
        4,
        "L18",
        fontsize=9,
        ha="left",
        va="bottom",
    )

    # Region label
    ax.text(
        22,
        7,
        "Late decision region",
        fontsize=9,
        ha="center",
        va="bottom",
    )

    ax.set_title(
        "(a) Same-prompt transfer across depth",
        fontsize=11.5,
        pad=9,
    )

    ax.set_xlabel(
        "Layer",
        fontsize=10.5,
    )

    ax.set_ylabel(
        "Directional decision-change rate (%)",
        fontsize=10.5,
    )

    ax.set_xlim(
        -0.3,
        26.3,
    )

    ax.set_ylim(
        -2,
        103,
    )

    ax.set_xticks(
        [0, 5, 10, 15, 18, 20, 22, 24, 26]
    )

    ax.set_yticks(
        [0, 20, 40, 60, 80, 100]
    )

    ax.grid(
        alpha=0.18,
    )

    ax.legend(
        frameon=False,
        loc="upper left",
        fontsize=8.8,
    )

    # ------------------------------------------------------------
    # Panel B: L26 summary
    # ------------------------------------------------------------

    ax2 = axes[1]

    labels = [
        "CI-D →\nBase-D",
        "Base-D →\nCI-D",
    ]

    values = [
        c2b_rate,
        b2c_rate,
    ]

    bars = ax2.bar(
        labels,
        values,
        width=0.58,
    )

    ax2.set_title(
        "(b) Transfer at L26",
        fontsize=11.5,
        pad=9,
    )

    ax2.set_ylabel(
        "Decision-change rate (%)",
        fontsize=10.5,
    )

    ax2.set_ylim(
        0,
        106,
    )

    ax2.set_yticks(
        [0, 20, 40, 60, 80, 100]
    )

    ax2.grid(
        axis="y",
        alpha=0.18,
    )

    # Exact counts above bars
    counts = [
        (c2b_count, n_c2b, "to No"),
        (b2c_count, n_b2c, "to Yes"),
    ]

    for bar, (count, n, outcome), rate in zip(
        bars,
        counts,
        values,
    ):
        x = (
            bar.get_x()
            + bar.get_width() / 2
        )

        ax2.text(
            x,
            rate + 1.5,
            f"{count}/{n}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

        ax2.text(
            x,
            rate - 7,
            outcome,
            ha="center",
            va="top",
            fontsize=9,
        )

    # ------------------------------------------------------------
    # Overall title
    # ------------------------------------------------------------

    fig.suptitle(
        "Same-prompt cross-model state transfer becomes effective in late layers",
        fontsize=13.5,
        y=1.02,
    )

    fig.tight_layout()

    # ------------------------------------------------------------
    # Save
    # ------------------------------------------------------------

    out = args.out

    out.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fig.savefig(
        out.with_suffix(".pdf"),
        bbox_inches="tight",
    )

    fig.savefig(
        out.with_suffix(".png"),
        dpi=300,
        bbox_inches="tight",
    )

    print(
        f"Saved {out.with_suffix('.pdf')}"
    )

    print(
        f"Saved {out.with_suffix('.png')}"
    )

    print()
    print("L26 summary:")
    print(
        f"CI-D -> Base-D: "
        f"{c2b_count}/{n_c2b} rescued to No "
        f"({c2b_rate:.1f}%)"
    )

    print(
        f"Base-D -> CI-D: "
        f"{b2c_count}/{n_b2c} changed to Yes "
        f"({b2c_rate:.1f}%)"
    )


if __name__ == "__main__":
    main()