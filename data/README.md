# Source PDFs (not committed)

Raw annual report PDFs, named by ticker to match the excerpt
convention: `ASE.WA.pdf` → `../annual_report_excerpts/ASE.WA.txt`.

These are gitignored — they're heavy binary source material, not
pipeline state. To reproduce the excerpts, download each company's
most recent annual report from its investor relations site, save
it here with the ticker filename, then run:

    uv run python scripts/extract_pdf_text.py