from pathlib import Path
import argparse

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


BASE_NAME = "Qwen2.5-7B-Instruct"
CI_NAME = "Qwen2.5-7B-Instruct-CI"

EXPERIMENTS = {
    "Recipient A→B": (
        "recipient",
        "recipient_last_AB_A_to_B",
    ),
    "Purpose A→C": (
        "purpose",
        "purpose_last_AC_A_to_C",
    ),
    "Final A→D": (
        "final",
        "final_AD_A_to_D",
    ),
}


def load_experiment(path, experiment):
    df = pd.read_csv(path)

    required = {
        "model_short",
        "experiment",
        "layer",
        "mean_aligned_effect",
        "flip_rate",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required columns: {sorted(missing)}"
        )

    df = df[df["experiment"] == experiment].copy()

    # Exclude L27 patching because the cached and patched
    # activations do not correspond to the same residual-stream site.
    df = df[df["layer"] <= 26].copy()

    if df.empty:
        raise ValueError(
            f"Could not find experiment {experiment!r} in {path}"
        )

    return df


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--recipient",
        default=ROOT / "results" / "clean304" / "within_model_patching" / "recipient_AB_summary.csv",
        type=Path,
        help="Recipient-patching summary CSV",
    )

    parser.add_argument(
        "--purpose",
        default=ROOT / "results" / "clean304" / "within_model_patching" / "purpose_AC_summary.csv",
        type=Path,
        help="Purpose-patching summary CSV",
    )

    parser.add_argument(
        "--final",
        default=ROOT / "results" / "clean304" / "within_model_patching" / "final_AD_summary.csv",
        type=Path,
        help="Final-position A-to-D patching summary CSV",
    )

    parser.add_argument(
        "--out",
        default=ROOT / "figures" / "clean304" / "within_model_patching_flow",
        type=Path,
        help="Output path without extension",
    )

    args = parser.parse_args()

    paths = {
        "recipient": args.recipient,
        "purpose": args.purpose,
        "final": args.final,
    }

    data = {}

    for label, (file_key, experiment) in EXPERIMENTS.items():
        data[label] = load_experiment(
            paths[file_key],
            experiment,
        )

    # Wider figure so the important L18-L26 region is easier to inspect.
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(12.4, 4.7),
        sharex=True,
        sharey=True,
    )

    model_panels = [
        ("Base", BASE_NAME),
        ("CI", CI_NAME),
    ]

    markers = {
        "Recipient A→B": "o",
        "Purpose A→C": "s",
        "Final A→D": "^",
    }

    # Regions highlighted in the figure.
    semantic_start = 0
    semantic_end = 11

    integration_start = 18
    integration_end = 26

    for ax, (panel_name, model_name) in zip(
        axes,
        model_panels,
    ):

        # Region where recipient/purpose information has
        # substantial influence at its semantic positions.
        ax.axvspan(
            semantic_start,
            semantic_end,
            alpha=0.10,
            color="gray",
            zorder=0,
        )

        # Region where final-token integration becomes strong.
        ax.axvspan(
            integration_start,
            integration_end,
            alpha=0.08,
            color="green",
            zorder=0,
        )

        for label in EXPERIMENTS:

            sub = data[label]
            sub = sub[
                sub["model_short"] == model_name
            ].copy()

            sub = sub.sort_values("layer")

            if sub.empty:
                raise ValueError(
                    f"No rows found for model {model_name} "
                    f"in experiment {label}"
                )

            ax.plot(
                sub["layer"],
                sub["mean_aligned_effect"],
                marker=markers[label],
                markevery=2,
                linewidth=2,
                markersize=4,
                label=label,
                zorder=3,
            )

        # Mark the sharp final-token transition.
        ax.axvline(
            18,
            linestyle=":",
            linewidth=1.5,
            color="black",
            zorder=2,
        )

        # Early contextual-information annotation.
        ax.text(
            5.5,
            14.7,
            "Semantic-position\ninfluence strongest",
            ha="center",
            va="top",
            fontsize=8.5,
        )

        # Final-token transition annotation.
        transition_y = (
            5.8 if panel_name == "Base" else 7.0
        )

        ax.annotate(
            "Final-token integration\nbecomes strong",
            xy=(18, transition_y),
            xytext=(19.0, 14.7),
            textcoords="data",
            ha="left",
            va="top",
            fontsize=8.5,
            arrowprops=dict(
                arrowstyle="->",
                lw=1.0,
            ),
        )

        ax.set_title(
            panel_name,
            fontsize=12.5,
        )

        ax.set_xlabel(
            "Layer",
            fontsize=11,
        )

        ax.set_xlim(
            0,
            26,
        )

        # Cleaner spacing in the important late region.
        ax.set_xticks(
            [
                0,
                5,
                10,
                15,
                18,
                20,
                22,
                24,
                26,
            ]
        )

        ax.grid(
            alpha=0.2,
        )

    axes[0].set_ylabel(
        "Mean aligned Yes–No margin effect",
        fontsize=11,
    )

    axes[0].set_ylim(
        -0.8,
        15.1,
    )

    # Shared legend.
    handles, labels = (
        axes[0].get_legend_handles_labels()
    )

    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 1.03),
        fontsize=11,
    )

    fig.suptitle(
        "Contextual influence moves from semantic positions "
        "to the final decision state",
        y=1.11,
        fontsize=14,
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

    print(
        f"Saved {out.with_suffix('.pdf')}"
    )

    print(
        f"Saved {out.with_suffix('.png')}"
    )


if __name__ == "__main__":
    main()