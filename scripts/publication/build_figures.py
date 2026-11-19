"""Render original SVG and PNG charts from the sanitized measurements."""

import argparse
import json
import os
from pathlib import Path
from shutil import copyfile

os.environ["MPLBACKEND"] = "Agg"
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
COLOR = {"A": "#4b627a", "B": "#00768b"}
INK = "#13273b"
MUTED = "#4d6070"
ORDER = ("A1", "A2", "B1", "B2")
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.edgecolor": "#ccd5e0",
        "svg.hashsalt": "inference-audit",
        "svg.fonttype": "none",
        "figure.facecolor": "#f8fafc",
        "axes.facecolor": "#f8fafc",
    }
)


def figure(title, subtitle, footnote, *, panels=1, height=4.3, left=0.13):
    fig, axes = plt.subplots(1, panels, figsize=(9.2, height), squeeze=False)
    fig.subplots_adjust(left=left, right=0.95, top=0.73, bottom=0.25, wspace=0.54)
    fig.text(0.055, 0.90, title, fontsize=19, fontweight="bold")
    fig.text(0.055, 0.81, subtitle, fontsize=10, color=MUTED)
    fig.text(0.055, 0.055, footnote, fontsize=9, color=MUTED, linespacing=1.45)
    for ax in axes[0]:
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(length=0, pad=7)
        ax.set_axisbelow(True)
    return fig, axes[0]


def export(fig, name, output, web):
    for extension in ("svg", "png"):
        file = output / f"{name}.{extension}"
        metadata = {"Date": None} if extension == "svg" else {}
        fig.savefig(file, dpi=136, metadata=metadata)
        if extension == "svg":
            source = file.read_text(encoding="utf-8")
            normalized = "\n".join(line.rstrip() for line in source.splitlines()) + "\n"
            file.write_text(normalized, encoding="utf-8", newline="\n")
            copyfile(file, web / file.name)
    plt.close(fig)


def chat(data, output, web):
    fig, (ax,) = figure(
        "Homogeneous chat bursts processed more tokens",
        "Qwen3-8B Q4_K_M  /  matched repeated bursts  /  f16 KV, 16,384 total positions",
        "Source P2-CHAT • Phase 2 request observations. Pooled tokens ÷ sum of launch spans.\n"
        "The four-slot profile halves per-slot context. This comparison is scoped to this burst trace.",
        left=0.28,
    )
    groups = data["phase2"]["comparisons"]
    values = [groups[f"Chat burst {name}"] for name in ("standard c2", "selected c4")]
    labels = [
        f"{slots} serving slots\n{d['offered']} requests, {len(d['launches'])} launches"
        for slots, d in zip((2, 4), values, strict=True)
    ]
    bars = ax.barh(labels, [g["tok_s"] for g in values], color=[COLOR["A"], COLOR["B"]], height=0.48)
    ax.bar_label(bars, fmt="%.2f", padding=8, color=INK)
    ax.invert_yaxis()
    ax.set(xlim=(0, 265), xlabel="Output tokens/s")
    ax.grid(axis="x", color="#e1e7ed")
    export(fig, "chat-burst-throughput", output, web)


def models(data, output, web):
    fig, (ax,) = figure(
        "The throughput gain varied across models",
        "Phase 3 highest mixed-load window for each model  /  four slots relative to its own two-slot control",
        "Source P3-MODELS • Medians of launch rates. Two four-slot launches per model; Qwen used two\n"
        "controls, Forge and Gemma used three. Request rates, context pools and engine builds varied by model.",
        left=0.33,
    )
    launch_data = data["transfer"]
    labels = [f"{m['model']}\n{m['launches'][0]['offered_rps']:.3g} offered txn/s" for m in launch_data]
    bars = ax.barh(labels, [m["delta_pct"] for m in launch_data], color=COLOR["B"], height=0.53)
    ax.bar_label(bars, fmt="+%.1f%%", padding=7, color=INK)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.set(xlim=(0, 24), xlabel="Change in output tokens/s")
    ax.grid(axis="x", color="#e1e7ed")
    export(fig, "transfer-throughput", output, web)


def replication(data, output, web):
    rows = data["phase4"]["rows"]
    high = {r["stage"]: r for r in rows if r["window"] == 3 and r["family"] == "all"}
    fig, axes = figure(
        "First tokens arrived sooner. Completions took longer.",
        "Qwen3-8B Q4_K_M  /  fresh mixed trace at 1.15 offered txn/s  /  345 offered per launch",
        "Source P4-TAIL • Each bar is one fresh server launch. P95 uses complete transactions.\n"
        "A1 and A2 used two slots. B1 and B2 used four. Actual launch order was A1, B1, B2, A2.",
        panels=2,
        height=4.4,
        left=0.10,
    )
    for ax, key, label in zip(
        axes, ("ttft_p95", "e2e_p95"), ("P95 first token (s)", "P95 completion (s)"), strict=True
    ):
        bars = ax.bar(ORDER, [high[s][key] for s in ORDER], color=[COLOR[s[0]] for s in ORDER], width=0.58)
        ax.bar_label(bars, fmt="%.2f", padding=4, fontsize=9)
        ax.set(ylim=(0, 5.4), xlabel=label, yticks=range(6))
        ax.grid(axis="y", color="#e1e7ed")
    export(fig, "replication-tail-latency", output, web)

    fig, (ax,) = figure(
        "More slots delivered less correct, on-time work",
        "Qwen3-8B Q4_K_M  /  fresh mixed trace  /  matched 300 s windows",
        "Source P4-GOODPUT • 240, 300 and 345 offered transactions per launch window.\n"
        "Thin lines show separate launches. The dashed reference represents all offered work delivered on time.",
        left=0.12,
    )
    offered = [0.8, 1, 1.15]
    ax.plot(offered, offered, color="#8191a2", linestyle="--", linewidth=1.2, label="All offered work")
    for stage in ORDER:
        arm = [r for r in rows if r["stage"] == stage and r["family"] == "all"]
        ax.plot(
            offered,
            [r["goodput_rps"] for r in arm],
            color=COLOR[stage[0]],
            linewidth=1.25,
            marker="o" if stage[0] == "A" else "s",
            markersize=4,
            label={"A1": "Two slots", "B1": "Four slots"}.get(stage),
        )
    ax.set(
        xlim=(0.75, 1.20),
        ylim=(0, 1.26),
        xticks=offered,
        xlabel="Offered transactions/s",
        ylabel="Correct, on-time txn/s",
    )
    ax.legend(loc="lower right", ncol=1, frameon=False, fontsize=9)
    ax.grid(axis="y", color="#e1e7ed")
    export(fig, "replication-goodput", output, web)

    agg = {(r["stage"], r["family"]): r for r in rows if r["window"] == 3}
    fig, (ax,) = figure(
        "Aggregate throughput hid failures in chat and agents",
        "Qwen3-8B Q4_K_M  /  1.15 offered mixed txn/s  /  two launches per serving profile",
        "Source P4-FAMILY • Share of offered transactions that passed task checks and both per-step deadlines.\n"
        "The vertical rule marks the 95% qualification threshold in every workload family.",
        height=4.8,
        left=0.23,
    )
    for i, (family, label) in enumerate(
        (("chat", "Chat"), ("coding", "Code"), ("rag", "Retrieval"), ("agent", "Agent"))
    ):
        for j, stage in enumerate(ORDER):
            row = agg[stage, family]
            ax.scatter(
                row["share"],
                i + (j - 1.5) * 0.13,
                color=COLOR[stage[0]],
                s=26,
                marker="o" if stage[0] == "A" else "s",
                label={"A1": "Two slots", "B1": "Four slots"}.get(stage) if i == 0 else None,
            )
        n = agg["A1", family]["offered"]
        ax.text(
            -0.03, i, f"{label} ({n}/launch)", transform=ax.get_yaxis_transform(), ha="right", va="center"
        )
    ax.axvline(0.95, color="#8b501f", linewidth=1.2, linestyle="--", label="95% target")
    ax.set(
        xlim=(0, 1.06),
        ylim=(3.65, -0.65),
        yticks=[],
        xticks=[0, 0.25, 0.50, 0.75, 1],
        xlabel="Correct and on time (share of offered)",
    )
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.legend(loc="lower left", frameon=False, fontsize=9)
    ax.grid(axis="x", color="#e1e7ed")
    export(fig, "replication-family-slo", output, web)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "public/evidence/measurements.json")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    output, web = ROOT / "docs/case-study/assets", ROOT / "public/assets"
    chat(data, output, web)
    models(data, output, web)
    replication(data, output, web)
    print("Generated five figures in SVG and PNG, with SVG copies for the site.")


if __name__ == "__main__":
    main()
