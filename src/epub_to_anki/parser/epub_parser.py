"""Parse EPUB files into structured chapter data with optional image extraction."""

import re
import uuid
from pathlib import Path
from typing import Optional

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from ..models import Book, Chapter, EpubImage


def clean_html_to_text(html_content: str) -> str:
    """Convert HTML to clean plain text."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "nav", "header", "footer"]):
        element.decompose()

    # Get text with some structure preservation
    text = soup.get_text(separator="\n")

    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    text = "\n".join(line for line in lines if line)

    # Normalize multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_chapter_title(item: epub.EpubHtml, soup: BeautifulSoup, index: int) -> str:
    """Extract the chapter title from an EPUB item."""
    # Try to get title from the item's title attribute
    if item.title:
        return item.title

    # Try to find h1, h2, or h3 heading
    for tag in ["h1", "h2", "h3"]:
        heading = soup.find(tag)
        if heading:
            title = heading.get_text(strip=True)
            if title and len(title) < 200:  # Sanity check
                return title

    # Fallback to item filename or generic title
    if item.file_name:
        name = Path(item.file_name).stem
        # Clean up common naming patterns
        name = re.sub(r"^(chapter|ch|chap)[_-]?", "", name, flags=re.IGNORECASE)
        if name and not name.isdigit():
            return name.replace("_", " ").replace("-", " ").title()

    return f"Chapter {index + 1}"


def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def is_content_chapter(text: str, title: str) -> bool:
    """Determine if this is actual content vs front/back matter."""
    # Skip very short sections
    if count_words(text) < 100:
        return False

    # Skip common non-content sections
    skip_patterns = [
        r"^table of contents?$",
        r"^contents?$",
        r"^copyright",
        r"^all rights reserved",
        r"^title page$",
        r"^cover$",
        r"^dedication$",
        r"^acknowledgements?$",
        r"^about the author$",
        r"^index$",
        r"^bibliography$",
        r"^references$",
        r"^notes$",
        r"^appendix",
    ]

    title_lower = title.lower().strip()
    for pattern in skip_patterns:
        if re.match(pattern, title_lower):
            return False

    return True


def extract_images_from_epub(
    epub_book: epub.EpubBook,
    extract_images: bool = False,
) -> list[EpubImage]:
    """
    Extract all images from an EPUB book.

    Args:
        epub_book: The parsed EPUB book
        extract_images: Whether to actually extract image data

    Returns:
        List of EpubImage objects
    """
    if not extract_images:
        return []

    images: list[EpubImage] = []

    for item in epub_book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE:
            try:
                filename = Path(item.file_name).name
                media_type = item.media_type

                images.append(
                    EpubImage(
                        id=str(uuid.uuid4())[:8],
                        filename=filename,
                        media_type=media_type,
                        data=item.get_content(),
                    )
                )
            except Exception:
                # Skip problematic images
                continue

    return images


def extract_chapter_images(
    html_content: str,
    all_images: list[EpubImage],
    chapter_index: int,
) -> list[EpubImage]:
    """
    Find images referenced in a chapter's HTML.

    Args:
        html_content: The chapter's HTML content
        all_images: List of all extracted images
        chapter_index: Index of the chapter

    Returns:
        List of images referenced in this chapter
    """
    soup = BeautifulSoup(html_content, "html.parser")
    chapter_images: list[EpubImage] = []

    # Find all img tags
    for img_tag in soup.find_all("img"):
        src = img_tag.get("src", "")
        if not src:
            continue

        # Get filename from src
        img_filename = Path(src).name

        # Find matching image in our list
        for img in all_images:
            if img.filename == img_filename:
                # Create a copy with chapter reference
                chapter_img = EpubImage(
                    id=img.id,
                    filename=img.filename,
                    media_type=img.media_type,
                    data=img.data,
                    source_chapter_index=chapter_index,
                )
                chapter_images.append(chapter_img)
                break

    return chapter_images


def parse_epub(
    file_path: str | Path,
    extract_images: bool = False,
) -> Book:
    """
    Parse an EPUB file into a Book object with chapters.

    Args:
        file_path: Path to the EPUB file
        extract_images: Whether to extract and include images

    Returns:
        Book object with parsed chapters
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"EPUB file not found: {file_path}")

    book = epub.read_epub(str(file_path))

    # Extract metadata
    title = "Unknown Title"
    author = "Unknown Author"
    language = None
    identifier = None

    # Get title
    title_meta = book.get_metadata("DC", "title")
    if title_meta:
        title = title_meta[0][0]

    # Get author
    author_meta = book.get_metadata("DC", "creator")
    if author_meta:
        author = author_meta[0][0]

    # Get language
    lang_meta = book.get_metadata("DC", "language")
    if lang_meta:
        language = lang_meta[0][0]

    # Get identifier (ISBN etc)
    id_meta = book.get_metadata("DC", "identifier")
    if id_meta:
        identifier = id_meta[0][0]

    # Extract all images if requested
    all_images = extract_images_from_epub(book, extract_images)

    # Extract chapters
    chapters: list[Chapter] = []
    chapter_index = 0

    # Get items in spine order (reading order)
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            html_content = item.get_content().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html_content, "html.parser")
            text = clean_html_to_text(html_content)

            if not text:
                continue

            chapter_title = extract_chapter_title(item, soup, chapter_index)

            # Filter out non-content sections
            if not is_content_chapter(text, chapter_title):
                continue

            # Extract images for this chapter
            chapter_images = extract_chapter_images(
                html_content, all_images, chapter_index
            ) if extract_images else []

            chapter = Chapter(
                index=chapter_index,
                title=chapter_title,
                content=text,
                word_count=count_words(text),
                html_content=html_content,
                images=chapter_images,
            )
            chapters.append(chapter)
            chapter_index += 1

    if not chapters:
        raise ValueError(
            f"No content chapters found in '{file_path.name}'. "
            "The EPUB may be empty, corrupted, or contain only front/back matter."
        )

    return Book(
        title=title,
        author=author,
        chapters=chapters,
        language=language,
        identifier=identifier,
        images=all_images,
    )


def get_book_summary(book: Book, include_images: bool = False) -> str:
    """Get a human-readable summary of a parsed book."""
    lines = [
        f"Title: {book.title}",
        f"Author: {book.author}",
        f"Chapters: {len(book.chapters)}",
        f"Total words: {book.total_words:,}",
    ]

    if include_images and book.images:
        lines.append(f"Images: {len(book.images)}")

    lines.extend(["", "Chapters:"])

    for ch in book.chapters:
        line = f"  {ch.index + 1}. {ch.title} ({ch.word_count:,} words)"
        if include_images and ch.images:
            line += f" [{len(ch.images)} images]"
        lines.append(line)

    return "\n".join(lines)
