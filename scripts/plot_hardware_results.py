"""Plot an archived IBM experiment without connecting to IBM or submitting jobs."""

import argparse
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "shor-matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "shor-cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = json.loads((args.directory / "analysis.json").read_text())
    manifest = json.loads((args.directory / "prepare.json").read_text())
    fig, axes = plt.subplots(len(report["experiments"]), 1, figsize=(12, 10))
    fig.patch.set_facecolor("#fafbfc")
    for ax, result, prepared in zip(axes, report["experiments"], manifest["experiments"]):
        bits = result["counting_qubits"]
        keys = [format(i, f"0{bits}b") for i in range(1 << bits)]
        xs = np.arange(len(keys))
        observed = np.array([result["counts"].get(key, 0) / result["shots"] for key in keys])
        ideal = np.array([result["ideal_probabilities"][key] for key in keys])
        z, n = 1.96, result["shots"]
        denominator = 1 + z * z / n
        center = (observed + z * z / (2 * n)) / denominator
        half_width = z * np.sqrt(observed * (1 - observed) / n + z * z / (4 * n * n)) / denominator
        errors = np.maximum(0, np.array([observed - center + half_width, center + half_width - observed]))
        ax.bar(xs, observed, width=.72, color="#247d96", label="IBM hardware", zorder=3)
        ax.errorbar(xs, observed, yerr=errors, fmt="none", ecolor="#143743", elinewidth=.8, capsize=2, zorder=4)
        ax.plot(xs, ideal, "o", color="#e58a35", ms=5, label="Ideal circuit", zorder=5)
        ax.axhline(1 / len(keys), color="#7e858d", ls="--", lw=1.2, label="Uniform noise")
        factors = " × ".join(map(str, result["factors"])) if result["factors"] else "not recovered"
        gates = prepared["selected"]["two_qubit_gates"]
        ax.set_title(
            f"N = {result['modulus']}  →  {factors}     |     {bits} phase bits, {gates} native two-qubit gates",
            loc="left", fontsize=12, weight="bold", pad=14,
        )
        ax.text(.99, .96, f"Distribution fidelity: {result['classical_fidelity']:.1%}",
                transform=ax.transAxes, ha="right", va="top", fontsize=10, color="#32434b")
        ax.set_xticks(xs)
        ax.set_xticklabels([str(i) for i in xs], fontsize=8)
        ax.set_xlabel("Measured phase-register integer  y  (phase = y / 2ᵗ)", fontsize=10)
        ax.set_ylabel("Probability", fontsize=10)
        ax.set_ylim(0, max(max(ideal), max(observed)) * 1.25)
        ax.set_xlim(-.7, len(keys) - .3)
        ax.grid(axis="y", color="#e5e9ec", lw=.7, zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["bottom", "left"]].set_color("#c4cbd0")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(.075, .925), ncol=3, frameon=False, fontsize=10)
    fig.suptitle("Shor demonstrations on IBM Fez", x=.075, y=.98, ha="left", fontsize=21, weight="bold")
    fig.text(.075, .944,
             "4,096 shots per circuit · Raw counts · Compiled circuits for specific instances · November 16, 2026",
             fontsize=10, color="#52606a")
    fig.text(.075, .023,
             f"Job: {report['job_id']}  |  Error bars: 95% marginal Wilson intervals.\n"
             "The N=21 work register uses a precomputed encoding; these experiments do not demonstrate a scalable quantum speedup.",
             fontsize=9, color="#52606a", linespacing=1.6)
    fig.subplots_adjust(left=.075, right=.97, top=.86, bottom=.11, hspace=.62)
    for extension in ("png", "svg"):
        path = args.directory / f"phase_distributions.{extension}"
        fig.savefig(path, dpi=180, facecolor=fig.get_facecolor())
        print(path.resolve())


if __name__ == "__main__":
    main()
