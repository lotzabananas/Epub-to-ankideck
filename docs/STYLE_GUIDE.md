# Card Style Guide

This document defines the standards for generating high-quality Anki flashcards. These guidelines are embedded into the card generation prompts to ensure consistency.

---

## Core Principles

### 1. Atomicity
- **One fact per card** - Never combine multiple concepts
- If you need "and" in your answer, consider splitting into multiple cards
- Exception: Tightly coupled pairs (e.g., "cause and effect" as a single unit)

### 2. Active Recall
- Cards must require **retrieval**, not recognition
- The answer should not be guessable from the question structure
- Avoid yes/no questions - they're too easy and don't build strong memories

### 3. Clarity
- Questions should be unambiguous - only one correct answer possible
- Answers should stand alone without needing to see the question
- Write for your future confused self at 11pm

### 4. Brevity
- Answers: 1-15 words typical, up to 30 for lists/processes
- Questions: Direct and concise, no unnecessary preamble
- If the answer is a paragraph, the card is too complex

---

## Q&A Card Guidelines

### Question Starters (Preferred)
- **What** - definitions, concepts, facts
- **Why** - reasoning, causation, purpose
- **How** - processes, mechanisms, methods
- **When** - temporal facts, conditions
- **Who** - people, roles, attribution
- **Where** - locations, contexts

### Question Patterns

**Good:**
```
Q: What is neuroplasticity?
A: The brain's ability to reorganize itself by forming new neural connections throughout life
```

**Bad:**
```
Q: What is the definition of the term neuroplasticity as used in neuroscience?
A: Neuroplasticity is defined as the brain's ability to reorganize itself by forming new neural connections throughout life.
```

### Answer Guidelines
- Start with the core answer, add brief context only if necessary
- No need to repeat words from the question
- Use sentence fragments when appropriate - this isn't an essay

**Good:**
```
Q: What causes tides?
A: Gravitational pull of the Moon (and to a lesser extent, the Sun)
```

**Bad:**
```
Q: What causes tides?
A: Tides are caused by the gravitational pull of the Moon and to a lesser extent the Sun on Earth's oceans.
```

---

## Cloze Card Guidelines

### When to Use Cloze
- Terminology with specific names/terms
- Facts with numbers, dates, names
- Sequences and ordered lists
- Dense sentences where context aids recall

### What to Blank Out
- **Do blank:** Key terms, names, numbers, the "payload" of the sentence
- **Don't blank:** Articles, prepositions, filler words, obvious terms

**Good:**
```
The {{c1::mitochondria}} is often called the powerhouse of the cell because it produces {{c2::ATP}}.
```

**Bad:**
```
{{c1::The}} mitochondria {{c2::is}} often called the powerhouse of {{c3::the}} cell.
```

### Cloze Context Rules
- Surrounding text should make the blank unambiguous
- One primary blank per card (multi-cloze creates separate cards)
- The sentence should read naturally with the blank filled in

---

## Content Selection

### DO Make Cards For
- Core concepts and definitions
- Key facts that support understanding
- Relationships between ideas
- Processes and their steps
- Terminology essential to the subject
- Surprising or counterintuitive facts (these stick well)
- Examples that illuminate abstract concepts

### DON'T Make Cards For
- Author opinions or subjective claims
- Filler content and transitions
- Information you already know well
- Trivia disconnected from core concepts
- Highly context-dependent statements
- Speculation or uncertain claims
- Content that requires the full chapter to understand

---

## Difficulty & Importance Ranking

Cards are ranked 1-10 on two dimensions:

### Importance (How essential is this knowledge?)
- **9-10:** Core concept, everything else builds on this
- **7-8:** Key supporting fact, important for understanding
- **5-6:** Useful detail, enriches understanding
- **3-4:** Nice to know, but not critical
- **1-2:** Trivia, edge cases, minor details

### Difficulty (How hard is this to remember?)
- **9-10:** Abstract, counterintuitive, easily confused with similar concepts
- **7-8:** Requires connecting multiple ideas
- **5-6:** Moderate - straightforward but not obvious
- **3-4:** Relatively easy, some natural memorability
- **1-2:** Almost self-evident once understood

---

## Metadata & Tagging

### Hidden Fields (stored but not shown on card face)
- `source_chapter`: Chapter title
- `source_section`: Section/heading if available
- `page_estimate`: Approximate location in book
- `importance`: 1-10 ranking
- `difficulty`: 1-10 ranking

### Auto-generated Tags
- `chapter::01_introduction` (chapter number + slug)
- `type::concept` | `type::fact` | `type::process` | `type::term`
- `format::qa` | `format::cloze`

---

## Examples by Content Type

### Concept Definition
```
Q: What is opportunity cost?
A: The value of the next-best alternative you give up when making a choice
```

### Process/Sequence
```
Q: What are the three stages of memory formation?
A: Encoding → Storage → Retrieval
```

### Causal Relationship
```
Q: Why do prices rise during inflation?
A: More money chasing the same amount of goods reduces each unit's purchasing power
```

### Terminology (Cloze)
```
{{c1::Cognitive dissonance}} is the mental discomfort experienced when holding contradictory beliefs or values.
```

### Factual (Cloze)
```
The human brain contains approximately {{c1::86 billion}} neurons.
```

---

## Anti-Patterns to Avoid

### The "Enumerate" Trap
**Bad:** "List the 7 habits of highly effective people"
**Better:** Make 7 separate cards, or test recognition of whether something IS one of the habits

### The "Define X" Crutch
**Bad:** "Define photosynthesis"
**Better:** "What process do plants use to convert sunlight into energy?"

### The "True or False" Temptation
**Bad:** "True or false: The heart has four chambers"
**Better:** "How many chambers does the human heart have?" → "Four"

### The "Fill in the Blank" Overload
**Bad:** "{{c1::The}} {{c2::quick}} {{c3::brown}} {{c4::fox}}..."
**Better:** One meaningful blank per cloze note

---

## Quality Checklist

Before including a card, verify:
- [ ] Single atomic fact
- [ ] Clear, unambiguous question
- [ ] Concise answer (typically <15 words)
- [ ] Not guessable from question structure
- [ ] Not trivial or already well-known
- [ ] Connected to broader understanding (not orphan trivia)
- [ ] Appropriate format (Q&A vs Cloze) for content type
