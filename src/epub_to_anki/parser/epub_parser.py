"""Parse EPUB files into structured chapter data."""

import hashlib
import re
from pathlib import Path
from typing import Optional

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from ..models import Book, Chapter, ImageRef


# Try to import PIL for image dimensions, but make it optional
try:
    from PIL import Image
    import io
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


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


def get_image_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    """Get image dimensions if PIL is available."""
    if not HAS_PIL:
        return None, None
    try:
        img = Image.open(io.BytesIO(data))
        return img.width, img.height
    except Exception:
        return None, None


def generate_image_id(filename: str, data: bytes) -> str:
    """Generate a unique ID for an image based on content hash."""
    content_hash = hashlib.md5(data).hexdigest()[:8]
    stem = Path(filename).stem
    # Sanitize filename for use in ID
    safe_stem = re.sub(r'[^a-zA-Z0-9_-]', '_', stem)[:20]
    return f"img_{safe_stem}_{content_hash}"


def find_images_in_html(html_content: str, epub_images: dict[str, str]) -> list[str]:
    """Find image IDs referenced in HTML content.

    Args:
        html_content: HTML content to search
        epub_images: Mapping of EPUB file paths to image IDs

    Returns:
        List of image IDs referenced in this HTML
    """
    soup = BeautifulSoup(html_content, "html.parser")
    found_ids = []

    for img_tag in soup.find_all("img"):
        src = img_tag.get("src", "")
        if not src:
            continue

        # Normalize the path (remove ../ prefixes, etc.)
        src_parts = src.split("/")
        src_filename = src_parts[-1] if src_parts else src

        # Try to match against our extracted images
        for epub_path, image_id in epub_images.items():
            epub_filename = epub_path.split("/")[-1] if "/" in epub_path else epub_path
            if src_filename == epub_filename or src.endswith(epub_path):
                if image_id not in found_ids:
                    found_ids.append(image_id)
                break

    return found_ids


def parse_epub(file_path: str | Path, extract_images: bool = False) -> tuple[Book, dict[str, bytes]]:
    """
    Parse an EPUB file into a Book object with chapters.

    Args:
        file_path: Path to the EPUB file
        extract_images: Whether to extract images from the EPUB

    Returns:
        Tuple of (Book object with parsed chapters, dict of image_id -> image_data)
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"EPUB file not found: {file_path}")

    epub_book = epub.read_epub(str(file_path))

    # Extract metadata
    title = "Unknown Title"
    author = "Unknown Author"
    language = None
    identifier = None

    # Get title
    title_meta = epub_book.get_metadata("DC", "title")
    if title_meta:
        title = title_meta[0][0]

    # Get author
    author_meta = epub_book.get_metadata("DC", "creator")
    if author_meta:
        author = author_meta[0][0]

    # Get language
    lang_meta = epub_book.get_metadata("DC", "language")
    if lang_meta:
        language = lang_meta[0][0]

    # Get identifier (ISBN etc)
    id_meta = epub_book.get_metadata("DC", "identifier")
    if id_meta:
        identifier = id_meta[0][0]

    # Extract images if requested
    image_refs: list[ImageRef] = []
    image_data: dict[str, bytes] = {}
    epub_path_to_id: dict[str, str] = {}  # Maps EPUB internal paths to image IDs

    if extract_images:
        for item in epub_book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                data = item.get_content()
                filename = item.file_name
                media_type = item.media_type or "image/unknown"

                # Generate unique ID
                image_id = generate_image_id(filename, data)

                # Get dimensions if possible
                width, height = get_image_dimensions(data)

                # Create ImageRef
                image_ref = ImageRef(
                    id=image_id,
                    filename=filename,
                    media_type=media_type,
                    width=width,
                    height=height,
                )
                image_refs.append(image_ref)
                image_data[image_id] = data
                epub_path_to_id[filename] = image_id

    # Extract chapters
    chapters: list[Chapter] = []
    chapter_index = 0

    # Get items in spine order (reading order)
    for item in epub_book.get_items():
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

            # Find images in this chapter
            chapter_image_ids = []
            if extract_images:
                chapter_image_ids = find_images_in_html(html_content, epub_path_to_id)
                # Update image refs with chapter index
                for img_id in chapter_image_ids:
                    for img_ref in image_refs:
                        if img_ref.id == img_id and img_ref.chapter_index is None:
                            img_ref.chapter_index = chapter_index

            chapter = Chapter(
                index=chapter_index,
                title=chapter_title,
                content=text,
                word_count=count_words(text),
                html_content=html_content,
                image_ids=chapter_image_ids,
            )
            chapters.append(chapter)
            chapter_index += 1

    if not chapters:
        raise ValueError(
            f"No content chapters found in '{file_path.name}'. "
            "The EPUB may be empty, corrupted, or contain only front/back matter."
        )

    result_book = Book(
        title=title,
        author=author,
        chapters=chapters,
        language=language,
        identifier=identifier,
        images=image_refs,
    )

    return result_book, image_data


def get_book_summary(book: Book) -> str:
    """Get a human-readable summary of a parsed book."""
    lines = [
        f"Title: {book.title}",
        f"Author: {book.author}",
        f"Chapters: {len(book.chapters)}",
        f"Total words: {book.total_words:,}",
    ]

    if book.images:
        lines.append(f"Images: {len(book.images)}")

    lines.extend(["", "Chapters:"])

    for ch in book.chapters:
        img_info = f", {len(ch.image_ids)} images" if ch.image_ids else ""
        lines.append(f"  {ch.index + 1}. {ch.title} ({ch.word_count:,} words{img_info})")

    return "\n".join(lines)
