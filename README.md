# EPUB to Anki Deck Generator

Generate high-quality Anki flashcard decks from EPUB books using Claude AI.

## Features

- **Smart Card Generation**: Uses Claude to identify card-worthy content and create appropriate Q&A or Cloze cards
- **Two-Pass Ranking**: Generates all potential cards, then ranks by importance/difficulty for filtering
- **Chapter-by-Chapter Processing**: Review one chapter at a time, adjust thresholds per chapter
- **Flexible Density Settings**: Light (core concepts), Medium (balanced), Thorough (comprehensive)
- **Hidden Metadata**: Source chapter/section stored but not shown on card face
- **Preserves Excluded Cards**: Nothing thrown away - adjust thresholds later without re-processing

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/epub-to-ankideck.git
cd epub-to-ankideck

# Install dependencies
pip install -e .
```

## Usage

### Command Line

```bash
# Show book information
epub2anki info mybook.epub

# Generate deck (interactive mode)
epub2anki generate mybook.epub

# Generate with specific settings
epub2anki generate mybook.epub --density thorough --chapters 1-3

# Auto mode (no manual review)
epub2anki generate mybook.epub --auto --threshold 6
```

### As a Library

```python
from epub_to_anki.parser import parse_epub
from epub_to_anki.generator import CardGenerator
from epub_to_anki.ranker import CardRanker
from epub_to_anki.exporter import AnkiExporter
from epub_to_anki.models import Density

# Parse book
book = parse_epub("mybook.epub")

# Generate cards
generator = CardGenerator()
chapter_cards = generator.generate_for_chapter(book, book.chapters[0], Density.MEDIUM)

# Rank and filter
ranker = CardRanker()
ranker.rank_chapter(chapter_cards)
ranker.apply_custom_threshold(chapter_cards, threshold=6.0)

# Export
exporter = AnkiExporter(f"{book.title} - {book.author}")
exporter.add_chapter_cards(chapter_cards)
exporter.export("output/mybook.apkg")
```

### With Claude Code Agent

The package includes an agent interface for use with Claude Code SDK:

```python
from epub_to_anki.agent import EpubToAnkiAgent

agent = EpubToAnkiAgent()
agent.load_book("mybook.epub")
agent.set_density("medium")
agent.generate_chapter(0)
agent.apply_threshold(0, 6.0)
agent.export_deck()
```

## Card Generation

### Density Levels

| Density | Cards per Page | Best For |
|---------|---------------|----------|
| Light | ~0.3-0.5 | Quick overview, core concepts only |
| Medium | ~1 | Balanced learning, most users |
| Thorough | ~2-3 | Deep study, comprehensive retention |

### Card Scoring

Cards are scored 1-10 on two dimensions:
- **Importance**: How essential is this knowledge? (weighted 2x)
- **Difficulty**: How hard is this to remember?

Score = (Importance × 2 + Difficulty) / 3

### Card Formats

**Q&A Cards** - For concepts, explanations, relationships:
```
Q: What is neuroplasticity?
A: The brain's ability to reorganize itself by forming new neural connections
```

**Cloze Cards** - For terminology, facts, sequences:
```
The {{c1::mitochondria}} is the powerhouse of the cell.
```

## Output Structure

```
output/
├── Book_Title/
│   ├── included/
│   │   ├── chapter_01.json
│   │   └── chapter_02.json
│   ├── excluded/
│   │   ├── chapter_01.json
│   │   └── chapter_02.json
│   ├── metadata.json
│   └── Book_Title.apkg
```

## Style Guide

See [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md) for detailed card quality guidelines.

## Requirements

- Python 3.10+
- Anthropic API key (set `ANTHROPIC_API_KEY` environment variable)

## License

MIT
