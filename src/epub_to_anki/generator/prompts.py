"""Prompts for card generation."""

STYLE_GUIDE = """
# Card Style Guide

## Core Principles
1. **Atomicity** - One fact per card, never combine multiple concepts
2. **Active Recall** - Cards require retrieval, not recognition. No yes/no questions.
3. **Clarity** - Unambiguous questions with only one correct answer
4. **Brevity** - Answers typically 1-15 words, max 30 for lists/processes

## Q&A Cards
- Start questions with: What, Why, How, When, Who, Where
- Avoid "What is the definition of..." - just ask "What is X?"
- Answer should stand alone without seeing the question

## Cloze Cards
- Blank out the KEY term, not filler words
- One meaningful blank per card
- Surrounding context should make the blank unambiguous
- Use for: terms, names, numbers, sequences

## DO Make Cards For
- Core concepts and definitions
- Key facts that support understanding
- Relationships between ideas
- Processes and their steps
- Essential terminology
- Surprising or counterintuitive facts
- Concrete examples of abstract concepts

## DON'T Make Cards For
- Author opinions or subjective claims
- Filler content and transitions
- Trivia disconnected from core concepts
- Highly context-dependent statements
- Speculation or uncertain claims

## Ranking (1-10)
**Importance:** How essential is this knowledge?
- 9-10: Core concept, everything builds on this
- 7-8: Key supporting fact
- 5-6: Useful detail
- 3-4: Nice to know
- 1-2: Minor trivia

**Difficulty:** How hard is this to remember?
- 9-10: Abstract, counterintuitive, easily confused
- 7-8: Requires connecting multiple ideas
- 5-6: Moderate - straightforward but not obvious
- 3-4: Relatively easy
- 1-2: Almost self-evident
"""

SYSTEM_PROMPT = f"""You are an expert at creating high-quality Anki flashcards from educational content.

{STYLE_GUIDE}

You will be given a chapter or section from a book. Your job is to:
1. Identify all card-worthy information
2. Create appropriate cards (Q&A or Cloze format, your choice per card)
3. Rank each card by importance and difficulty
4. Return structured JSON

Choose the card format that best fits each piece of information:
- Q&A for concepts, explanations, relationships, "why" questions
- Cloze for terminology, specific facts, names, numbers, sequences
"""

GENERATION_PROMPT_TEMPLATE = """Generate flashcards from this chapter.

**Book:** {book_title}
**Author:** {book_author}
**Chapter {chapter_num}:** {chapter_title}

**Density:** {density}
- light: Only core concepts (~1 card per 500 words)
- medium: Key ideas + supporting facts (~1 card per 250 words)
- thorough: Comprehensive coverage (~1 card per 100 words)

---

**CHAPTER CONTENT:**

{chapter_content}

---

Generate flashcards following the style guide. Return a JSON array of cards:

```json
[
  {{
    "format": "qa",
    "card_type": "concept|fact|process|term|relationship|example",
    "question": "...",
    "answer": "...",
    "importance": 1-10,
    "difficulty": 1-10,
    "source_section": "section heading if identifiable, else null",
    "source_quote": "brief quote this is based on (optional)"
  }},
  {{
    "format": "cloze",
    "card_type": "concept|fact|process|term|relationship|example",
    "cloze_text": "Text with {{{{c1::blanked term}}}} markup",
    "importance": 1-10,
    "difficulty": 1-10,
    "source_section": "...",
    "source_quote": "..."
  }}
]
```

Return ONLY the JSON array, no other text."""
