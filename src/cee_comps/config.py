# src/cee_comps/config.py
"""Static configuration: universe lists, paths, FX rates."""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
EXCERPTS_DIR = DATA_DIR / "annual_report_excerpts"
MAP_EXCERPTS_DIR = DATA_DIR / "market_map_excerpts"
LLM_CACHE_DIR = DATA_DIR / "llm_cache"
OUTPUT_DIR = DATA_DIR / "output"
DB_PATH = DATA_DIR / "data.db"

EXCEL_OUT = OUTPUT_DIR / "comps_v1.xlsx"
MAP_OUT = OUTPUT_DIR / "ecom_map_v1.pdf"

for d in (EXCERPTS_DIR, MAP_EXCERPTS_DIR, LLM_CACHE_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Comp universe (15 names, three buckets)
# ---------------------------------------------------------------------------
COMP_UNIVERSE: dict[str, dict] = {
    # Polish-listed
    "ASE.WA":   {"name": "Asseco Poland",   "bucket": "polish",   "currency": "PLN"},
    "CMR.WA":   {"name": "Comarch",         "bucket": "polish",   "currency": "PLN"},
    "LVC.WA":   {"name": "LiveChat",        "bucket": "polish",   "currency": "PLN"},
    "ALE.WA":   {"name": "Allegro",         "bucket": "polish",   "currency": "PLN"},
    "VRC.WA":   {"name": "Vercom",          "bucket": "polish",   "currency": "PLN"},
    # European IT services / hybrid
    "DAVA":     {"name": "Endava",          "bucket": "eu_it",    "currency": "USD"},
    "REY.MI":   {"name": "Reply SpA",       "bucket": "eu_it",    "currency": "EUR"},
    "BC8.DE":   {"name": "Bechtle",         "bucket": "eu_it",    "currency": "EUR"},
    "SCT.L":    {"name": "Softcat",         "bucket": "eu_it",    "currency": "GBP"},
    "GFT.DE":   {"name": "GFT Technologies","bucket": "eu_it",    "currency": "EUR"},
    # Pure-play SaaS benchmarks
    "GLOB":     {"name": "Globant",         "bucket": "saas",     "currency": "USD"},
    "SINCH.ST": {"name": "Sinch",           "bucket": "saas",     "currency": "SEK"},
    "HUBS":     {"name": "HubSpot",         "bucket": "saas",     "currency": "USD"},
    "KVYO":     {"name": "Klaviyo",         "bucket": "saas",     "currency": "USD"},
    "TRST.L":   {"name": "Trustpilot",      "bucket": "saas",     "currency": "GBP"},
}

COMP_TICKERS = list(COMP_UNIVERSE.keys())

# Fallback for tickers where yfinance returns incomplete fundamentals.
# Populate manually after first ingest run; values in listing currency, millions.
# Keys: shares_out_m, market_cap_m, total_debt_m, cash_m, ltm_revenue_m, ltm_ebitda_m
YFINANCE_FALLBACKS: dict[str, dict] = {
    # "VRC.WA": {"shares_out_m": ..., "market_cap_m": ..., ...},
}

# ---------------------------------------------------------------------------
# Market map universe — Polish e-commerce infrastructure / MarTech
# Pre-pick 20; trim to 15-17 after seeing what data exists.
# ---------------------------------------------------------------------------
MARKET_MAP_UNIVERSE: list[str] = [
    "SALESmango",
    "Synerise",
    "eStoreBrands",
    "Survicate",
    "Alokai",
    "Shoper",
    "IdoSell",
    "Atomstore",
    "Selly",
    "Sky-Shop",
    "Apilo",
    "Base",
    "Convertiser",
    "Tpay",
    "RTB House",
    "DataFeedWatch",
    "Ergonode"
]

# ---------------------------------------------------------------------------
# FX — single spot rate per currency, all into EUR.
# Update before each run. Note date in the methodology sheet.
# ---------------------------------------------------------------------------
FX_DATE = "2026-05-22"  # update on refresh
FX_TO_EUR: dict[str, float] = {
    "EUR": 1.0,
    "PLN": 0.2356,
    "GBP": 1.1570,
    "SEK": 0.0915,
    "USD": 0.8617,
}

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
LLM_MODEL = "claude-opus-4-7"
LLM_MAX_TOKENS = 2048


# LinkedIn headcounts — fill in during hour 7 of the plan.
# Names must match MARKET_MAP_UNIVERSE exactly. Missing entries → the
# LLM will mark headcount_source as 'estimate' and leave the value null.
MARKET_MAP_HEADCOUNTS: dict[str, int] = {
    "SALESmango": 458,
    "Synerise": 189,
    "eStoreBrands": 6, #estimte based on LinkedIn range of `1-10`
    "Survicate": 36,
    "Alokai": 112,
    "Shoper": 391,
    "IdoSell": 230,
    "Atomstore": 6,
    "Selly": 31, #estimte based on LinkedIn range of `11-50`
    "Sky-Shop": 31, #estimte based on LinkedIn range of `11-50`
    "Apilo": 31, #estimte based on LinkedIn range of `11-50`
    "Base": 201-500,
    "Convertiser": 31, #estimte based on LinkedIn range of `11-50`
    "Tpay": 194,
    "RTB House": 1405,
    "DataFeedWatch": 80,
    "Ergonode": 31 #estimte based on LinkedIn range of `11-50`
}