import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot PrivacyLens L22 top-100 dose response from result CSVs."
    )

    parser.add_argument(
        "--seed",
        default=ROOT / "results" / "privacylens" / "ci_l22_writer_transfer" / "seed" / "direction_ablation_summary.csv",
        type=Path,
        help="Seed-level direction-ablation summary CSV",
    )
    parser.add_argument(
        "--vignette",
        default=ROOT / "results" / "privacylens" / "ci_l22_writer_transfer" / "vignette" / "direction_ablation_summary.csv",
        type=Path,
        help="Vignette-level direction-ablation summary CSV",
    )
    parser.add_argument(
        "--trajectory",
        default=ROOT / "results" / "privacylens" / "ci_l22_writer_transfer" / "trajectory" / "direction_ablation_summary.csv",
        type=Path,
        help="Trajectory-level direction-ablation summary CSV",
    )
    parser.add_argument(
        "--trajectory-enhancing",
        default=ROOT / "results" / "privacylens" / "ci_l22_writer_transfer" / "trajectory_enhancing" / "direction_ablation_summary.csv",
        type=Path,
        dest="trajectory_enhancing",
        help="Trajectory-enhancing direction-ablation summary CSV",
    )
    parser.add_argument(
        "--output",
        default=ROOT / "figures" / "privacylens" / "ci_l22_writer_dose_response.pdf",
        type=Path,
        help="Output PDF filename",
    )

    return parser.parse_args()


def load_csv(path, expected_level):
    df = pd.read_csv(path)

    required_columns = {
        "level",
        "control_type",
        "layer",
        "k",
        "alpha",
        "n",
        "delta_toward_yes_mean",
        "no_to_yes_flips",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"{path} is missing required columns: {sorted(missing)}"
        )

    levels = df["level"].dropna().unique()

    print(f"\nLoaded: {path}")
    print(f"Rows: {len(df)}")
    print(f"Level values: {levels}")

    if len(levels) != 1:
        raise ValueError(
            f"Expected one PrivacyLens level in {path}, found {levels}"
        )

    if levels[0] != expected_level:
        raise ValueError(
            f"Expected level '{expected_level}' in {path}, "
            f"but CSV contains '{levels[0]}'"
        )

    return df


def aggregate(df):
    rows = []

    for alpha, group in df.groupby("alpha"):
        total_n = int(group["n"].sum())
        total_flips = int(group["no_to_yes_flips"].sum())

        weighted_margin_shift = (
            group["delta_toward_yes_mean"] * group["n"]
        ).sum() / total_n

        rows.append(
            {
                "alpha": float(alpha),
                "n": total_n,
                "flips": total_flips,
                "flip_rate": total_flips / total_n,
                "mean_margin_shift": weighted_margin_shift,
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values("alpha")
        .reset_index(drop=True)
    )


def main():
    args = parse_args()

    dfs = [
        load_csv(args.seed, "seed"),
        load_csv(args.vignette, "vignette"),
        load_csv(args.trajectory, "trajectory"),
        load_csv(args.trajectory_enhancing, "trajectory_enhancing"),
    ]

    results = pd.concat(dfs, ignore_index=True)

    # --------------------------------------------------------
    # Fixed CLEAN304-derived L22 top-100 targeted intervention
    # --------------------------------------------------------

    target = results[
        (results["control_type"] == "ci_top_neurons")
        & (results["layer"] == 22)
        & (results["k"] == 100)
    ].copy()

    # --------------------------------------------------------
    # Matched random-neuron control
    # --------------------------------------------------------

    random = results[
        (results["control_type"] == "random_neurons")
        & (results["layer"] == 22)
        & (results["k"] == 100)
    ].copy()

    if target.empty:
        raise ValueError("No L22 top-100 ci_top_neurons rows found.")

    if random.empty:
        raise ValueError("No L22 top-100 random_neurons rows found.")

    target_summary = aggregate(target)
    random_summary = aggregate(random)

    print("\n==========================================")
    print("TARGETED L22 TOP-100")
    print("==========================================")
    print(target_summary.to_string(index=False))

    print("\n==========================================")
    print("MATCHED RANDOM")
    print("==========================================")
    print(random_summary.to_string(index=False))

    # --------------------------------------------------------
    # Verify expected structure
    # --------------------------------------------------------

    expected_alphas = [1.0, 2.0, 4.0, 6.0]

    if target_summary["alpha"].tolist() != expected_alphas:
        raise ValueError(
            f"Unexpected targeted alphas: "
            f"{target_summary['alpha'].tolist()}"
        )

    if random_summary["alpha"].tolist() != expected_alphas:
        raise ValueError(
            f"Unexpected random alphas: "
            f"{random_summary['alpha'].tolist()}"
        )

    # These checks make sure you are plotting the run we inspected.
    expected_target_flips = [6, 17, 836, 1937]

    if target_summary["flips"].tolist() != expected_target_flips:
        raise ValueError(
            "Targeted flip counts do not match the verified run.\n"
            f"Found: {target_summary['flips'].tolist()}\n"
            f"Expected: {expected_target_flips}"
        )

    if random_summary["flips"].tolist() != [0, 0, 0, 0]:
        raise ValueError(
            "Random-neuron control unexpectedly contains flips: "
            f"{random_summary['flips'].tolist()}"
        )

    # --------------------------------------------------------
    # Plot
    # --------------------------------------------------------

    alphas = target_summary["alpha"].to_numpy()

    target_rates = (
        100.0 * target_summary["flip_rate"].to_numpy()
    )

    random_rates = (
        100.0 * random_summary["flip_rate"].to_numpy()
    )

    fig, ax = plt.subplots(figsize=(6.4, 4.2))

    ax.plot(
        alphas,
        target_rates,
        marker="o",
        linewidth=2.2,
        markersize=7,
        label="L22 top-100",
    )

    ax.plot(
        alphas,
        random_rates,
        marker="s",
        linestyle="--",
        linewidth=1.8,
        markersize=6,
        label="Matched random",
    )

    # --------------------------------------------------------
    # Exact counts above targeted points
    # --------------------------------------------------------

    for _, row in target_summary.iterrows():
        alpha = row["alpha"]
        rate = 100.0 * row["flip_rate"]
        flips = int(row["flips"])
        n = int(row["n"])

        if alpha == 6:
            xytext = (0, -17)
            va = "top"
        else:
            xytext = (0, 8)
            va = "bottom"

        ax.annotate(
            f"{flips}/{n}",
            xy=(alpha, rate),
            xytext=xytext,
            textcoords="offset points",
            ha="center",
            va=va,
            fontsize=9,
        )

    # --------------------------------------------------------
    # Formatting
    # --------------------------------------------------------

    ax.set_xlabel(
        r"Intervention strength $\alpha$",
        fontsize=11,
    )

    ax.set_ylabel(
        "No-to-Yes decision changes (%)",
        fontsize=11,
    )

    ax.set_xticks(alphas)

    ax.set_xlim(0.7, 6.3)
    ax.set_ylim(-3, 105)

    ax.set_yticks([0, 20, 40, 60, 80, 100])

    ax.grid(
        axis="y",
        linestyle=":",
        linewidth=0.7,
        alpha=0.5,
    )

    ax.legend(
        frameon=False,
        loc="upper left",
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    args.output.parent.mkdir(parents=True, exist_ok=True)

    fig.savefig(
        args.output,
        bbox_inches="tight",
    )

    png_output = args.output.with_suffix(".png")

    fig.savefig(
        png_output,
        dpi=300,
        bbox_inches="tight",
    )

    print(f"\nSaved PDF: {args.output}")
    print(f"Saved PNG: {png_output}")

    plt.show()


if __name__ == "__main__":
    main()