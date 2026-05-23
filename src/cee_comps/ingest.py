# src/cee_comps/ingest.py
"""Market data ingestion via yfinance.

Pulls shares outstanding, market cap, debt, cash, LTM revenue, and LTM
EBITDA for the comp universe. Computes enterprise value inline. Polish
tickers (.WA suffix) frequently have incomplete fundamentals on Yahoo;
config.YFINANCE_FALLBACKS provides manually-curated overrides for any
ticker that comes back empty.

All monetary values are returned in millions of listing currency. FX
normalization to EUR happens later in enrich.py.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.progress import track

from .config import COMP_TICKERS, COMP_UNIVERSE, YFINANCE_FALLBACKS

console = Console()

# yfinance Ticker.info field → our column name
_INFO_MAP: dict[str, str] = {
    "sharesOutstanding": "shares_out",
    "marketCap": "market_cap",
    "totalDebt": "total_debt",
    "totalCash": "cash",
    "totalRevenue": "ltm_revenue",
    "ebitda": "ltm_ebitda",
    "revenueGrowth": "revenue_growth_yoy",
    "financialCurrency": "currency",
}

# Columns whose raw yfinance value is a currency amount (or share count)
# and needs dividing by 1e6 to land in "millions of units".
_SCALE_TO_M: list[str] = [
    "shares_out",
    "market_cap",
    "total_debt",
    "cash",
    "ltm_revenue",
    "ltm_ebitda",
]

# Fields that must be present for a row to be useful.
_REQUIRED: list[str] = ["market_cap", "ltm_revenue"]

# Fallback config keys (in millions) → our column names
_FALLBACK_MAP: dict[str, str] = {
    "shares_out_m": "shares_out",
    "market_cap_m": "market_cap",
    "total_debt_m": "total_debt",
    "cash_m": "cash",
    "ltm_revenue_m": "ltm_revenue",
    "ltm_ebitda_m": "ltm_ebitda",
}


def _fetch_one(ticker: str) -> dict[str, Any]:
    """Pull raw .info dict from yfinance and map to our column names.

    Returns an empty dict if yfinance errors out — caller treats this as
    a 'fully missing' row and applies fallbacks.
    """
    try:
        info = yf.Ticker(ticker).info
    except Exception as e:
        console.print(f"[red]yfinance error for {ticker}:[/red] {e}")
        return {}
    return {col: info.get(yf_key) for yf_key, col in _INFO_MAP.items()}


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert raw yfinance currency/share values to millions.

    `pd.isna` (not a truthy check) so a legitimate zero (e.g. zero debt)
    survives normalisation. yfinance may return either None or NaN for
    missing fields; both collapse to None here.
    """
    out = dict(raw)
    for col in _SCALE_TO_M:
        val = out.get(col)
        out[col] = None if pd.isna(val) else val / 1_000_000
    return out


def _apply_fallback(ticker: str, row: dict[str, Any]) -> dict[str, Any]:
    """Overlay manually-curated fallback values where yfinance came up empty.

    Fallbacks only fill blanks — they never override a value yfinance returned.
    Fallback dict values are already in millions (per config schema).
    """
    fb = YFINANCE_FALLBACKS.get(ticker, {})
    if not fb:
        return row
    out = dict(row)
    for fb_key, col in _FALLBACK_MAP.items():
        fb_val = fb.get(fb_key)
        if fb_val is not None and pd.isna(out.get(col)):
            out[col] = fb_val
    # Currency override (fallback may specify it explicitly)
    if fb.get("currency") and not out.get("currency"):
        out["currency"] = fb["currency"]
    return out


def _is_incomplete(row: dict[str, Any]) -> bool:
    return any(not row.get(k) for k in _REQUIRED)


def fetch_market_data() -> pd.DataFrame:
    """Fetch market data for every ticker in COMP_UNIVERSE.

    Returns a DataFrame in listing currency, with monetary columns in
    millions. Computes enterprise_value = market_cap + total_debt - cash.
    Tickers with incomplete data after fallbacks are printed in yellow
    so they can be patched in config.YFINANCE_FALLBACKS.
    """
    rows: list[dict[str, Any]] = []
    incomplete: list[str] = []

    for ticker in track(COMP_TICKERS, description="Fetching market data"):
        raw = _fetch_one(ticker)
        row = _normalize(raw)
        row = _apply_fallback(ticker, row)

        # Compute EV in millions of listing currency
        mc = row.get("market_cap") or 0
        td = row.get("total_debt") or 0
        cs = row.get("cash") or 0
        row["enterprise_value"] = mc + td - cs if mc else None

        # Attach identifiers from config (single source of truth)
        row["ticker"] = ticker
        row["company_name"] = COMP_UNIVERSE[ticker]["name"]
        row["bucket"] = COMP_UNIVERSE[ticker]["bucket"]
        # If yfinance didn't return a currency, fall back to the config value
        row["currency"] = row.get("currency") or COMP_UNIVERSE[ticker]["currency"]

        if _is_incomplete(row):
            incomplete.append(ticker)
        rows.append(row)

    df = pd.DataFrame(rows)
    # Put identifiers first for readability
    front = ["ticker", "company_name", "bucket", "currency"]
    df = df[front + [c for c in df.columns if c not in front]]

    if incomplete:
        console.print(
            f"[yellow]Incomplete after fallbacks: {', '.join(incomplete)}.\n"
            f"Add the missing fields to config.YFINANCE_FALLBACKS and re-run.[/yellow]"
        )
    console.print(f"[green]Fetched {len(df)} tickers.[/green]")
    return df