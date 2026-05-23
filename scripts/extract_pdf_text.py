# scripts/extract_pdf_text.py
"""
Extract business-description text from source PDFs into excerpts.

For each PDF in data/source_pdfs/<TICKER>.pdf this:
  1. Searches every page for business/segment section markers.
  2. If a sensible number of pages match, extracts them plus one
     page of context on each side.
  3. If too few pages match (non-standard structure) OR too many
     (over-broad matching), falls back to dumping full document text
     so nothing relevant is silently dropped.
  4. Reports the mode used and flags empty (image-only) PDFs.

Permission flags that block copy-in-Preview do not block byte-level
text extraction; pymupdf reads the embedded text layer directly.

Usage:
    uv run python scripts/extract_pdf_text.py            # all PDFs
    uv run python scripts/extract_pdf_text.py ASE.WA     # one ticker
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import sys

import fitz  # pymupdf

from cee_comps.config import DATA_DIR, EXCERPTS_DIR

SOURCE_DIR = DATA_DIR / "source_pdfs"

# Below MIN: markers didn't match the report's structure.
# Above MAX: markers matched too promiscuously (phrases appearing in
# risk factors, notes, ESG, etc.). Either way, fall back to full text
# rather than trust a bad page selection.
MIN_PAGES_BEFORE_FALLBACK = 3
MAX_PAGES_BEFORE_FALLBACK = 35

# Hard ceiling on full-text fallback output. ~120k chars ≈ 30k tokens,
# enough to retain the business overview + segment breakdown that sit
# in the front of any annual report, while dropping the irrelevant
# back-matter that made SCT.L balloon to 699k.
MAX_FALLBACK_CHARS = 120_000

# Headings that reliably title the sections we want — not phrases that
# also appear in running prose throughout the report. Precision over
# recall: a missed section is caught by the full-text fallback; a
# false match silently bloats the excerpt.
SECTION_MARKERS = [
    # English
    "principal activities",
    "description of business",
    "operating segments",
    "revenue by segment",
    "segment information",
    "segment results",
    # Polish
    "podstawowa działalność",
    "segmenty operacyjne",
    "przychody w podziale na segmenty",
    "informacje o segmentach",
    "struktura przychodów",
    # US 20-F / 10-K item headings
    "information on the company",
    "operating and financial review",
    "business overview",
    # UK annual report headings
    "strategic report",
    "our business model",
    "how we create value",
]



def find_relevant_pages(doc) -> list[int]:
    """Page indices whose text contains any section marker, plus neighbours."""
    hits: set[int] = set()
    for i in range(len(doc)):
        text = doc[i].get_text().lower()
        if any(marker in text for marker in SECTION_MARKERS):
            hits.update({i - 1, i, i + 1})  # context padding
    return sorted(p for p in hits if 0 <= p < len(doc))


def extract_one(ticker: str) -> None:
    pdf_path = SOURCE_DIR / f"{ticker}.pdf"
    if not pdf_path.exists():
        print(f"  MISSING PDF: {pdf_path}")
        return

    doc = fitz.open(pdf_path)
    pages = find_relevant_pages(doc)

    if MIN_PAGES_BEFORE_FALLBACK <= len(pages) <= MAX_PAGES_BEFORE_FALLBACK:
        mode = f"located ({len(pages)} pages)"
        chunks = [doc[i].get_text() for i in pages]
    else:
        reason = "too few" if len(pages) < MIN_PAGES_BEFORE_FALLBACK else "too many"
        mode = f"full-text fallback ({reason}: {len(pages)} matched)"
        chunks = [doc[i].get_text() for i in range(len(doc))]

    text = "\n".join(chunks).strip()

    # Cap oversized full-text dumps. Annual reports front-load the
    # business overview and segment data; the tail is governance,
    # remuneration, and financial notes the classifier doesn't need.
    # Only applies to the fallback path — located extracts are already
    # bounded by the page band.
    if "fallback" in mode and len(text) > MAX_FALLBACK_CHARS:
        text = text[:MAX_FALLBACK_CHARS]
        mode += f", capped to {MAX_FALLBACK_CHARS:,} chars"

    out_path = EXCERPTS_DIR / f"{ticker}.txt"

    if not text:
        print(f"  EMPTY (likely image-only): {ticker} — use IR site / screenshots")
        return

    out_path.write_text(text, encoding="utf-8")
    print(f"  OK [{mode}]: {ticker} ({len(text):,} chars) -> {out_path.name}")


def main() -> None:
    EXCERPTS_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 1:
        targets = [sys.argv[1]]
    else:
        targets = sorted(p.stem for p in SOURCE_DIR.glob("*.pdf"))

    if not targets:
        print(f"No PDFs found in {SOURCE_DIR}/. Drop <TICKER>.pdf files there first.")
        return

    print(f"Extracting {len(targets)} ticker(s):")
    for ticker in targets:
        extract_one(ticker)


if __name__ == "__main__":
    main()