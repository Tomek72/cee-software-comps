# src/cee_comps/enrich.py
"""
Compute multiples and FX-normalize the comp set.

Joins `market_data` (from ingest) with `extractions` (from LLM
classification), converts monetary values to EUR alongside the
listing-currency originals, and computes the standard trading
multiples.

Multiples computed:
  - EV / Revenue (EUR basis)
  - EV / EBITDA  (EUR basis; NaN where LTM EBITDA <= 0)
  - Revenue growth YoY (passthrough from yfinance)
  - EBITDA margin (decimal)
  - Rule of 40 (revenue_growth + ebitda_margin, in percentage points)

Output table `enriched_comps` has one row per ticker. Listing-currency
columns are preserved for audit; `*_eur` columns are what feed the
Excel deliverable.
"""
from __future__ import annotations

import pandas as pd
from rich.console import Console

from . import db
from .config import FX_DATE, FX_TO_EUR

console = Console()

_MONETARY_COLS: list[str] = [
    "market_cap",
    "total_debt",
    "cash",
    "ltm_revenue",
    "ltm_ebitda",
    "enterprise_value",
]


def _fx_normalize(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add EUR-converted copies of monetary columns.

    Original columns are preserved; new columns are suffixed `_eur`.
    Rows with currencies missing from config.FX_TO_EUR get NaN in the
    EUR columns and trigger a console warning.
    """
    out = df.copy()
    unknown = set(out["currency"].dropna().unique()) - set(FX_TO_EUR.keys())
    if unknown:
        console.print(
            f"[yellow]Unknown currencies (no FX rate): {sorted(unknown)}. "
            f"Add to config.FX_TO_EUR.[/yellow]"
        )

    rate = out["currency"].map(FX_TO_EUR)
    for col in _MONETARY_COLS:
        if col in out.columns:
            out[f"{col}_eur"] = out[col] * rate
    return out


def _compute_multiples(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute EV/Revenue, EV/EBITDA, EBITDA margin, Rule of 40.

    All ratio multiples are computed in EUR for cross-currency
    comparability. Margins and growth rates are currency-agnostic.
    EV/EBITDA is set to NaN where LTM EBITDA <= 0 — a negative or zero
    multiple is meaningless and downstream peer stats use pandas mean/
    median which exclude NaN by default.
    """
    out = df.copy()

    out["ev_revenue"] = out["enterprise_value_eur"] / out["ltm_revenue_eur"]

    # EV/EBITDA — keep value only where EBITDA strictly positive
    ev_ebitda = out["enterprise_value_eur"] / out["ltm_ebitda_eur"]
    out["ev_ebitda"] = ev_ebitda.where(out["ltm_ebitda_eur"] > 0)

    out["ebitda_margin"] = out["ltm_ebitda"] / out["ltm_revenue"]

    # Rule of 40 in percentage points. Computed for all rows including
    # negative-EBITDA names (a hypergrowth SaaS with -10% margin and
    # 60% growth has a meaningful Rule of 40 of 50).
    out["rule_of_40"] = (out["revenue_growth_yoy"] + out["ebitda_margin"]) * 100

    return out


def enrich() -> pd.DataFrame:
    """
    Read market_data + extractions, join, FX-normalize, compute multiples.

    Returns the enriched DataFrame. Caller (CLI) writes to DB.
    """
    available = db.tables()
    for required in ("market_data", "extractions"):
        if required not in available:
            raise RuntimeError(
                f"Table '{required}' missing. Run the upstream stage first. "
                f"Currently available: {available}"
            )

    market = db.read_table("market_data")
    extractions = db.read_table("extractions")

    # Catch empty/stale tables here with an actionable message — otherwise
    # the inner merge yields an empty df and db.write_table raises a
    # cryptic "Refusing to write empty DataFrame" further downstream.
    if market.empty:
        raise RuntimeError(
            "market_data table is empty. Run `cee-comps fetch` first."
        )
    if extractions.empty:
        raise RuntimeError(
            "extractions table is empty. Run `cee-comps classify --target comps` first "
            "(and check that excerpts exist in data/annual_report_excerpts/)."
        )

    df = market.merge(extractions, on=["ticker", "company_name"], how="inner")
    if df.empty:
        raise RuntimeError(
            "market_data and extractions joined to zero rows — ticker/company_name "
            "mismatch between the two tables. Re-run fetch + classify."
        )
    if len(df) < len(market):
        dropped = set(market["ticker"]) - set(df["ticker"])
        console.print(
            f"[yellow]No extraction for: {sorted(dropped)} — dropped from output.[/yellow]"
        )

    df = _fx_normalize(df)
    df = _compute_multiples(df)
    df["fx_date"] = FX_DATE  # audit trail for Excel cover sheet

    console.print(
        f"[green]Enriched {len(df)} companies. FX as of {FX_DATE}.[/green]"
    )
    return df