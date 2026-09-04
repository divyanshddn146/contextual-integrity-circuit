import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "results" / "clean304" / "component_direction_ablation" / "component_ablation_summary.csv",
        help="Input component-ablation summary CSV",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "figures" / "clean304" / "component_localization",
        help="Output path without extension",
    )
    args = parser.parse_args()

    csv_path = args.csv
    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)

    required = {
        "component",
        "layer",
        "mode",
        "alpha",
        "control_type",
        "n",
        "no_to_yes_flips",
        "no_to_yes_flip_rate",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    # Main Figure 4:
    # real D-minus-A direction, alpha=1, valid block-output layers L0-L26.
    plot_df = df[
        (df["control_type"] == "real_direction")
        & (df["mode"] == "remove_positive")
        & (df["alpha"] == 1.0)
        & (df["layer"] <= 26)
    ].copy()

    component_names = {
        "attn": "Attention",
        "mlp": "MLP",
        "resid_post": "Residual",
    }

    component_order = ["resid_post", "attn", "mlp"]
    markers = {
        "resid_post": "o",
        "attn": "s",
        "mlp": "^",
    }

    # Verify that we are plotting the actual expected result file.
    expected = {
        ("resid_post", 17): 19,
        ("resid_post", 18): 95,
        ("attn", 17): 3,
        ("attn", 18): 93,
        ("attn", 19): 7,
        ("mlp", 18): 72,
        ("mlp", 19): 87,
        ("mlp", 20): 94,
        ("mlp", 21): 94,
        ("mlp", 22): 91,
    }

    for (component, layer), expected_flips in expected.items():
        rows = plot_df[
            (plot_df["component"] == component)
            & (plot_df["layer"] == layer)
        ]

        if len(rows) != 1:
            raise ValueError(
                f"Expected one row for {component} L{layer}, found {len(rows)}"
            )

        actual = int(rows.iloc[0]["no_to_yes_flips"])
        if actual != expected_flips:
            raise ValueError(
                f"Unexpected result for {component} L{layer}: "
                f"expected {expected_flips}, found {actual}"
            )

    print("Verified key Figure 4 values against CSV.")

    # Paper-friendly sizing.
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.labelsize": 11,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig, ax = plt.subplots(figsize=(7.2, 4.1))

    for component in component_order:
        sub = (
            plot_df[plot_df["component"] == component]
            .sort_values("layer")
        )

        ax.plot(
            sub["layer"],
            sub["no_to_yes_flips"],
            marker=markers[component],
            markersize=4.2,
            linewidth=2.0,
            label=component_names[component],
        )

    # Mark the layer where all previous analyses show the sharp transition.
    ax.axvline(
        18,
        linestyle="--",
        linewidth=1.2,
        alpha=0.7,
    )

    ax.text(
        18.25,
        7,
        "L18",
        fontsize=9,
        rotation=90,
        va="bottom",
    )

    # Emphasize the key attention result without filling the plot with labels.
    ax.annotate(
        "Attention: 93/95",
        xy=(18, 93),
        xytext=(12.5, 78),
        arrowprops={"arrowstyle": "->", "linewidth": 0.9},
        fontsize=9,
    )

    # Highlight the broader downstream MLP region.
    ax.annotate(
        "Broad MLP effect",
        xy=(21, 94),
        xytext=(22.5, 77),
        arrowprops={"arrowstyle": "->", "linewidth": 0.9},
        fontsize=9,
    )

    ax.set_xlabel("Layer")
    ax.set_ylabel("No-to-Yes decisions changed (out of 95)")

    ax.set_xlim(-0.5, 26.5)
    ax.set_ylim(-2, 100)

    ax.set_xticks([0, 4, 8, 12, 16, 18, 20, 22, 24, 26])
    ax.set_yticks([0, 20, 40, 60, 80, 95])

    ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.45,
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend(
        frameon=False,
        loc="upper left",
    )

    fig.tight_layout()

    fig.savefig(
        str(out_path) + ".pdf",
        bbox_inches="tight",
    )
    fig.savefig(
        str(out_path) + ".png",
        dpi=300,
        bbox_inches="tight",
    )

    print(f"Saved: {out_path}.pdf")
    print(f"Saved: {out_path}.png")


if __name__ == "__main__":
    main()