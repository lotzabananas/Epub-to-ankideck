"""Command-line interface for EPUB to Anki conversion."""

import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from .exporter import AnkiExporter
from .exporter.anki_exporter import export_cards_to_json
from .generator import CardGenerator
from .models import CardStatus, ChapterCards, Density
from .parser import parse_epub
from .parser.epub_parser import get_book_summary
from .ranker import CardRanker

console = Console()


def display_book_info(book) -> None:
    """Display parsed book information."""
    summary = get_book_summary(book)
    console.print(Panel(summary, title="[bold]Book Loaded[/bold]", border_style="green"))


def display_chapter_cards_summary(chapter_cards: ChapterCards) -> None:
    """Display summary of generated cards for a chapter."""
    ranker = CardRanker()
    stats = ranker.get_score_distribution(chapter_cards)

    table = Table(title=f"Chapter {chapter_cards.chapter.index + 1}: {chapter_cards.chapter.title}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Cards", str(stats["total"]))
    table.add_row("Score Range", f"{stats['min']} - {stats['max']}")
    table.add_row("Mean Score", str(stats["mean"]))

    console.print(table)

    # Show bucket distribution
    bucket_table = Table(title="Score Distribution")
    bucket_table.add_column("Score Range", style="cyan")
    bucket_table.add_column("Count", style="yellow")

    for bucket, count in stats["buckets"].items():
        bucket_table.add_row(bucket, str(count))

    console.print(bucket_table)


def display_cards_preview(cards: list, limit: int = 5) -> None:
    """Display a preview of cards."""
    console.print(f"\n[bold]Sample Cards (showing {min(limit, len(cards))} of {len(cards)}):[/bold]\n")

    for i, card in enumerate(cards[:limit]):
        score = card.compute_score()
        status_icon = "[green]✓[/green]" if card.status == CardStatus.INCLUDED else "[red]✗[/red]"

        console.print(f"{status_icon} [{card.format.value.upper()}] Score: {score:.1f}")
        console.print(f"   {card.get_display_text()}")
        console.print()


def interactive_threshold_selection(chapter_cards: ChapterCards, ranker: CardRanker) -> float:
    """Interactively select threshold for a chapter."""
    # Show current distribution
    display_chapter_cards_summary(chapter_cards)

    # Preview different thresholds
    console.print("\n[bold]Threshold Previews:[/bold]")
    for threshold in [3.0, 5.0, 7.0, 8.0]:
        preview = ranker.preview_threshold(chapter_cards, threshold)
        console.print(
            f"  Threshold {threshold}: "
            f"[green]{preview['would_include']} included[/green], "
            f"[red]{preview['would_exclude']} excluded[/red]"
        )

    # Get user choice
    console.print()
    choice = Prompt.ask(
        "Enter threshold (1-10) or 'auto' for density-based",
        default="auto",
    )

    if choice.lower() == "auto":
        return -1  # Signal to use density-based threshold

    try:
        return float(choice)
    except ValueError:
        console.print("[yellow]Invalid input, using auto threshold[/yellow]")
        return -1


@click.group()
def cli():
    """EPUB to Anki - Generate flashcards from books using Claude."""
    pass


@cli.command()
@click.argument("epub_path", type=click.Path(exists=True))
def info(epub_path: str):
    """Show information about an EPUB file."""
    console.print(f"\n[bold]Parsing:[/bold] {epub_path}\n")

    with console.status("Parsing EPUB..."):
        book = parse_epub(epub_path)

    display_book_info(book)


@cli.command()
@click.argument("epub_path", type=click.Path(exists=True))
@click.option(
    "--output", "-o",
    type=click.Path(),
    help="Output directory (default: ./output/<book-title>)",
)
@click.option(
    "--density", "-d",
    type=click.Choice(["light", "medium", "thorough"]),
    default="medium",
    help="Card generation density",
)
@click.option(
    "--chapters", "-c",
    type=str,
    help="Specific chapters to process (e.g., '1,2,3' or '1-5')",
)
@click.option(
    "--auto", "-a",
    is_flag=True,
    help="Skip manual review, use automatic thresholds",
)
@click.option(
    "--threshold", "-t",
    type=float,
    help="Custom importance threshold (1-10)",
)
def generate(
    epub_path: str,
    output: Optional[str],
    density: str,
    chapters: Optional[str],
    auto: bool,
    threshold: Optional[float],
):
    """Generate Anki deck from an EPUB file."""
    density_enum = Density(density)

    # Parse EPUB
    console.print(f"\n[bold]Parsing:[/bold] {epub_path}\n")
    with console.status("Parsing EPUB..."):
        book = parse_epub(epub_path)

    display_book_info(book)

    # Parse chapter selection
    chapter_indices = None
    if chapters:
        chapter_indices = parse_chapter_selection(chapters, len(book.chapters))
        console.print(f"\n[bold]Processing chapters:[/bold] {chapter_indices}")

    # Confirm before proceeding
    if not auto:
        if not Confirm.ask("\nProceed with card generation?"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    # Initialize components
    generator = CardGenerator()
    ranker = CardRanker()

    # Generate cards for each chapter
    all_chapter_cards: list[ChapterCards] = []

    chapters_to_process = book.chapters
    if chapter_indices:
        chapters_to_process = [ch for ch in book.chapters if ch.index in chapter_indices]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating cards...", total=len(chapters_to_process))

        for chapter in chapters_to_process:
            progress.update(task, description=f"Processing: {chapter.title[:40]}...")

            # Generate cards
            chapter_cards = generator.generate_for_chapter(book, chapter, density_enum)

            # Rank cards
            ranker.rank_chapter(chapter_cards)

            # Apply threshold
            if auto or threshold:
                # Auto mode: use provided threshold or density-based default
                if threshold:
                    ranker.apply_custom_threshold(chapter_cards, threshold)
                else:
                    ranker.apply_density_threshold(chapter_cards)
            else:
                # Interactive mode: ask user
                progress.stop()
                console.print(f"\n[bold]Chapter {chapter.index + 1}: {chapter.title}[/bold]")
                user_threshold = interactive_threshold_selection(chapter_cards, ranker)

                if user_threshold == -1:
                    ranker.apply_density_threshold(chapter_cards)
                else:
                    ranker.apply_custom_threshold(chapter_cards, user_threshold)

                # Show preview
                display_cards_preview(chapter_cards.cards)

                # Ask if user wants to continue with remaining chapters on auto
                if len(chapters_to_process) > 1:
                    if Confirm.ask("Apply same threshold to remaining chapters?"):
                        auto = True
                        if user_threshold != -1:
                            threshold = user_threshold

                progress.start()

            all_chapter_cards.append(chapter_cards)
            progress.advance(task)

    # Summary
    total_cards = sum(len(cc.cards) for cc in all_chapter_cards)
    included_cards = sum(len(cc.included_cards) for cc in all_chapter_cards)
    excluded_cards = sum(len(cc.excluded_cards) for cc in all_chapter_cards)

    console.print("\n[bold]Generation Complete![/bold]")
    console.print(f"  Total cards generated: {total_cards}")
    console.print(f"  [green]Included: {included_cards}[/green]")
    console.print(f"  [red]Excluded: {excluded_cards}[/red]")

    # Set up output directory
    if output:
        output_dir = Path(output)
    else:
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in book.title)
        output_dir = Path("output") / safe_title

    output_dir.mkdir(parents=True, exist_ok=True)

    # Export to JSON
    console.print(f"\n[bold]Saving to:[/bold] {output_dir}")
    export_cards_to_json(all_chapter_cards, output_dir, book.title)

    # Export to Anki
    deck_name = f"{book.title} - {book.author}"
    exporter = AnkiExporter(deck_name)

    for chapter_cards in all_chapter_cards:
        exporter.add_chapter_cards(chapter_cards, include_excluded=False)

    apkg_path = output_dir / f"{safe_title}.apkg"
    exporter.export(apkg_path)

    console.print(f"\n[green]✓[/green] Anki deck exported: {apkg_path}")
    console.print(f"[green]✓[/green] JSON backup saved to: {output_dir}/included/ and {output_dir}/excluded/")


@cli.command()
@click.argument("json_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output .apkg path")
@click.option("--name", "-n", type=str, help="Deck name")
def export(json_dir: str, output: Optional[str], name: Optional[str]):
    """Export previously generated cards to Anki format."""
    json_dir = Path(json_dir)

    # Read metadata
    meta_path = json_dir / "metadata.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text())
        deck_name = name or metadata.get("book_title", "Imported Deck")
    else:
        deck_name = name or "Imported Deck"

    # Collect all included cards
    included_dir = json_dir / "included"
    if not included_dir.exists():
        console.print("[red]No included cards found![/red]")
        return

    exporter = AnkiExporter(deck_name)
    card_count = 0

    for json_file in sorted(included_dir.glob("*.json")):
        cards_data = json.loads(json_file.read_text())
        for card_data in cards_data:
            from .models import Card

            card = Card(**card_data)
            exporter.add_card(card)
            card_count += 1

    if output:
        output_path = Path(output)
    else:
        output_path = json_dir / f"{deck_name}.apkg"

    exporter.export(output_path)
    console.print(f"[green]✓[/green] Exported {card_count} cards to: {output_path}")


def parse_chapter_selection(selection: str, total_chapters: int) -> list[int]:
    """Parse chapter selection string like '1,2,3' or '1-5' into indices."""
    indices = set()

    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start_idx = int(start) - 1  # Convert to 0-indexed
            end_idx = int(end)  # Inclusive end
            indices.update(range(start_idx, end_idx))
        else:
            indices.add(int(part) - 1)  # Convert to 0-indexed

    # Filter valid indices
    return sorted(i for i in indices if 0 <= i < total_chapters)


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
