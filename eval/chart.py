"""`make chart`: bar chart of ₹ lost to attacks per defence -> eval/chart.png (slide 10)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from eval.summary import summarise  # noqa: E402
from shared.money import inr  # noqa: E402

LABEL = {"agent_alone": "Agent alone", "hardened_prompt": "Hardened prompt", "rails": "Today's rails", "leash": "Leash"}
COLOR = {"agent_alone": "#FF5C7A", "hardened_prompt": "#FF8FA3", "rails": "#FBBF24", "leash": "#34D399"}

if __name__ == "__main__":
    s = summarise()
    if not s["available"]:
        raise SystemExit("no eval/results.csv yet: run `make eval` first")
    ds = s["defences"]
    vals = [s["lost_paise"][d] / 100 for d in ds]
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
    fig.patch.set_facecolor("#1B1249")
    ax.set_facecolor("#1B1249")
    bars = ax.bar([LABEL[d] for d in ds], vals, color=[COLOR[d] for d in ds], width=0.6)
    for b, d in zip(bars, ds):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), inr(s["lost_paise"][d]),
                ha="center", va="bottom", color="white", fontsize=15, fontweight="bold")
    ax.set_title(f"₹ lost to {s['attack_total']} attacks (mean of {s['runs']} runs, {s['model']})",
                 color="white", fontsize=15, pad=14)
    ax.set_ylabel("₹ lost", color="#CBD5E1")
    ax.tick_params(colors="#CBD5E1", labelsize=12)
    for sp in ax.spines.values():
        sp.set_color("#4B3EA6")
    ax.margins(y=0.15)
    out = "eval/chart.png"
    fig.tight_layout()
    fig.savefig(out, facecolor=fig.get_facecolor())
    print(f"wrote {out}")
