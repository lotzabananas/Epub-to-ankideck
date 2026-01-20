"""Tests for cost estimation."""


from epub_to_anki.cost_estimator import CostEstimate, CostEstimator
from epub_to_anki.models import Book, Chapter, Density


def create_test_book() -> Book:
    """Create a test book with chapters."""
    chapters = [
        Chapter(index=0, title="Chapter 1", content="word " * 1000, word_count=1000),
        Chapter(index=1, title="Chapter 2", content="word " * 2000, word_count=2000),
        Chapter(index=2, title="Chapter 3", content="word " * 500, word_count=500),
    ]
    return Book(title="Test Book", author="Test Author", chapters=chapters)


def test_estimate_book_all_chapters():
    """Test estimating cost for all chapters."""
    book = create_test_book()
    estimator = CostEstimator()

    estimate = estimator.estimate_book(book, Density.MEDIUM)

    assert estimate.chapters_count == 3
    assert estimate.total_words == 3500
    assert estimate.estimated_cost_usd > 0
    assert estimate.total_input_tokens > 0
    assert estimate.total_output_tokens > 0
    assert len(estimate.chapter_estimates) == 3


def test_estimate_book_selected_chapters():
    """Test estimating cost for selected chapters."""
    book = create_test_book()
    estimator = CostEstimator()

    estimate = estimator.estimate_book(book, Density.MEDIUM, chapter_indices=[0, 2])

    assert estimate.chapters_count == 2
    assert estimate.total_words == 1500  # Chapters 1 and 3


def test_density_affects_output_estimate():
    """Test that density affects output token estimates."""
    book = create_test_book()
    estimator = CostEstimator()

    light = estimator.estimate_book(book, Density.LIGHT)
    thorough = estimator.estimate_book(book, Density.THOROUGH)

    # Thorough should estimate more output tokens (more cards)
    assert thorough.total_output_tokens > light.total_output_tokens


def test_estimate_remaining():
    """Test estimating remaining chapters."""
    book = create_test_book()
    estimator = CostEstimator()

    # Simulate chapter 0 already processed
    estimate = estimator.estimate_remaining(book, Density.MEDIUM, processed_indices=[0])

    assert estimate.chapters_count == 2  # Chapters 1 and 2
    assert estimate.total_words == 2500


def test_format_estimate():
    """Test formatting estimate for display."""
    book = create_test_book()
    estimator = CostEstimator()

    estimate = estimator.estimate_book(book, Density.MEDIUM)
    formatted = estimator.format_estimate(estimate)

    assert "Cost Estimate" in formatted
    assert "medium" in formatted
    assert "$" in formatted


def test_format_estimate_verbose():
    """Test verbose formatting with per-chapter breakdown."""
    book = create_test_book()
    estimator = CostEstimator()

    estimate = estimator.estimate_book(book, Density.MEDIUM)
    formatted = estimator.format_estimate(estimate, verbose=True)

    assert "Per-chapter breakdown" in formatted
    assert "Chapter 1" in formatted


def test_cost_estimate_str():
    """Test CostEstimate string representation."""
    estimate = CostEstimate(
        total_input_tokens=10000,
        total_output_tokens=5000,
        estimated_cost_usd=0.0525,
        chapters_count=3,
        total_words=3500,
        density="medium",
        chapter_estimates=[],
    )

    result = str(estimate)

    assert "0.0525" in result
    assert "10,000" in result
    assert "5,000" in result
