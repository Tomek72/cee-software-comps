# src/cee_comps/output_map.py
"""One-page market map: Polish e-commerce infrastructure.

Reads the `market_map` table (MarketMapCompany extractions) and
renders a scatter:
  - X: target_segment   (SMB → Mixed, encoded 1–4)
  - Y: product_scope    (Point tool → Suite, encoded 1–3)
  - bubble size: headcount (sqrt-scaled; fixed size where unknown)
  - bubble colour: primary_geography
  - label: company name beside each bubble

Exports a single high-DPI PDF page. Matplotlib label collisions on
a 20-point scatter are expected; the plan budgets 15 min of manual
cleanup in a vector editor — this produces the honest first pass.
"""
from __future__ import annotations

import hashlib
import math

import matplotlib

matplotlib.use("Agg")  # no display in a CLI/headless context
import matplotlib.pyplot as plt
from rich.console import Console

from . import db
from .config import FX_DATE, MAP_OUT

console = Console()

# Categorical → numeric axis encodings. Order matters: it sets the
# visual narrative (cheap/simple bottom-left → complex/upmarket top-right).
_SEGMENT_POS = {"smb": 1, "mid_market": 2, "enterprise": 3, "mixed": 4}
_SCOPE_POS = {"point_tool": 1, "platform": 2, "suite": 3}

_SEGMENT_TICKS = ["SMB", "Mid-Market", "Enterprise", "Mixed"]
_SCOPE_TICKS = ["Point Tool", "Platform", "Suite"]

# Stable colour per geography (avoids matplotlib reassigning between runs).
_GEO_COLOUR = {
    "poland": "#C8102E",
    "cee": "#1F77B4",
    "europe": "#2CA02C",
    "global": "#7F4FC9",
}
_GEO_LABEL = {
    "poland": "Poland",
    "cee": "CEE",
    "europe": "Europe",
    "global": "Global",
}

_FALLBACK_HEADCOUNT = 50  # bubble size for unknown headcount


def _bubble_size(headcount) -> float:
    """sqrt scaling so a 2000-person firm isn't 40× the area of a 50-person one."""
    h = headcount if (headcount and headcount > 0) else _FALLBACK_HEADCOUNT
    return 40.0 + math.sqrt(h) * 14.0


def build() -> None:
    """Read market_map and write the one-page PDF."""
    df = db.read_table("market_map")
    if df.empty:
        console.print("[red]market_map table is empty — run `classify --target map` first.[/red]")
        return

    fig, ax = plt.subplots(figsize=(11.69, 8.27))  # A4 landscape

    plotted_geographies: set[str] = set()
    for _, row in df.iterrows():
        seg = _SEGMENT_POS.get(row.get("target_segment"))
        scope = _SCOPE_POS.get(row.get("product_scope"))
        if seg is None or scope is None:
            console.print(
                f"[yellow]Skipping {row.get('company_name')}: "
                f"unmapped segment/scope.[/yellow]"
            )
            continue
        geo = row.get("primary_geography", "global")
        colour = _GEO_COLOUR.get(geo, "#888888")
        plotted_geographies.add(geo)

        # jitter avoids exact overlaps when many firms share a cell.
        # md5 (not Python's hash) so the same company lands in the same
        # spot across runs — Python's hash() is salted by PYTHONHASHSEED.
        digest = hashlib.md5(row["company_name"].encode("utf-8")).digest()
        jx = (digest[0] % 7 - 3) * 0.03
        jy = (digest[1] % 7 - 3) * 0.03

        ax.scatter(
            seg + jx, scope + jy,
            s=_bubble_size(row.get("headcount_estimate")),
            c=colour, alpha=0.55, edgecolors="white", linewidths=0.8, zorder=2,
        )
        ax.annotate(
            row["company_name"],
            (seg + jx, scope + jy),
            xytext=(6, 4), textcoords="offset points",
            fontsize=7.5, color="#222222", zorder=3,
        )

    ax.set_xticks(list(_SEGMENT_POS.values()))
    ax.set_xticklabels(_SEGMENT_TICKS)
    ax.set_yticks(list(_SCOPE_POS.values()))
    ax.set_yticklabels(_SCOPE_TICKS)
    ax.set_xlim(0.5, 4.5)
    ax.set_ylim(0.5, 3.5)
    ax.set_xlabel("Target segment", fontsize=10)
    ax.set_ylabel("Product scope", fontsize=10)
    ax.grid(True, linestyle=":", alpha=0.35, zorder=1)

    ax.set_title(
        "Polish E-commerce Infrastructure — Market Map",
        fontsize=15, fontweight="bold", pad=16,
    )
    ax.text(
        0.5, 1.015,
        f"Bubble size ∝ √headcount  ·  As of {FX_DATE}",
        transform=ax.transAxes, ha="center", fontsize=9, color="#555555",
    )

    # Geography legend — only for geographies actually present
    handles = [
        plt.Line2D(
            [0], [0], marker="o", linestyle="",
            markerfacecolor=_GEO_COLOUR[g], markeredgecolor="white",
            markersize=10, label=_GEO_LABEL[g],
        )
        for g in ("poland", "cee", "europe", "global")
        if g in plotted_geographies
    ]
    ax.legend(
        handles=handles, title="Primary geography",
        loc="lower right", fontsize=8, title_fontsize=9, framealpha=0.9,
    )

    fig.text(
        0.5, 0.02,
        "Source: company disclosures & websites · Classifications via Claude "
        "(Anthropic) · Tomasz Szymula",
        ha="center", fontsize=7.5, color="#777777",
    )

    fig.tight_layout(rect=(0, 0.04, 1, 1))
    MAP_OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(MAP_OUT, format="pdf", dpi=300, bbox_inches="tight")
    plt.close(fig)

    console.print(
        f"[green]Wrote {MAP_OUT.name} ({len(df)} companies plotted).[/green]\n"
        f"[yellow]Expect label overlaps — budget ~15 min manual cleanup in a "
        f"vector editor before using as a deliverable.[/yellow]"
    )