from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# Run from anywhere; paths are resolved relative to the repository root.
ROOT = Path(__file__).resolve().parents[2]

LEVELS = [
    "seed",
    "vignette",
    "trajectory",
    "trajectory_enhancing",
]

BASE_TO_CI = "baseD_final_to_ciD_final_destructive"
CI_TO_BASE = "ciD_final_to_baseD_final_rescue"


# ================================================================
# PANEL A
# Same-prompt Base <-> CI final-state transfer across layers
# ================================================================

cross_path = (
    ROOT
    / "results"
    / "clean304"
    / "cross_model_transfer"
    / "DD_same_final_both_summary.csv"
)

cross = pd.read_csv(cross_path)

base_to_ci = cross[
    cross["experiment"] == BASE_TO_CI
].copy()

ci_to_base = cross[
    cross["experiment"] == CI_TO_BASE
].copy()

# Only valid matched block-output sites.
base_to_ci = (
    base_to_ci[base_to_ci["layer"] <= 26]
    .sort_values("layer")
)

ci_to_base = (
    ci_to_base[ci_to_base["layer"] <= 26]
    .sort_values("layer")
)

# Direction-specific behavioral success rates.
#
# Base-D -> CI-D:
# CI originally says No.
# Success = Base state changes CI No -> Yes.
base_to_ci["rate"] = (
    100.0 * base_to_ci["destroyed_no_rate"]
)

# CI-D -> Base-D:
# Base originally says Yes.
# Success = CI state changes Base Yes -> No.
ci_to_base["rate"] = (
    100.0 * ci_to_base["rescued_yes_rate"]
)


# ================================================================
# PANEL B
# Reconstruct Base L22 remove/rescue directly from per-level CSVs
# ================================================================

def aggregate_l22(mode):
    if mode == "remove":
        filename = "base_remove_summary.csv"
        alpha = 6.0
        flip_col = "no_to_yes_flips"
        n_col = "normal_no_count"
    elif mode == "rescue":
        filename = "base_rescue_summary.csv"
        alpha = 2.0
        flip_col = "yes_to_no_flips"
        n_col = "normal_yes_count"
    else:
        raise ValueError(mode)

    target_flips = 0
    target_n = 0
    random_flips = 0
    random_n = 0

    for level in LEVELS:
        path = (
            ROOT
            / "results"
            / "privacylens"
            / "base_l22_remove_rescue"
            / level
            / filename
        )

        df = pd.read_csv(path)

        target = df[
            (df["selection_name"] == "L22_top100")
            & (df["control_type"] == "ci_top_neurons")
            & (df["alpha"].astype(float) == alpha)
        ].iloc[0]

        random = df[
            (df["selection_name"] == "L22_random_top100_r0")
            & (df["control_type"] == "random_neurons")
            & (df["alpha"].astype(float) == alpha)
        ].iloc[0]

        target_flips += int(round(target[flip_col]))
        target_n += int(round(target[n_col]))

        random_flips += int(round(random[flip_col]))
        random_n += int(round(random[n_col]))

    return (
        target_flips,
        target_n,
        random_flips,
        random_n,
    )


# ================================================================
# Reconstruct Base L18 remove/rescue directly from per-level CSVs
# ================================================================

def aggregate_l18(mode):
    target_flips = 0
    target_n = 0
    random_flips = 0
    random_n = 0

    for level in LEVELS:
        path = (
            ROOT
            / "results"
            / "privacylens"
            / "base_l18_remove_rescue"
            / mode
            / level
            / "downstream_propagation_summary.csv"
        )

        df = pd.read_csv(path)

        target = df[
            (df["selection_name"] == "L18_top5_per_layer")
            & (df["control_type"] == "top_heads")
            & (df["layers"].astype(int) == 18)
            & (df["alpha"].astype(float) == 1.0)
        ].iloc[0]

        random = df[
            (df["selection_name"] == "L18_random5_per_layer_r0")
            & (df["control_type"] == "random_heads")
            & (df["layers"].astype(int) == 18)
            & (df["alpha"].astype(float) == 1.0)
        ].iloc[0]

        target_flips += int(round(target["success_flips"]))
        target_n += int(round(target["n"]))

        random_flips += int(round(random["success_flips"]))
        random_n += int(round(random["n"]))

    return (
        target_flips,
        target_n,
        random_flips,
        random_n,
    )


l22_remove = aggregate_l22("remove")
l22_rescue = aggregate_l22("rescue")
l18_remove = aggregate_l18("remove")
l18_rescue = aggregate_l18("rescue")

results = [
    l22_remove,
    l22_rescue,
    l18_remove,
    l18_rescue,
]

labels = [
    "L22 remove",
    "L22 rescue",
    "L18 remove",
    "L18 rescue",
]


def percentage(flips, n):
    return 100.0 * flips / n


target_rates = [
    percentage(x[0], x[1])
    for x in results
]

random_rates = [
    percentage(x[2], x[3])
    for x in results
]


# ================================================================
# MAKE FIGURE
# ================================================================

fig, axes = plt.subplots(
    1,
    2,
    figsize=(12.2, 4.35),
    gridspec_kw={
        "width_ratios": [1.18, 1.0],
    },
)


# ----------------------------------------------------------------
# PANEL A
# ----------------------------------------------------------------

ax = axes[0]

ax.axvspan(
    18,
    26,
    alpha=0.07,
    zorder=0,
)

ax.axvline(
    18,
    linestyle="--",
    linewidth=1.1,
    alpha=0.7,
)

ax.plot(
    ci_to_base["layer"],
    ci_to_base["rate"],
    marker="o",
    markevery=2,
    linewidth=2.2,
    markersize=4.2,
    label="CI-D → Base-D (Yes → No)",
)

ax.plot(
    base_to_ci["layer"],
    base_to_ci["rate"],
    marker="s",
    markevery=2,
    linewidth=2.2,
    markersize=4.2,
    label="Base-D → CI-D (No → Yes)",
)

ax.text(
    18.25,
    5,
    "L18",
    fontsize=9,
)

ax.text(
    22.8,
    8,
    "Late decision region",
    fontsize=9,
    ha="center",
)

ax.set_title(
    "(a) Cross-checkpoint state transfer becomes effective around L18",
    fontsize=11,
)

ax.set_xlabel("Layer")

ax.set_ylabel(
    "Directional decision-change rate (%)"
)

ax.set_xlim(-0.3, 26.3)
ax.set_ylim(-2, 103)

ax.set_xticks(
    [0, 5, 10, 15, 18, 20, 22, 24, 26]
)

ax.set_yticks(
    [0, 20, 40, 60, 80, 100]
)

ax.grid(alpha=0.18)

ax.legend(
    frameon=False,
    loc="upper left",
    fontsize=8.4,
)


# L26 counts are calculated from the CSV.
b26 = base_to_ci[
    base_to_ci["layer"] == 26
].iloc[0]

c26 = ci_to_base[
    ci_to_base["layer"] == 26
].iloc[0]

base_to_ci_count = int(
    round(
        b26["destroyed_no_rate"]
        * b26["n"]
    )
)

ci_to_base_count = int(
    round(
        c26["rescued_yes_rate"]
        * c26["n"]
    )
)

ax.text(
    23.2,
    93.2,
    f"{ci_to_base_count}/{int(c26['n'])}",
    fontsize=8.5,
)

ax.text(
    23.2,
    99.2,
    f"{base_to_ci_count}/{int(b26['n'])}",
    fontsize=8.5,
)


# ----------------------------------------------------------------
# PANEL B
# ----------------------------------------------------------------

ax2 = axes[1]

y = np.arange(len(labels))
height = 0.34

target_bars = ax2.barh(
    y - height / 2,
    target_rates,
    height=height,
    label="Targeted",
)

ax2.barh(
    y + height / 2,
    random_rates,
    height=height,
    label="Matched random",
)

ax2.set_yticks(y)
ax2.set_yticklabels(labels)

ax2.invert_yaxis()

ax2.set_xlim(0, 108)

ax2.set_xlabel(
    "Decision-change rate (%)"
)

ax2.set_title(
    "(b) CI-localized machinery is already active in Base",
    fontsize=11,
)

ax2.set_xticks(
    [0, 20, 40, 60, 80, 100]
)

ax2.grid(
    axis="x",
    alpha=0.18,
)

ax2.legend(
    frameon=False,
    loc="lower right",
    fontsize=8.8,
)


# Exact targeted counts.
for bar, result in zip(
    target_bars,
    results,
):
    flips, n, _, _ = result

    ax2.text(
        min(
            bar.get_width() + 1.0,
            101.5,
        ),
        bar.get_y()
        + bar.get_height() / 2,
        f"{flips}/{n}",
        va="center",
        fontsize=8.6,
        fontweight="bold",
    )


# Exact random-control counts.
random_text = (
    f"Random: "
    f"L22 remove {l22_remove[2]}/{l22_remove[3]}, "
    f"L22 rescue {l22_rescue[2]}/{l22_rescue[3]}, "
    f"L18 remove {l18_remove[2]}/{l18_remove[3]}, "
    f"L18 rescue {l18_rescue[2]}/{l18_rescue[3]}"
)

ax2.text(
    0.02,
    -0.17,
    random_text,
    transform=ax2.transAxes,
    fontsize=7.7,
    ha="left",
    va="top",
)


# ================================================================
# OVERALL TITLE + SAVE
# ================================================================

fig.suptitle(
    "CI post-training changes how a largely shared privacy-decision pathway is used",
    fontsize=13.3,
    y=1.02,
)

fig.tight_layout()

out = (
    ROOT
    / "figures"
    / "summary"
    / "executive_summary_mechanism"
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

plt.close(fig)


print()
print("Saved:")
print(out.with_suffix(".pdf"))
print(out.with_suffix(".png"))

print()
print("Values reconstructed from CSVs:")

for label, result in zip(
    labels,
    results,
):
    tf, tn, rf, rn = result

    print(
        f"{label}: "
        f"targeted {tf}/{tn} "
        f"({percentage(tf, tn):.2f}%), "
        f"random {rf}/{rn} "
        f"({percentage(rf, rn):.2f}%)"
    )