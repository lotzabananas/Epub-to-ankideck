"""EPUB to Anki - Create flashcards from books using Claude Code."""

__version__ = "0.3.0"

from .checkpoint import CheckpointManager, SessionCheckpoint
from .deduplicator import CardDeduplicator, DeduplicationResult
from .exporter.anki_exporter import AnkiExporter
from .models import (
    Book,
    Card,
    CardFormat,
    CardStatus,
    CardType,
    Chapter,
    ChapterCards,
    DeckConfig,
    Density,
)
from .parser import parse_epub
from .ranker import CardRanker

__all__ = [
    # Parser
    "parse_epub",
    # Exporter
    "AnkiExporter",
    # Ranker
    "CardRanker",
    # Checkpoint
    "CheckpointManager",
    "SessionCheckpoint",
    # Deduplication
    "CardDeduplicator",
    "DeduplicationResult",
    # Models
    "Book",
    "Card",
    "CardFormat",
    "CardStatus",
    "CardType",
    "Chapter",
    "ChapterCards",
    "DeckConfig",
    "Density",
]
