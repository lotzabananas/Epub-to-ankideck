"""EPUB to Anki Deck Generator - Create high-quality flashcards from books using Claude."""

__version__ = "0.1.0"

from .agent import EpubToAnkiAgent, AGENT_TOOLS, get_agent_system_prompt
from .checkpoint import CheckpointManager, SessionCheckpoint
from .cost_estimator import CostEstimator, CostEstimate
from .deduplicator import CardDeduplicator, DeduplicationResult
from .models import (
    Book,
    Card,
    CardFormat,
    CardStatus,
    CardType,
    Chapter,
    ChapterCards,
    Density,
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
    # Models
    "Book",
    "Card",
    "CardFormat",
    "CardStatus",
    "CardType",
    "Chapter",
    "ChapterCards",
    "Density",
]
