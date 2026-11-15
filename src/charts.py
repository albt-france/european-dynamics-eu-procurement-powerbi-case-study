"""Report charts (matplotlib -> inline SVG). House style of the earlier case studies: light card background,
blue = European Dynamics / the data, grey = the comparison, dashed = targets, Segoe UI, labels on the bars."""
from __future__ import annotations

import io
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BLUE, BLUE_L, BLUE_D = "#2A78D6", "#86B6EF", "#1C5CAB"
GRAY, GRAY_D, RED = "#C9C7BF", "#898781", "#D03B3B"
INK, INK2, GRID, CARD = "#0B0B0B", "#52514E", "#E1E0D9", "#FCFCFB"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9.5, "text.color": INK2,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.facecolor": CARD, "figure.facecolor": CARD,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.grid.axis": "x", "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": GRAY_D, "ytick.color": INK2, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False, "legend.fontsize": 9,
    "svg.fonttype": "none", "axes.axisbelow": True,
})


def fig(w_px, h_px):
    return plt.subplots(figsize=(w_px / 96, h_px / 96), dpi=96)


def svg(f) -> str:
    buf = io.StringIO()
    f.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.05)
    plt.close(f)
    s = buf.getvalue()
    s = s[s.find("<svg"):]
    return re.sub(r'width="[\d.]+pt" height="[\d.]+pt"', 'width="100%" height="100%" preserveAspectRatio="xMidYMid meet"', s, 1)


def hbar(labels, values, w=560, h=300, fmt="{:,.0f}", color=BLUE, highlight=None, xlabel=None):
    f, ax = fig(w, h)
    y = np.arange(len(labels))[::-1]
    cols = [BLUE if (highlight is None or l in highlight) else GRAY for l in labels] if highlight else color
    ax.barh(y, values, color=cols, height=0.65)
    ax.set_yticks(y, labels)
    for yi, v in zip(y, values):
        ax.text(v, yi, " " + fmt.format(v), va="center", fontsize=8.5, color=INK)
    ax.set_xlim(0, max(values) * 1.18 if len(values) else 1)
    ax.set_xticks([])
    ax.grid(False)
    if xlabel:
        ax.set_xlabel(xlabel)
    return svg(f)


def awards_by_year(df, w=640, h=290):
    """df: Year, EU, National, MovingAvg"""
    f, ax = fig(w, h)
    x = df.Year.values
    ax.bar(x, df.EU, color=BLUE, width=0.65, label="EU institutions and agencies")
    ax.bar(x, df.National, bottom=df.EU, color=BLUE_L, width=0.65, label="National and other public buyers")
    ax.plot(x, df.MovingAvg, color=INK2, lw=1.6, marker="o", ms=3, label="3-year moving average (total)")
    for xi, t in zip(x, df.EU + df.National):
        ax.text(xi, t + 0.4, f"{t:.0f}", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(x, [str(v) + ("*" if v == x.max() else "") for v in x])
    ax.grid(axis="y")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", ncol=3, fontsize=8.5)
    ax.set_ylim(0, (df.EU + df.National).max() * 1.35)
    return svg(f)


def paired_bars(labels, a, b, la, lb, w=560, h=280, pct=True):
    f, ax = fig(w, h)
    y = np.arange(len(labels))[::-1]
    ax.barh(y + 0.18, a, height=0.34, color=BLUE, label=la)
    ax.barh(y - 0.18, b, height=0.34, color=GRAY, label=lb)
    for yi, va, vb in zip(y, a, b):
        ax.text(va, yi + 0.18, f" {va:.0%}" if pct else f" {va:.1f}", va="center", fontsize=8.5, color=INK)
        ax.text(vb, yi - 0.18, f" {vb:.0%}" if pct else f" {vb:.1f}", va="center", fontsize=8.5, color=INK2)
    ax.set_yticks(y, labels)
    ax.set_xticks([])
    ax.grid(False)
    ax.set_xlim(0, max(max(a), max(b)) * 1.25)
    ax.legend(loc="lower right")
    return svg(f)


def share_line(years, share, w=520, h=250):
    f, ax = fig(w, h)
    ax.plot(years, share, color=BLUE, lw=2, marker="o", ms=4)
    for x, v in zip(years, share):
        ax.text(x, v + 0.002, f"{v:.1%}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(years, [str(v) + ("*" if v == max(years) else "") for v in years])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_ylim(0, max(share) * 1.3)
    return svg(f)


def fts_years(df, w=640, h=280):
    """df: Year, Contracted, Consumed (EUR)"""
    f, ax = fig(w, h)
    x = np.arange(len(df))
    ax.bar(x - 0.2, df.Contracted / 1e6, width=0.4, color=BLUE, label="Committed (contracted)")
    ax.bar(x + 0.2, df.Consumed / 1e6, width=0.4, color=GRAY, label="Estimated consumed")
    for xi, v in zip(x, df.Contracted / 1e6):
        ax.text(xi - 0.2, v + 0.8, f"{v:.0f}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x, df.Year.astype(str))
    ax.set_ylabel("EUR million")
    ax.grid(axis="y")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    return svg(f)


def perf(df, w=560, h=250):
    """df: query, before, first, tuned (logical reads)"""
    f, ax = fig(w, h)
    y = np.arange(len(df))[::-1]
    for off, col, c, lab in ((0.27, "before", GRAY, "No nonclustered index"), (0, "first", BLUE_L, "First index set"),
                             (-0.27, "tuned", BLUE, "Tuned covering indexes")):
        ax.barh(y + off, df[col], height=0.25, color=c, label=lab)
        for yi, v in zip(y, df[col]):
            ax.text(v, yi + off, f" {v}", va="center", fontsize=8, color=INK)
    ax.set_yticks(y, df["query"])
    ax.set_xticks([])
    ax.grid(False)
    ax.set_xlabel("logical reads (lower is better)")
    ax.legend(loc="lower right", fontsize=8)
    return svg(f)


def sla(labels, values, target=0.9, w=520, h=250):
    f, ax = fig(w, h)
    y = np.arange(len(labels))[::-1]
    ax.barh(y, values, color=[BLUE if v >= target else BLUE_L for v in values], height=0.6)
    for yi, v in zip(y, values):
        ax.text(v, yi, f" {v:.1%}", va="center", fontsize=8.5, color=INK)
    ax.axvline(target, color=INK2, ls="--", lw=1)
    ax.text(target, len(labels) - 0.4, " 90% target", fontsize=8, color=INK2)
    ax.set_yticks(y, labels)
    ax.set_xticks([])
    ax.grid(False)
    ax.set_xlim(0, 1.08)
    return svg(f)


def star_schema() -> str:
    """Hand-laid SVG of the model (boxes + one-to-many lines)."""
    boxes = {  # name: (x, y, w, kind)
        "FactAward": (330, 170, 170, "fact"), "FactFts": (330, 420, 170, "fact"),
        "DimDate": (600, 300, 150, "dim"), "DimEntity": (60, 300, 150, "dim"),
        "DimBuyer": (90, 40, 140, "dim"), "DimCountry": (345, 20, 140, "dim"), "DimCPV": (590, 40, 130, "dim"),
        "DimProcedure": (640, 165, 160, "dim"), "DimDepartment": (110, 540, 170, "dim"), "DimProgramme": (540, 540, 170, "dim"),
        "FactServiceRequest": (790, 420, 200, "sim"), "DimAgency": (815, 540, 150, "sim"),
    }
    links = [("FactAward", "DimDate"), ("FactAward", "DimEntity"), ("FactAward", "DimBuyer"), ("FactAward", "DimCountry"),
             ("FactAward", "DimCPV"), ("FactAward", "DimProcedure"), ("FactFts", "DimDate"), ("FactFts", "DimEntity"),
             ("FactFts", "DimDepartment"), ("FactFts", "DimProgramme"), ("FactServiceRequest", "DimDate"),
             ("FactServiceRequest", "DimAgency")]
    H = 40

    def c(n):
        x, y, w, _ = boxes[n]
        return x + w / 2, y + H / 2
    out = ['<svg viewBox="0 0 1000 620" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI" font-size="16">']
    for a, b in links:
        (x1, y1), (x2, y2) = c(a), c(b)
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#B4B2A9" stroke-width="1.4"/>')
    style = {"fact": ("#2A78D6", "#FFFFFF"), "dim": ("#EEF5FD", "#1C5CAB"), "sim": ("#F4F4F2", "#52514E")}
    for n, (x, y, w, k) in boxes.items():
        fill, txt = style[k]
        stroke = "#86B6EF" if k != "sim" else "#B4B2A9"
        dash = ' stroke-dasharray="4 3"' if k == "sim" else ""
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{H}" rx="6" fill="{fill}" stroke="{stroke}"{dash}/>')
        out.append(f'<text x="{x + w / 2}" y="{y + 26}" text-anchor="middle" fill="{txt}" font-weight="600">{n}</text>')
    out.append('<text x="795" y="408" fill="#52514E" font-size="14">SIMULATED (RLS demo)</text>')
    out.append('<text x="10" y="612" fill="#898781" font-size="13">All relationships one-to-many, single direction · '
               'blue = fact, light = dimension · plus Time Calc (calculation group), Axis (field parameter), _Measures</text>')
    out.append("</svg>")
    return "".join(out)
