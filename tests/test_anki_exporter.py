"""Tests for Anki exporter features."""

import tempfile
from pathlib import Path

import pytest

from epub_to_anki.exporter.anki_exporter import (
    AnkiExporter,
    MultiBookExporter,
    create_qa_model,
    create_cloze_model,
    generate_deck_id,
    generate_model_id,
)
from epub_to_anki.models import (
    Book,
    Card,
    CardFormat,
    CardStatus,
    CardType,
    CardTemplate,
    Chapter,
    ChapterCards,
    DeckConfig,
    Density,
)


def create_test_card(
    id: str,
    format: CardFormat = CardFormat.QA,
    question: str = "Test question?",
    answer: str = "Test answer",
    cloze_text: str = None,
    image_id: str = None,
) -> Card:
    """Helper to create test cards."""
    return Card(
        id=id,
        format=format,
        card_type=CardType.CONCEPT,
        question=question,
        answer=answer,
        cloze_text=cloze_text,
        importance=5,
        difficulty=5,
        source_chapter="Test Chapter",
        source_chapter_index=0,
        status=CardStatus.INCLUDED,
        image_id=image_id,
    )


def create_test_chapter_cards() -> ChapterCards:
    """Create a ChapterCards for testing."""
    chapter = Chapter(
        index=0,
        title="Test Chapter",
        content="Test content",
        word_count=100,
    )
    cards = [
        create_test_card("1", question="Q1?", answer="A1"),
        create_test_card("2", question="Q2?", answer="A2"),
    ]
    return ChapterCards(chapter=chapter, cards=cards, density_used=Density.MEDIUM)


class TestIdGeneration:
    """Test stable ID generation."""

    def test_generate_model_id_stable(self):
        """Same name generates same ID."""
        id1 = generate_model_id("Test Model")
        id2 = generate_model_id("Test Model")
        assert id1 == id2

    def test_generate_model_id_unique(self):
        """Different names generate different IDs."""
        id1 = generate_model_id("Model A")
        id2 = generate_model_id("Model B")
        assert id1 != id2

    def test_generate_deck_id_stable(self):
        """Same name generates same deck ID."""
        id1 = generate_deck_id("Test Deck")
        id2 = generate_deck_id("Test Deck")
        assert id1 == id2


class TestQAModel:
    """Test Q&A model creation."""

    def test_basic_model(self):
        """Test basic Q&A model."""
        model = create_qa_model("Test")
        assert model.name == "Test - Q&A"
        assert len(model.templates) == 1
        assert model.templates[0]["name"] == "Card 1"

    def test_model_with_reverse(self):
        """Test Q&A model with reverse cards."""
        model = create_qa_model("Test", include_reverse=True)
        assert len(model.templates) == 2
        assert model.templates[0]["name"] == "Card 1"
        assert model.templates[1]["name"] == "Card 2 (Reverse)"

    def test_model_with_custom_template(self):
        """Test Q&A model with custom template."""
        template = CardTemplate(
            name="Custom",
            front_html="<div>{{Question}}</div>",
            back_html="<div>{{Answer}}</div>",
            css=".custom { color: red; }",
        )
        model = create_qa_model("Test", custom_template=template)
        assert template.front_html in model.templates[0]["qfmt"]
        assert ".custom" in model.css


class TestClozeModel:
    """Test Cloze model creation."""

    def test_basic_cloze_model(self):
        """Test basic Cloze model."""
        model = create_cloze_model("Test")
        assert model.name == "Test - Cloze"
        assert len(model.templates) == 1


class TestAnkiExporter:
    """Test AnkiExporter class."""

    def test_basic_export(self):
        """Test basic deck export."""
        exporter = AnkiExporter("Test Deck")
        cc = create_test_chapter_cards()
        exporter.add_chapter_cards(cc)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.apkg"
            result = exporter.export(output)
            assert result.exists()

    def test_parent_deck_config(self):
        """Test parent deck configuration."""
        config = DeckConfig(parent_deck="My Library")
        exporter = AnkiExporter("Book Title", config=config)
        assert exporter.deck_name == "My Library::Book Title"

    def test_chapter_subdecks(self):
        """Test chapter subdeck creation."""
        config = DeckConfig(use_chapter_subdecks=True)
        exporter = AnkiExporter("Test", config=config)

        chapter1 = Chapter(index=0, title="Chapter 1", content="", word_count=0)
        chapter2 = Chapter(index=1, title="Chapter 2", content="", word_count=0)

        deck1 = exporter._get_deck_for_chapter(0, "Chapter 1")
        deck2 = exporter._get_deck_for_chapter(1, "Chapter 2")

        assert len(exporter.subdecks) == 2
        assert "Ch1" in exporter.subdecks[0].name
        assert "Ch2" in exporter.subdecks[1].name

    def test_no_subdecks_without_config(self):
        """Test that subdecks are not created without config."""
        exporter = AnkiExporter("Test")
        deck = exporter._get_deck_for_chapter(0, "Chapter 1")
        assert len(exporter.subdecks) == 0
        assert deck == exporter.deck

    def test_add_image(self):
        """Test image addition."""
        exporter = AnkiExporter("Test")
        filename = exporter.add_image("img1", "test.png", b"fake image data")
        assert filename == "test.png"
        assert "test.png" in exporter.image_data

    def test_export_with_images(self):
        """Test export with images."""
        exporter = AnkiExporter("Test")
        exporter.add_image("img1", "test.png", b"PNG image data")

        cc = create_test_chapter_cards()
        exporter.add_chapter_cards(cc)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.apkg"
            result = exporter.export(output)
            assert result.exists()

    def test_reverse_cards_config(self):
        """Test reverse cards configuration."""
        config = DeckConfig(include_reverse_cards=True)
        exporter = AnkiExporter("Test", config=config)
        assert len(exporter.qa_model.templates) == 2

    def test_exclude_cards(self):
        """Test that excluded cards are not added by default."""
        exporter = AnkiExporter("Test")

        chapter = Chapter(index=0, title="Test", content="", word_count=0)
        cards = [
            create_test_card("1"),
            create_test_card("2"),
        ]
        cards[1].status = CardStatus.EXCLUDED

        cc = ChapterCards(chapter=chapter, cards=cards, density_used=Density.MEDIUM)
        count = exporter.add_chapter_cards(cc, include_excluded=False)

        assert count == 1

    def test_include_excluded_with_tag(self):
        """Test including excluded cards with tag."""
        exporter = AnkiExporter("Test")

        chapter = Chapter(index=0, title="Test", content="", word_count=0)
        cards = [create_test_card("1")]
        cards[0].status = CardStatus.EXCLUDED

        cc = ChapterCards(chapter=chapter, cards=cards, density_used=Density.MEDIUM)
        count = exporter.add_chapter_cards(cc, include_excluded=True)

        assert count == 1


class TestMultiBookExporter:
    """Test MultiBookExporter class."""

    def test_create_multi_book_exporter(self):
        """Test basic multi-book exporter creation."""
        exporter = MultiBookExporter("My Library")
        assert exporter.master_deck_name == "My Library"

    def test_add_book(self):
        """Test adding a book to multi-book exporter."""
        exporter = MultiBookExporter("My Library")

        book = Book(title="Test Book", author="Author", chapters=[])
        cc = create_test_chapter_cards()

        count = exporter.add_book(book, [cc])
        assert count == 2
        assert "Test Book" in exporter.book_exporters

    def test_multi_book_export(self):
        """Test exporting multiple books."""
        exporter = MultiBookExporter("My Library")

        book1 = Book(title="Book One", author="Author 1", chapters=[])
        book2 = Book(title="Book Two", author="Author 2", chapters=[])

        cc1 = create_test_chapter_cards()
        cc2 = create_test_chapter_cards()

        exporter.add_book(book1, [cc1])
        exporter.add_book(book2, [cc2])

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "library.apkg"
            result = exporter.export(output)
            assert result.exists()

    def test_multi_book_hierarchy(self):
        """Test that books are added as subdecks."""
        exporter = MultiBookExporter("My Library")

        book = Book(title="Test Book", author="Author", chapters=[])
        exporter.add_book(book, [create_test_chapter_cards()])

        book_exporter = exporter.book_exporters["Test Book"]
        assert "My Library::" in book_exporter.deck_name


class TestCustomTemplates:
    """Test custom card templates."""

    def test_custom_qa_template(self):
        """Test custom Q&A template."""
        template = CardTemplate(
            name="Minimal",
            front_html="<b>{{Question}}</b>",
            back_html="<i>{{Answer}}</i>",
        )
        config = DeckConfig(custom_qa_template=template)
        exporter = AnkiExporter("Test", config=config)

        assert "<b>{{Question}}</b>" in exporter.qa_model.templates[0]["qfmt"]

    def test_custom_cloze_template(self):
        """Test custom Cloze template."""
        template = CardTemplate(
            name="Minimal Cloze",
            front_html="<div>{{cloze:Text}}</div>",
            back_html="<div>{{cloze:Text}}</div>",
        )
        config = DeckConfig(custom_cloze_template=template)
        exporter = AnkiExporter("Test", config=config)

        assert template.front_html in exporter.cloze_model.templates[0]["qfmt"]

    def test_custom_css(self):
        """Test custom CSS."""
        config = DeckConfig(custom_css=".custom { font-size: 24px; }")
        exporter = AnkiExporter("Test", config=config)

        assert ".custom" in exporter.qa_model.css
