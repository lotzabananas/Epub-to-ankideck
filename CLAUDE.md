# Claude Code Instructions for EPUB to Anki

When the user asks to generate flashcards from an EPUB file, follow this workflow:

## Quick Start
If the user says something like "make flashcards from book.epub" or "process my-book.epub":

1. **Parse the EPUB** using the installed library:
```python
source venv/bin/activate && python -c "
from epub_to_anki.parser import parse_epub
from epub_to_anki.parser.epub_parser import get_book_summary
book = parse_epub('/path/to/book.epub')
print(get_book_summary(book))
"
```

2. **Read each chapter** and generate flashcards in JSON format
3. **Export to Anki** using the workflow script

## Flashcard Generation Guidelines

When generating flashcards from chapter content:

### Card Formats
- **Q&A cards**: For concepts, explanations, relationships
- **Cloze cards**: For terminology, facts, names, numbers (use `{{c1::term}}` syntax)

### JSON Format for Cards
```json
{
  "format": "qa",
  "card_type": "concept",
  "question": "What is X?",
  "answer": "X is...",
  "importance": 7,
  "difficulty": 5,
  "source_chapter": "Chapter Title",
  "source_chapter_index": 0
}
```

### Scoring (1-10)
- **Importance**: How essential? (9-10 = core concept, 5-6 = useful detail, 1-2 = trivia)
- **Difficulty**: How hard to remember? (9-10 = abstract/counterintuitive, 5-6 = moderate)

### DO make cards for:
- Core concepts and definitions
- Key facts and relationships
- Processes and steps
- Essential terminology

### DON'T make cards for:
- Author opinions
- Filler content
- Highly context-dependent statements

## Workflow Script Commands

```bash
# Parse an EPUB
python claude_code_workflow.py parse /path/to/book.epub

# Show a chapter (for reading)
python claude_code_workflow.py chapter 1

# Add generated cards
python claude_code_workflow.py add '[{"format":"qa","question":"...","answer":"...","importance":7,"difficulty":5,"source_chapter":"Ch1","source_chapter_index":0}]'

# Export to Anki
python claude_code_workflow.py export

# Check status
python claude_code_workflow.py status
```

## Interactive vs Auto Mode

**Interactive**: Ask the user after each chapter if they want to review/adjust cards
**Auto**: Generate all cards, apply threshold, export without asking
