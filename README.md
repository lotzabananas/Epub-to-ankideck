# EPUB to Anki

Create high-quality Anki flashcards from EPUB books using Claude Code.

**No API costs** - Uses your Claude Pro plan through Claude Code.

## Quick Start

1. **Open Claude Code in this folder**

2. **Tell Claude Code to process your book:**
   ```
   Make flashcards from ~/Downloads/mybook.epub
   ```

3. **Import the generated `.apkg` file into Anki**

That's it! Claude Code handles everything.

## How It Works

1. **EPUB Parser** - Extracts text from your ebook
2. **Claude Code** - Reads chapters and generates flashcards (using your Pro plan)
3. **Anki Exporter** - Creates `.apkg` files you can import into Anki

## Features

- **Q&A and Cloze cards** - Claude chooses the best format for each fact
- **Smart ranking** - Cards scored by importance and difficulty
- **Deduplication** - Removes similar/duplicate cards
- **Checkpoint/Resume** - For long books, resume where you left off

## Installation

```bash
# Clone and set up
git clone https://github.com/lotzabananas/Epub-to-ankideck.git
cd Epub-to-ankideck
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Usage Examples

**Basic:**
```
Make flashcards from /path/to/book.epub
```

**With options:**
```
Process book.epub with thorough density (more cards)
```

**Auto mode (no questions):**
```
Auto-generate flashcards from book.epub
```

## Output

Cards are exported to `output/<book-name>/`:
- `<book-name>.apkg` - Import this into Anki
- `cards.json` - JSON backup of all cards

## Project Structure

```
src/epub_to_anki/
├── parser/          # EPUB text extraction
├── exporter/        # Anki .apkg generation
├── ranker/          # Card scoring and filtering
├── deduplicator.py  # Duplicate detection
├── checkpoint.py    # Resume support
└── models.py        # Data structures
```

## License

MIT
