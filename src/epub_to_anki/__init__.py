"""EPUB to Anki Deck Generator - Create high-quality flashcards from books using Claude."""

__version__ = "0.2.0"

from .agent import AGENT_TOOLS, EpubToAnkiAgent, get_agent_system_prompt
from .checkpoint import CheckpointManager, SessionCheckpoint
from .cost_estimator import CostEstimate, CostEstimator
from .deduplicator import CardDeduplicator, DeduplicationResult
from .exporter.anki_exporter import MultiBookExporter
from .models import (
    Book,
    Card,
    CardFormat,
    CardStatus,
    CardTemplate,
    CardType,
    CardVersion,
    Chapter,
    ChapterCards,
    ChapterDensityConfig,
    DeckConfig,
    Density,
    EpubImage,
)

__all__ = [
    # Agent
    "EpubToAnkiAgent",
    "AGENT_TOOLS",
    "get_agent_system_prompt",
    # Checkpoint
    "CheckpointManager",
    "SessionCheckpoint",
    # Cost estimation
    "CostEstimator",
    "CostEstimate",
    # Deduplication
    "CardDeduplicator",
    "DeduplicationResult",
    # Multi-book export
    "MultiBookExporter",
    # Models
    "Book",
    "Card",
    "CardFormat",
    "CardStatus",
    "CardTemplate",
    "CardType",
    "CardVersion",
    "Chapter",
    "ChapterCards",
    "ChapterDensityConfig",
    "DeckConfig",
    "Density",
    "EpubImage",
]
