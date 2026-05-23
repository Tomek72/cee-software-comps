# src/cee_comps/schemas.py
"""
Pydantic schemas for LLM-extracted company data.

These double as Anthropic tool input_schemas (via .model_json_schema()) and
as validation for cached extraction results. Field names and Literal values
are the contract between extract.py, enrich.py, and the output modules —
changing a Literal invalidates the LLM cache and forces re-extraction.
"""
from pydantic import BaseModel, Field
from typing import Literal


class CompanyProfile(BaseModel):
    """LLM-extracted business profile from annual report text."""
    ticker: str
    company_name: str
    one_line_description: str = Field(
        description="Neutral analyst tone, 15-25 words"
    )
    # Order matches REVENUE_MODEL_ORDER below: pure SaaS → IT services.
    # JSON Schema preserves enum order, so this is the order Claude sees;
    # keeping a single source of narrative order avoids subtle LLM bias
    # toward whichever option appears first.
    revenue_model: Literal[
        "pure_saas",
        "hybrid_saas_services",
        "transactional",
        "license_maintenance",
        "it_services",
    ]
    end_market: Literal["horizontal", "vertical_specific"]
    customer_profile: Literal[
        "enterprise", "mid_market", "smb", "consumer", "mixed"
    ]
    primary_geography: Literal["poland", "cee", "europe", "global"]
    rd_intensity_signal: Literal["high", "medium", "low"] = Field(
        description="Based on R&D as % of revenue or qualitative signal"
    )


class MarketMapCompany(BaseModel):
    """LLM-extracted profile for market map companies."""
    company_name: str
    one_line_description: str
    target_segment: Literal["smb", "mid_market", "enterprise", "mixed"]
    product_scope: Literal["point_tool", "platform", "suite"]
    headcount_estimate: int | None
    headcount_source: Literal["linkedin", "disclosed", "estimate"]
    primary_geography: Literal["poland", "cee", "europe", "global"]
    plausible_strategic_acquirers: list[str] = Field(
        description="3-5 named companies, inferred from product fit and known M&A patterns",
        max_length=5,
    )
    equity_story_pillar: str = Field(
        description="One sentence on the strongest narrative angle"
    )

# ---------------------------------------------------------------------------
# Display + ordering helpers
# Used by output_excel.py (sort order, group labels) and output_map.py
# (axis tick labels). Keeping them next to the schemas means changing a
# Literal value forces you to update the label in the same file.
# ---------------------------------------------------------------------------

REVENUE_MODEL_ORDER: list[str] = [
    "pure_saas",
    "hybrid_saas_services",
    "transactional",
    "license_maintenance",
    "it_services",
]

REVENUE_MODEL_LABELS: dict[str, str] = {
    "pure_saas": "Pure SaaS",
    "hybrid_saas_services": "Hybrid SaaS / Services",
    "transactional": "Transactional",
    "license_maintenance": "License & Maintenance",
    "it_services": "IT Services",
}

TARGET_SEGMENT_ORDER: list[str] = ["smb", "mid_market", "enterprise", "mixed"]
TARGET_SEGMENT_LABELS: dict[str, str] = {
    "smb": "SMB",
    "mid_market": "Mid-Market",
    "enterprise": "Enterprise",
    "mixed": "Mixed",
}

PRODUCT_SCOPE_ORDER: list[str] = ["point_tool", "platform", "suite"]
PRODUCT_SCOPE_LABELS: dict[str, str] = {
    "point_tool": "Point Tool",
    "platform": "Platform",
    "suite": "Suite",
}

GEOGRAPHY_LABELS: dict[str, str] = {
    "poland": "Poland",
    "cee": "CEE",
    "europe": "Europe",
    "global": "Global",
}