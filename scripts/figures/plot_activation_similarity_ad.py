from pathlib import Path
import argparse

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--csv",
        default=ROOT / "results" / "clean304" / "activation_similarity" / "ABC_contrast_summary.csv",
        type=Path,
        help="Input contrast-summary CSV",
    )

    parser.add_argument(
        "--out",
        default=ROOT / "figures" / "clean304" / "activation_similarity_ad",
        type=Path,
        help="Output path without extension",
    )

    args = parser.parse_args()

    df = pd.read_csv(args.csv)

    required = {
        "contrast",
        "site",
        "layer",
        "n",
        "mean_direction_cosine",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    # Final-position D-minus-A contrast
    sub = df[
        (df["contrast"] == "AD_D_minus_A")
        & (df["site"] == "final")
    ].copy()

    # Keep layers 0--26 for consistency with the main analysis
    sub = sub[sub["layer"] <= 26].copy()
    sub = sub.sort_values("layer")

    if sub.empty:
        raise ValueError(
            "No rows found for AD_D_minus_A at the final position."
        )

    x = sub["layer"].to_numpy()
    y = sub["mean_direction_cosine"].to_numpy()

    fig, ax = plt.subplots(
        figsize=(7.4, 4.5),
    )

    # Lightly highlight the late decision-relevant region
    ax.axvspan(
        18,
        26,
        alpha=0.08,
        zorder=0,
    )

    # Mean Base-CI direction cosine
    ax.plot(
        x,
        y,
        marker="o",
        markevery=2,
        linewidth=2.2,
        markersize=4.5,
        zorder=3,
    )

    # Perfect alignment reference
    ax.axhline(
        1.0,
        linestyle=":",
        linewidth=1.1,
        alpha=0.75,
        zorder=1,
    )

    # Mark L18, where final-token influence rises sharply
    ax.axvline(
        18,
        linestyle="--",
        linewidth=1.1,
        alpha=0.75,
        zorder=2,
    )

    # Annotate representative late-layer values
    annotation_layers = [18, 22, 26]

    for layer in annotation_layers:
        row = sub[sub["layer"] == layer]

        if row.empty:
            continue

        value = row.iloc[0]["mean_direction_cosine"]

        if layer == 18:
            offset = (-10, 13)
        elif layer == 22:
            offset = (-7, 13)
        else:
            offset = (-28, 12)

        ax.annotate(
            f"L{layer}: {value:.3f}",
            xy=(layer, value),
            xytext=offset,
            textcoords="offset points",
            fontsize=8.5,
            ha="center",
            arrowprops=dict(
                arrowstyle="-",
                lw=0.7,
                alpha=0.7,
            ),
        )

    # Label the highlighted region
    ax.text(
        22,
        0.9528,
        "Late decision region",
        ha="center",
        va="bottom",
        fontsize=9,
    )

    ax.set_title(
        "Base and CI preserve a highly aligned privacy contrast",
        fontsize=12.5,
        pad=10,
    )

    ax.set_xlabel(
        "Layer",
        fontsize=11,
    )

    ax.set_ylabel(
        "Base–CI cosine of D−A direction",
        fontsize=11,
    )

    ax.set_xlim(
        -0.3,
        26.3,
    )

    ax.set_ylim(
        0.95,
        1.002,
    )

    ax.set_xticks(
        [0, 5, 10, 15, 18, 20, 22, 24, 26]
    )

    ax.grid(
        alpha=0.18,
    )

    fig.tight_layout()

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

    print(f"Saved {out.with_suffix('.pdf')}")
    print(f"Saved {out.with_suffix('.png')}")


if __name__ == "__main__":
    main()