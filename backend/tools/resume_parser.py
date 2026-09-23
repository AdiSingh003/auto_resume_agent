"""Resume Parser — extracts text from uploaded PDF and DOCX files."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_pdf(file_path: str) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    try:
        import pymupdf

        with pymupdf.open(file_path) as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception as e:
        logger.error("Failed to parse PDF %s: %s", file_path, e)
        raise


def parse_docx(file_path: str) -> str:
    """Extract text from a DOCX file."""
    try:
        from docx import Document

        doc = Document(file_path)
        text_parts = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)
        return "\n".join(text_parts)
    except Exception as e:
        logger.error("Failed to parse DOCX %s: %s", file_path, e)
        raise


def parse_resume(file_path: str) -> str:
    """Parse a resume file (PDF or DOCX) and return extracted text."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return parse_pdf(file_path)
    elif suffix == ".docx":
        return parse_docx(file_path)
    elif suffix == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use PDF, DOCX, or TXT.")


# Allowed extensions for file upload validation (legacy binary .doc is not parseable by python-docx)
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def validate_upload(filename: str, file_size: int) -> tuple[bool, str]:
    """Validate uploaded file extension and size."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported format: {ext or 'none'}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
    if file_size == 0:
        return False, "File is empty"
    if file_size > MAX_FILE_SIZE:
        return False, f"File too large: {file_size / 1024 / 1024:.1f}MB. Max: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
    return True, "OK"
