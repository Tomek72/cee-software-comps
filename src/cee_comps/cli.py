# src/cee_comps/cli.py
import typer
from rich.console import Console

from . import db, enrich, extract, ingest, output_excel, output_map

app = typer.Typer()
console = Console()


@app.command()
def fetch():
    """Fetch market data for the comp universe and persist it."""
    df = ingest.fetch_market_data()
    db.write_table("market_data", df)
    console.print(f"[green]Fetched and stored {len(df)} companies[/green]")


@app.command()
def classify(target: str = "comps"):
    """Run LLM extraction and persist it. target: 'comps' or 'map'."""
    if target == "comps":
        df = extract.run_comp_extraction()
        db.write_table("extractions", df)
        console.print(f"[green]Stored {len(df)} comp extractions[/green]")
    elif target == "map":
        df = extract.run_map_extraction()
        db.write_table("market_map", df)
        console.print(f"[green]Stored {len(df)} map extractions[/green]")
    else:
        console.print(f"[red]Unknown target '{target}'. Use 'comps' or 'map'.[/red]")
        raise typer.Exit(1)


@app.command()
def build(output: str = "all"):
    """Enrich + build outputs. output: 'excel', 'map', or 'all'."""
    # Enrich is cheap and idempotent; always refresh before building so
    # the outputs reflect the latest market_data + extractions.
    enriched = enrich.enrich()
    db.write_table("enriched_comps", enriched)

    if output in ("excel", "all"):
        output_excel.build()
    if output in ("map", "all"):
        output_map.build()


if __name__ == "__main__":
    app()