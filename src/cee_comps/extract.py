# src/cee_comps/extract.py
"""
LLM extraction with content-hash caching.

Uses Anthropic forced tool use to coerce annual-report excerpts and
market-map descriptions into Pydantic-validated profiles. Results are
cached by content hash so re-runs of identical (prompt, schema) pairs
cost nothing.

Migration note: Anthropic released native structured outputs to GA in
late 2025 (`output_config={"format": {"type": "json_schema", ...}}`).
That path uses grammar-constrained decoding, which guarantees Literal
enum values are emitted exactly (avoiding occasional ValidationError
from near-miss strings like "hybrid" vs "hybrid_saas_services").
Forced tool use is sufficient for v1; output_config is the v2 upgrade.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Type, TypeVar

import pandas as pd
from anthropic import Anthropic
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.progress import track

from dotenv import load_dotenv
load_dotenv()

from .config import (
    COMP_UNIVERSE,
    EXCERPTS_DIR,
    LLM_CACHE_DIR,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    MAP_EXCERPTS_DIR,
    MARKET_MAP_HEADCOUNTS,
    MARKET_MAP_UNIVERSE,
)
from .schemas import CompanyProfile, MarketMapCompany

T = TypeVar("T", bound=BaseModel)
console = Console()


# ---------------------------------------------------------------------------
# Core wrapper
# ---------------------------------------------------------------------------

def _cache_path(prompt: str, schema_cls: Type[BaseModel]) -> Path:
    """Hash key includes prompt, full schema definition, and model id so that
    changing a Literal (or switching models) invalidates stale cache entries."""
    schema_json = json.dumps(schema_cls.model_json_schema(), sort_keys=True)
    key = f"{LLM_MODEL}:{schema_cls.__name__}:{schema_json}:{prompt}"
    h = hashlib.sha256(key.encode()).hexdigest()[:16]
    return LLM_CACHE_DIR / f"{schema_cls.__name__}_{h}.json"


def extract_with_schema(prompt: str, schema_cls: Type[T]) -> T:
    """Call Claude with forced tool use, validate against schema, cache result."""
    cache = _cache_path(prompt, schema_cls)
    if cache.exists():
        return schema_cls.model_validate_json(cache.read_text())

    client = Anthropic()
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        tools=[
            {
                "name": "record",
                "description": f"Record the extracted {schema_cls.__name__}.",
                "input_schema": schema_cls.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": "record"},
        messages=[{"role": "user", "content": prompt}],
    )

    # Forced tool use guarantees exactly one tool_use block in the response.
    tool_block = next(b for b in response.content if b.type == "tool_use")
    result = schema_cls.model_validate(tool_block.input)
    cache.write_text(result.model_dump_json(indent=2))
    return result


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _build_comp_prompt(ticker: str, company_name: str, excerpt: str) -> str:
    return (
        f"You are classifying {company_name} ({ticker}) using the `record` tool.\n\n"
        f"Pick the single best-fit Literal value for each enum based on the excerpt below. "
        f"Use neutral analyst tone for the one-line description (15-25 words). "
        f"Do not invent specific numerical facts that are not stated.\n\n"
        f"<excerpt>\n{excerpt}\n</excerpt>"
    )


def _build_map_prompt(name: str, excerpt: str, headcount: int | None) -> str:
    if headcount is not None:
        headcount_line = (
            f"LinkedIn headcount (use this verbatim, do not estimate): {headcount}. "
            f"Set headcount_source to 'linkedin'.\n\n"
        )
    else:
        headcount_line = (
            "Headcount not provided. Leave headcount_estimate as null and set "
            "headcount_source to 'estimate'.\n\n"
        )
    return (
        f"You are classifying {name} for a Polish e-commerce infrastructure "
        f"market map using the `record` tool.\n\n"
        f"{headcount_line}"
        f"Pick the single best-fit Literal value for each enum. "
        f"For plausible_strategic_acquirers, infer 3-5 named companies based on "
        f"product fit and known M&A patterns (adjacent SaaS players, regional "
        f"consolidators, PE platforms). Use neutral analyst tone throughout.\n\n"
        f"<excerpt>\n{excerpt}\n</excerpt>"
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """SALESmanago → salesmanago, Vue Storefront → vue_storefront."""
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


def run_comp_extraction() -> pd.DataFrame:
    """Extract CompanyProfile for every ticker in COMP_UNIVERSE."""
    rows: list[dict] = []
    missing: list[str] = []

    for ticker, meta in track(COMP_UNIVERSE.items(), description="Extracting comps"):
        excerpt_path = EXCERPTS_DIR / f"{ticker}.txt"
        if not excerpt_path.exists():
            missing.append(ticker)
            continue
        excerpt = excerpt_path.read_text(encoding="utf-8").strip()
        prompt = _build_comp_prompt(ticker, meta["name"], excerpt)
        try:
            profile = extract_with_schema(prompt, CompanyProfile)
        except ValidationError as e:
            console.print(f"[red]Validation failed for {ticker}:[/red] {e}")
            continue
        except Exception as e:
            # Transient API/network failure on one ticker shouldn't lose
            # progress on the rest of the batch — already-cached results
            # are safely on disk, and re-running picks them up for free.
            console.print(f"[red]Extraction failed for {ticker}:[/red] {e}")
            continue
        # Overwrite ticker/name with canonical values from config — the LLM
        # occasionally normalizes ("Asseco" vs "Asseco Poland S.A.") and we
        # want exact joins downstream.
        rows.append(
            profile.model_dump() | {"ticker": ticker, "company_name": meta["name"]}
        )

    if missing:
        console.print(f"[yellow]Missing excerpts: {', '.join(missing)}[/yellow]")
    df = pd.DataFrame(rows)
    console.print(f"[green]Extracted {len(df)} comp profiles.[/green]")
    return df


def run_map_extraction() -> pd.DataFrame:
    """Extract MarketMapCompany for every name in MARKET_MAP_UNIVERSE."""
    rows: list[dict] = []
    missing: list[str] = []

    for name in track(MARKET_MAP_UNIVERSE, description="Extracting map"):
        excerpt_path = MAP_EXCERPTS_DIR / f"{_slugify(name)}.txt"
        if not excerpt_path.exists():
            missing.append(name)
            continue
        excerpt = excerpt_path.read_text(encoding="utf-8").strip()
        prompt = _build_map_prompt(name, excerpt, MARKET_MAP_HEADCOUNTS.get(name))
        try:
            profile = extract_with_schema(prompt, MarketMapCompany)
        except ValidationError as e:
            console.print(f"[red]Validation failed for {name}:[/red] {e}")
            continue
        except Exception as e:
            console.print(f"[red]Extraction failed for {name}:[/red] {e}")
            continue
        rows.append(profile.model_dump() | {"company_name": name})

    if missing:
        console.print(f"[yellow]Missing excerpts: {', '.join(missing)}[/yellow]")
    df = pd.DataFrame(rows)
    console.print(f"[green]Extracted {len(df)} map profiles.[/green]")
    return df