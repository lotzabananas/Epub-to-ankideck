"""Export cards to Anki .apkg format."""

import hashlib
import json
import re
from pathlib import Path
from typing import Optional

import genanki

from ..models import Card, CardFormat, CardStatus, ChapterCards, DeckMetadata

# CSS styling for cards
CARD_CSS = """
.card {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 18px;
    text-align: left;
    color: #1a1a1a;
    background-color: #ffffff;
    padding: 20px;
    line-height: 1.5;
}

.question {
    font-size: 20px;
    margin-bottom: 20px;
}

.answer {
    border-top: 1px solid #e0e0e0;
    padding-top: 20px;
}

.cloze {
    font-weight: bold;
    color: #0066cc;
}

.metadata {
    font-size: 12px;
    color: #888;
    margin-top: 30px;
    padding-top: 15px;
    border-top: 1px solid #f0f0f0;
}

.source-chapter {
    font-style: italic;
}

.night_mode .card {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

.night_mode .cloze {
    color: #66b3ff;
}

.night_mode .metadata {
    color: #666;
    border-top-color: #333;
}

.night_mode .answer {
    border-top-color: #333;
}
"""

# Q&A Card template
QA_FRONT = """
<div class="question">{{Question}}</div>
"""

QA_BACK = """
<div class="question">{{Question}}</div>
<hr id="answer">
<div class="answer">{{Answer}}</div>

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
</div>
"""

# Cloze card template
CLOZE_FRONT = """
<div class="cloze-text">{{cloze:Text}}</div>
"""

CLOZE_BACK = """
<div class="cloze-text">{{cloze:Text}}</div>

<div class="metadata">
    <span class="source-chapter">{{SourceChapter}}</span>
    {{#SourceSection}} &middot; {{SourceSection}}{{/SourceSection}}
</div>
"""


def generate_model_id(name: str) -> int:
    """Generate a stable model ID from a name."""
    hash_bytes = hashlib.md5(name.encode()).digest()
    return int.from_bytes(hash_bytes[:4], byteorder="big")


def generate_deck_id(name: str) -> int:
    """Generate a stable deck ID from a name."""
    hash_bytes = hashlib.md5(f"deck_{name}".encode()).digest()
    return int.from_bytes(hash_bytes[:4], byteorder="big")


def create_qa_model(deck_name: str) -> genanki.Model:
    """Create the Q&A note model."""
    model_name = f"{deck_name} - Q&A"
    return genanki.Model(
        generate_model_id(model_name),
        model_name,
        fields=[
            {"name": "Question"},
            {"name": "Answer"},
            {"name": "SourceChapter"},
            {"name": "SourceSection"},
            {"name": "Importance"},
            {"name": "Difficulty"},
            {"name": "CardID"},
        ],
        templates=[
            {
                "name": "Card 1",
                "qfmt": QA_FRONT,
                "afmt": QA_BACK,
            },
        ],
        css=CARD_CSS,
    )


def create_cloze_model(deck_name: str) -> genanki.Model:
    """Create the Cloze note model."""
    model_name = f"{deck_name} - Cloze"
    return genanki.Model(
        generate_model_id(model_name),
        model_name,
        model_type=genanki.Model.CLOZE,
        fields=[
            {"name": "Text"},
            {"name": "SourceChapter"},
            {"name": "SourceSection"},
            {"name": "Importance"},
            {"name": "Difficulty"},
            {"name": "CardID"},
        ],
        templates=[
            {
                "name": "Cloze",
                "qfmt": CLOZE_FRONT,
                "afmt": CLOZE_BACK,
            },
        ],
        css=CARD_CSS,
    )


class AnkiExporter:
    """Export cards to Anki .apkg format."""

    def __init__(self, deck_name: str):
        """
        Initialize the exporter.

        Args:
            deck_name: Name for the Anki deck
        """
        self.deck_name = deck_name
        self.deck = genanki.Deck(generate_deck_id(deck_name), deck_name)
        self.qa_model = create_qa_model(deck_name)
        self.cloze_model = create_cloze_model(deck_name)

    def _card_to_qa_note(self, card: Card) -> genanki.Note:
        """Convert a Q&A card to an Anki note."""
        return genanki.Note(
            model=self.qa_model,
            fields=[
                card.question or "",
                card.answer or "",
                card.source_chapter,
                card.source_section or "",
                str(card.importance),
                str(card.difficulty),
                card.id,
            ],
            tags=card.tags,
        )

    def _card_to_cloze_note(self, card: Card) -> genanki.Note:
        """Convert a Cloze card to an Anki note."""
        return genanki.Note(
            model=self.cloze_model,
            fields=[
                card.cloze_text or "",
                card.source_chapter,
                card.source_section or "",
                str(card.importance),
                str(card.difficulty),
                card.id,
            ],
            tags=card.tags,
        )

    def add_card(self, card: Card) -> None:
        """Add a single card to the deck."""
        if card.format == CardFormat.QA:
            note = self._card_to_qa_note(card)
        else:
            note = self._card_to_cloze_note(card)
        self.deck.add_note(note)

    def add_chapter_cards(
        self,
        chapter_cards: ChapterCards,
        include_excluded: bool = False,
    ) -> int:
        """
        Add all cards from a chapter to the deck.

        Args:
            chapter_cards: ChapterCards to add
            include_excluded: If True, also add excluded cards (with 'excluded' tag)

        Returns:
            Number of cards added
        """
        count = 0
        for card in chapter_cards.cards:
            if card.status == CardStatus.INCLUDED:
                self.add_card(card)
                count += 1
            elif include_excluded:
                # Add excluded tag before adding
                card.tags.append("status::excluded")
                self.add_card(card)
                count += 1
        return count

    def export(self, output_path: str | Path) -> Path:
        """
        Export the deck to an .apkg file.

        Args:
            output_path: Path for the output file

        Returns:
            Path to the created file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        genanki.Package(self.deck).write_to_file(str(output_path))
        return output_path


def export_cards_to_json(
    chapter_cards_list: list[ChapterCards],
    output_dir: Path,
    book_title: str,
) -> dict[str, Path]:
    """
    Export cards to JSON files for persistence.

    Creates:
    - included/ directory with included cards per chapter
    - excluded/ directory with excluded cards per chapter
    - metadata.json with processing info

    Args:
        chapter_cards_list: List of ChapterCards to export
        output_dir: Base output directory
        book_title: Title of the book

    Returns:
        Dict mapping file type to paths created
    """
    output_dir = Path(output_dir)
    included_dir = output_dir / "included"
    excluded_dir = output_dir / "excluded"

    included_dir.mkdir(parents=True, exist_ok=True)
    excluded_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    total_included = 0
    total_excluded = 0

    for chapter_cards in chapter_cards_list:
        chapter_idx = chapter_cards.chapter.index
        filename = f"chapter_{chapter_idx + 1:02d}.json"

        # Export included cards
        included = [c.model_dump() for c in chapter_cards.included_cards]
        if included:
            path = included_dir / filename
            path.write_text(json.dumps(included, indent=2))
            paths[f"included_{chapter_idx}"] = path
        total_included += len(included)

        # Export excluded cards
        excluded = [c.model_dump() for c in chapter_cards.excluded_cards]
        if excluded:
            path = excluded_dir / filename
            path.write_text(json.dumps(excluded, indent=2))
            paths[f"excluded_{chapter_idx}"] = path
        total_excluded += len(excluded)

    # Create metadata
    metadata = {
        "book_title": book_title,
        "total_cards": total_included + total_excluded,
        "included_cards": total_included,
        "excluded_cards": total_excluded,
        "chapters_processed": len(chapter_cards_list),
    }

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))
    paths["metadata"] = meta_path

    return paths
