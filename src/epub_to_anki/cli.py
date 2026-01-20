"""Command-line interface for EPUB to Anki conversion."""

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .checkpoint import CheckpointManager
from .cost_estimator import CostEstimator
from .deduplicator import CardDeduplicator
from .exporter import AnkiExporter
from .exporter.anki_exporter import MultiBookExporter, export_cards_to_json
from .generator import CardGenerator
from .models import CardStatus, ChapterCards, DeckConfig, Density
from .parser import parse_epub
from .parser.epub_parser import get_book_summary
from .ranker import CardRanker

console = Console()


def display_book_info(book, include_images: bool = False) -> None:
    """Display parsed book information."""
    summary = get_book_summary(book, include_images=include_images)
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


def display_cost_estimate(
    book, density: Density, chapter_indices: Optional[list[int]] = None
) -> None:
    """Display cost estimate before generation."""
    estimator = CostEstimator()
    estimate = estimator.estimate_book(book, density, chapter_indices)

    table = Table(title="Cost Estimate", border_style="blue")
    table.add_column("Item", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Chapters to process", str(estimate.chapters_count))
    table.add_row("Total words", f"{estimate.total_words:,}")
    table.add_row("Density", estimate.density)
    table.add_row("Input tokens (est.)", f"~{estimate.total_input_tokens:,}")
    table.add_row("Output tokens (est.)", f"~{estimate.total_output_tokens:,}")
    table.add_row(
        "[bold]Estimated cost[/bold]", f"[bold]${estimate.estimated_cost_usd:.4f} USD[/bold]"
    )

    console.print(table)


def display_cards_preview(cards: list, limit: int = 5) -> None:
    """Display a preview of cards."""
    num_shown = min(limit, len(cards))
    console.print(f"\n[bold]Sample Cards (showing {num_shown} of {len(cards)}):[/bold]\n")

    for i, card in enumerate(cards[:limit]):
        score = card.compute_score()
        status_icon = "[green]O[/green]" if card.status == CardStatus.INCLUDED else "[red]X[/red]"

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
@click.option("--images", "-i", is_flag=True, help="Include image information")
def info(epub_path: str, images: bool):
    """Show information about an EPUB file."""
    console.print(f"\n[bold]Parsing:[/bold] {epub_path}\n")

    with console.status("Parsing EPUB..."):
        book = parse_epub(epub_path, extract_images=images)

    display_book_info(book, include_images=images)

    # Show cost estimates for different densities
    console.print("\n[bold]Cost estimates by density:[/bold]")
    estimator = CostEstimator()
    for density in [Density.LIGHT, Density.MEDIUM, Density.THOROUGH]:
        estimate = estimator.estimate_book(book, density)
        console.print(f"  {density.value:10s}: ~${estimate.estimated_cost_usd:.4f} USD")


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
    "--chapter-density",
    type=str,
    multiple=True,
    help="Per-chapter density override (e.g., '1:thorough' or '3-5:light')",
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
@click.option(
    "--resume", "-r",
    is_flag=True,
    help="Resume from checkpoint if available",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Test workflow without making API calls",
)
@click.option(
    "--dedupe/--no-dedupe",
    default=True,
    help="Check for duplicate cards before export (default: yes)",
)
@click.option(
    "--reverse",
    is_flag=True,
    help="Generate reverse (Answer->Question) cards for Q&A",
)
@click.option(
    "--images",
    is_flag=True,
    help="Extract and embed images from EPUB",
)
@click.option(
    "--subdecks",
    is_flag=True,
    help="Create per-chapter subdecks",
)
@click.option(
    "--parent-deck",
    type=str,
    help="Nest deck under a parent deck name",
)
def generate(
    epub_path: str,
    output: Optional[str],
    density: str,
    chapters: Optional[str],
    chapter_density: tuple,
    auto: bool,
    threshold: Optional[float],
    resume: bool,
    dry_run: bool,
    dedupe: bool,
    reverse: bool,
    images: bool,
    subdecks: bool,
    parent_deck: Optional[str],
):
    """Generate Anki deck from an EPUB file."""
    density_enum = Density(density)

    # Parse EPUB
    console.print(f"\n[bold]Parsing:[/bold] {epub_path}\n")
    with console.status("Parsing EPUB..."):
        book = parse_epub(epub_path, extract_images=images)

    display_book_info(book, include_images=images)

    # Set up deck config
    deck_config = DeckConfig(
        create_subdecks=subdecks,
        parent_deck=parent_deck,
        include_reverse=reverse,
        extract_images=images,
    )

    # Set up output directory
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in book.title)
    if output:
        output_dir = Path(output)
    else:
        output_dir = Path("output") / safe_title
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse per-chapter density settings
    chapter_densities: dict[int, Density] = {}
    for cd in chapter_density:
        try:
            parts = cd.split(":")
            if len(parts) != 2:
                console.print(f"[yellow]Invalid chapter-density format: {cd}[/yellow]")
                continue

            chapter_spec, density_value = parts
            density_value = Density(density_value.lower())

            # Parse chapter spec (single number or range)
            if "-" in chapter_spec:
                start, end = map(int, chapter_spec.split("-"))
                for i in range(start - 1, end):  # Convert to 0-indexed
                    chapter_densities[i] = density_value
            else:
                chapter_densities[int(chapter_spec) - 1] = density_value
        except (ValueError, KeyError) as e:
            console.print(f"[yellow]Error parsing chapter-density '{cd}': {e}[/yellow]")

    # Check for checkpoint
    checkpoint_manager = CheckpointManager(output_dir)
    all_chapter_cards: list[ChapterCards] = []
    processed_indices: set[int] = set()

    if resume and checkpoint_manager.exists():
        checkpoint = checkpoint_manager.load()
        if checkpoint and checkpoint.book_title == book.title:
            console.print("\n[bold green]Resuming from checkpoint[/bold green]")
            summary = checkpoint_manager.get_resume_summary(checkpoint)
            processed = summary['chapters_processed']
            total = summary['chapters_total']
            console.print(f"  Chapters processed: {processed}/{total}")
            console.print(f"  Cards generated: {summary['total_cards_generated']}")

            # Restore chapter cards
            for chapter in book.chapters:
                chapter_cards = checkpoint_manager.restore_chapter_cards(checkpoint, chapter)
                if chapter_cards:
                    all_chapter_cards.append(chapter_cards)
                    processed_indices.add(chapter.index)

            density_enum = checkpoint.density
            console.print(f"  Density: {density_enum.value}")
        else:
            console.print(
                "[yellow]Checkpoint found but for different book, starting fresh[/yellow]"
            )

    # Parse chapter selection
    chapter_indices = None
    if chapters:
        try:
            chapter_indices = parse_chapter_selection(chapters, len(book.chapters))
            console.print(f"\n[bold]Processing chapters:[/bold] {[i + 1 for i in chapter_indices]}")
        except ChapterSelectionError as e:
            console.print(f"[red]Error:[/red] {e}")
            return

    # Determine which chapters to process
    chapters_to_process = book.chapters
    if chapter_indices:
        chapters_to_process = [ch for ch in book.chapters if ch.index in chapter_indices]

    # Remove already processed chapters
    chapters_to_process = [ch for ch in chapters_to_process if ch.index not in processed_indices]

    if not chapters_to_process and not all_chapter_cards:
        console.print("[yellow]No chapters to process.[/yellow]")
        return

    if chapters_to_process:
        # Show cost estimate
        chapter_indices_to_process = [ch.index for ch in chapters_to_process]
        console.print()
        display_cost_estimate(book, density_enum, chapter_indices_to_process)

        if dry_run:
            console.print("\n[bold yellow]DRY RUN MODE[/bold yellow] - No API calls will be made")

        # Confirm before proceeding
        if not auto:
            if not Confirm.ask("\nProceed with card generation?"):
                console.print("[yellow]Aborted.[/yellow]")
                return

        # Initialize components
        if dry_run:
            generator = None
        else:
            generator = CardGenerator()
        ranker = CardRanker()

        # Create checkpoint if not resuming
        if not checkpoint_manager.exists():
            checkpoint = checkpoint_manager.create_checkpoint(
                epub_path=epub_path,
                book_title=book.title,
                book_author=book.author,
                total_chapters=len(book.chapters),
                density=density_enum,
            )
            checkpoint_manager.save(checkpoint)
        else:
            checkpoint = checkpoint_manager.load()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating cards...", total=len(chapters_to_process))

            for chapter in chapters_to_process:
                progress.update(task, description=f"Processing: {chapter.title[:40]}...")

                # Determine density for this chapter
                chapter_density_enum = chapter_densities.get(chapter.index, density_enum)

                # Generate cards
                if dry_run:
                    # Create mock cards for dry run
                    import uuid

                    from .models import Card, CardFormat, CardType

                    num_cards = max(1, chapter.word_count // 500)
                    mock_cards = []
                    for i in range(num_cards):
                        card = Card(
                            id=str(uuid.uuid4())[:8],
                            format=CardFormat.QA,
                            card_type=CardType.CONCEPT,
                            question=f"[DRY RUN] Sample question {i+1} from {chapter.title}?",
                            answer=f"[DRY RUN] Sample answer {i+1}",
                            importance=5 + (i % 5),
                            difficulty=3 + (i % 5),
                            source_chapter=chapter.title,
                            source_chapter_index=chapter.index,
                            status=CardStatus.INCLUDED,
                            tags=[f"chapter::{chapter.index + 1}", "dry_run"],
                        )
                        mock_cards.append(card)
                    chapter_cards = ChapterCards(
                        chapter=chapter,
                        cards=mock_cards,
                        density_used=chapter_density_enum,
                    )
                else:
                    chapter_cards = generator.generate_for_chapter(
                        book, chapter, chapter_density_enum
                    )

                # Rank cards
                ranker.rank_chapter(chapter_cards)

                # Apply threshold
                if auto or threshold:
                    # Auto mode: use provided threshold or density-based default
                    if threshold:
                        ranker.apply_custom_threshold(chapter_cards, threshold)
                    else:
                        ranker.apply_density_threshold(chapter_cards, chapter_density_enum)
                else:
                    # Interactive mode: ask user
                    progress.stop()
                    console.print(f"\n[bold]Chapter {chapter.index + 1}: {chapter.title}[/bold]")
                    user_threshold = interactive_threshold_selection(chapter_cards, ranker)

                    if user_threshold == -1:
                        ranker.apply_density_threshold(chapter_cards, chapter_density_enum)
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

                # Save checkpoint after each chapter
                checkpoint_manager.add_chapter(checkpoint, chapter_cards)

                progress.advance(task)

    # Summary
    total_cards = sum(len(cc.cards) for cc in all_chapter_cards)
    included_cards = sum(len(cc.included_cards) for cc in all_chapter_cards)
    excluded_cards = sum(len(cc.excluded_cards) for cc in all_chapter_cards)

    console.print("\n[bold]Generation Complete![/bold]")
    console.print(f"  Total cards generated: {total_cards}")
    console.print(f"  [green]Included: {included_cards}[/green]")
    console.print(f"  [red]Excluded: {excluded_cards}[/red]")

    # Check for duplicates
    if dedupe and len(all_chapter_cards) > 1:
        console.print("\n[bold]Checking for duplicates...[/bold]")
        deduplicator = CardDeduplicator()
        all_cards = []
        for cc in all_chapter_cards:
            all_cards.extend(cc.cards)

        result = deduplicator.find_duplicates(all_cards, cross_chapter=True)
        if result.duplicates_found > 0:
            console.print(f"  Found {result.duplicates_found} duplicate cards")
            console.print(f"    Exact matches: {result.exact_duplicates}")
            console.print(f"    Similar cards: {result.similar_duplicates}")

            if auto or Confirm.ask("Remove duplicates (keep highest scoring)?"):
                removed = deduplicator.mark_duplicates_excluded(result, "highest_score")
                console.print(f"  [green]Marked {removed} duplicates as excluded[/green]")
                # Update counts
                included_cards = sum(len(cc.included_cards) for cc in all_chapter_cards)
                excluded_cards = sum(len(cc.excluded_cards) for cc in all_chapter_cards)
        else:
            console.print("  [green]No duplicates found[/green]")

    # Export to JSON
    console.print(f"\n[bold]Saving to:[/bold] {output_dir}")
    export_cards_to_json(all_chapter_cards, output_dir, book.title)

    # Export to Anki
    deck_name = f"{book.title} - {book.author}"
    exporter = AnkiExporter(deck_name, config=deck_config)

    for chapter_cards in all_chapter_cards:
        exporter.add_chapter_cards(
            chapter_cards, include_excluded=False, generate_reverse=reverse
        )

    # Add images if extracted
    if images and book.images:
        temp_media_dir = output_dir / ".media"
        exporter.add_images(book.images, temp_media_dir)

    apkg_path = output_dir / f"{safe_title}.apkg"
    exporter.export(apkg_path)

    console.print(f"\n[green]O[/green] Anki deck exported: {apkg_path}")
    console.print(
        f"[green]O[/green] JSON backup saved to: {output_dir}/included/ and {output_dir}/excluded/"
    )
    console.print(f"[green]O[/green] Final count: {included_cards} cards included")

    if reverse:
        console.print("[green]O[/green] Reverse cards: enabled")

    if subdecks:
        console.print("[green]O[/green] Chapter subdecks: created")

    if parent_deck:
        console.print(f"[green]O[/green] Parent deck: {parent_deck}")

    if dry_run:
        console.print("\n[yellow]Note: This was a dry run. No actual API calls were made.[/yellow]")


@cli.command()
@click.argument("epub_paths", nargs=-1, type=click.Path(exists=True), required=True)
@click.option("--output", "-o", type=click.Path(), required=True, help="Output .apkg path")
@click.option("--name", "-n", type=str, required=True, help="Parent deck name for all books")
@click.option("--subdecks", is_flag=True, help="Create per-chapter subdecks within each book")
@click.option("--reverse", is_flag=True, help="Generate reverse cards")
@click.option("--images", is_flag=True, help="Extract and embed images")
def combine(
    epub_paths: tuple,
    output: str,
    name: str,
    subdecks: bool,
    reverse: bool,
    images: bool,
):
    """Combine multiple EPUB files into a single Anki deck."""
    if not epub_paths:
        console.print("[red]Error: At least one EPUB file is required[/red]")
        return

    console.print(f"\n[bold]Combining {len(epub_paths)} books into deck:[/bold] {name}\n")

    # Set up deck config
    deck_config = DeckConfig(
        create_subdecks=subdecks,
        include_reverse=reverse,
        extract_images=images,
    )

    # Create multi-book exporter
    multi_exporter = MultiBookExporter(name, config=deck_config)

    # This is a placeholder - in real usage, users would need to generate cards first
    # or we would need to load from existing JSON exports
    console.print("[yellow]Note: This command combines existing generated decks.[/yellow]")
    console.print(
        "[yellow]Use the 'generate' command first to create cards for each book.[/yellow]"
    )

    # Look for existing output directories
    for epub_path in epub_paths:
        book = parse_epub(epub_path, extract_images=images)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in book.title)
        expected_dir = Path("output") / safe_title / "included"

        if expected_dir.exists():
            console.print(f"  Found cards for: {book.title}")

            # Load cards from JSON
            from .models import Card, Chapter
            chapter_cards_list = []

            for json_file in sorted(expected_dir.glob("*.json")):
                cards_data = json.loads(json_file.read_text())
                cards = [Card(**c) for c in cards_data]

                if cards:
                    # Create a minimal chapter for the ChapterCards
                    chapter_idx = int(json_file.stem.split("_")[1]) - 1
                    chapter = Chapter(
                        index=chapter_idx,
                        title=f"Chapter {chapter_idx + 1}",
                        content="",
                        word_count=0,
                    )
                    chapter_cards_list.append(ChapterCards(
                        chapter=chapter,
                        cards=cards,
                        density_used=Density.MEDIUM,
                    ))

            if chapter_cards_list:
                count = multi_exporter.add_book(
                    book, chapter_cards_list,
                    generate_reverse=reverse,
                )
                console.print(f"    Added {count} cards")
        else:
            console.print(f"  [yellow]No generated cards found for: {book.title}[/yellow]")
            console.print(f"    Expected: {expected_dir}")

    # Export combined deck
    output_path = Path(output)
    multi_exporter.export(output_path)

    summary = multi_exporter.get_summary()
    console.print(f"\n[green]O[/green] Combined deck exported: {output_path}")
    console.print(f"[green]O[/green] Books included: {summary['books']}")
    console.print(f"[green]O[/green] Parent deck: {summary['parent_deck']}")


@cli.command()
@click.argument("json_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output .apkg path")
@click.option("--name", "-n", type=str, help="Deck name")
@click.option("--reverse", is_flag=True, help="Generate reverse cards")
@click.option("--subdecks", is_flag=True, help="Create per-chapter subdecks")
@click.option("--parent-deck", type=str, help="Nest under a parent deck")
def export(
    json_dir: str,
    output: Optional[str],
    name: Optional[str],
    reverse: bool,
    subdecks: bool,
    parent_deck: Optional[str],
):
    """Export previously generated cards to Anki format."""
    json_dir_path = Path(json_dir)

    # Read metadata
    meta_path = json_dir_path / "metadata.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text())
        deck_name = name or metadata.get("book_title", "Imported Deck")
    else:
        deck_name = name or "Imported Deck"

    # Set up deck config
    deck_config = DeckConfig(
        create_subdecks=subdecks,
        parent_deck=parent_deck,
        include_reverse=reverse,
    )

    # Collect all included cards
    included_dir = json_dir_path / "included"
    if not included_dir.exists():
        console.print("[red]No included cards found![/red]")
        return

    exporter = AnkiExporter(deck_name, config=deck_config)
    card_count = 0

    for json_file in sorted(included_dir.glob("*.json")):
        cards_data = json.loads(json_file.read_text())
        for card_data in cards_data:
            from .models import Card

            card = Card(**card_data)
            exporter.add_card(card)
            card_count += 1

            # Generate reverse if requested
            if reverse and card.format.value == "qa":
                reverse_card = card.create_reverse()
                if reverse_card:
                    exporter.add_card(reverse_card)
                    card_count += 1

    if output:
        output_path = Path(output)
    else:
        output_path = json_dir_path / f"{deck_name}.apkg"

    exporter.export(output_path)
    console.print(f"[green]O[/green] Exported {card_count} cards to: {output_path}")


@cli.command()
@click.argument("output_dir", type=click.Path(exists=True))
def clear_checkpoint(output_dir: str):
    """Clear checkpoint to start fresh."""
    checkpoint_manager = CheckpointManager(Path(output_dir))
    if checkpoint_manager.delete():
        console.print("[green]O[/green] Checkpoint deleted")
    else:
        console.print("[yellow]No checkpoint found[/yellow]")


class ChapterSelectionError(ValueError):
    """Error parsing chapter selection string."""
    pass


def parse_chapter_selection(selection: str, total_chapters: int) -> list[int]:
    """
    Parse chapter selection string like '1,2,3' or '1-5' into indices.

    Args:
        selection: Comma-separated chapter numbers or ranges (e.g., "1,3,5" or "1-5")
        total_chapters: Total number of chapters in the book

    Returns:
        List of 0-indexed chapter indices

    Raises:
        ChapterSelectionError: If the selection string is invalid
    """
    if not selection or not selection.strip():
        raise ChapterSelectionError("Empty chapter selection")

    indices = set()

    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue

        try:
            if "-" in part:
                range_parts = part.split("-", 1)
                start_str, end_str = range_parts[0].strip(), range_parts[1].strip()

                if not start_str or not end_str:
                    raise ChapterSelectionError(
                        f"Invalid range format: '{part}'. Use format like '1-5'"
                    )

                start_idx = int(start_str) - 1  # Convert to 0-indexed
                end_idx = int(end_str)  # Inclusive end

                if start_idx < 0 or end_idx <= 0:
                    raise ChapterSelectionError(
                        f"Chapter numbers must be positive: '{part}'"
                    )
                if start_idx >= end_idx:
                    raise ChapterSelectionError(
                        f"Invalid range: start must be less than end in '{part}'"
                    )

                indices.update(range(start_idx, end_idx))
            else:
                chapter_num = int(part)
                if chapter_num <= 0:
                    raise ChapterSelectionError(
                        f"Chapter numbers must be positive: '{part}'"
                    )
                indices.add(chapter_num - 1)  # Convert to 0-indexed
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ChapterSelectionError(
                    f"Invalid chapter number: '{part}'. Use numbers like '1,2,3' or '1-5'"
                )
            raise

    # Filter valid indices
    valid_indices = sorted(i for i in indices if 0 <= i < total_chapters)

    if not valid_indices:
        raise ChapterSelectionError(
            f"No valid chapters selected. Book has {total_chapters} chapters (1-{total_chapters})"
        )

    return valid_indices


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
