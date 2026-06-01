import io
import logging

import pdfplumber
from PIL import Image

from .base import InputProcessor
from .image import ImageProcessor

logger = logging.getLogger(__name__)


class PDFProcessor(InputProcessor):
    """Text extraction from PDFs via pdfplumber, with optional OCR fallback for scanned pages."""

    supported_types = {"application/pdf"}

    def __init__(self) -> None:
        self._image_processor = ImageProcessor()

    async def extract_text(self, file_bytes: bytes, content_type: str, filename: str | None = None) -> str:
        text = self._extract_with_pdfplumber(file_bytes)

        is_likely_scanned = self._is_likely_scanned(text, file_bytes)

        if text.strip() and not is_likely_scanned:
            logger.info("PDF text via pdfplumber: %d chars", len(text))
            return text

        logger.warning(
            "PDF likely scanned or empty (%d chars) → OCR fallback",
            len(text or ""),
        )
        ocr_text = self._extract_with_ocr(file_bytes)
        if ocr_text:
            logger.info("PDF text via OCR fallback: %d chars", len(ocr_text))
        return ocr_text or text or ""

    def _extract_with_pdfplumber(self, file_bytes: bytes) -> str:
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            return "\n".join(pages).strip()
        except Exception as exc:
            logger.warning("pdfplumber failed: %s", exc)
            return ""

    def _is_likely_scanned(self, text: str | None, file_bytes: bytes) -> bool:
        """Heuristic: very short text relative to page count suggests a scanned/image PDF."""
        if not text or len(text.strip()) < 50:
            return True
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                page_count = len(pdf.pages)
                if page_count > 0:
                    avg_chars = len(text) / page_count
                    return avg_chars < 100
        except Exception:
            pass
        return False

    def _extract_with_ocr(self, file_bytes: bytes) -> str:
        try:
            import fitz  # PyMuPDF — optional dependency
        except ImportError:
            logger.warning(
                "PyMuPDF not installed. Scanned PDFs cannot be OCR'd locally. "
                "Install with: pip install pymupdf"
            )
            return ""

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            texts = []
            for page_num, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                page_text = self._image_processor._process_image(img)
                if page_text:
                    texts.append(page_text)
                else:
                    logger.debug("OCR produced no text for PDF page %d", page_num)
            return "\n".join(texts).strip()
        except Exception as exc:
            logger.warning("PDF OCR fallback failed: %s", exc)
            return ""
