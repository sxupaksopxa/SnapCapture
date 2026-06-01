import logging
import re

from app.models import ExtractedItem
from app.services.capture_service import GeminiExtractionService
from app.services.openai_extraction_service import OpenAIExtractionService
from app.services.quota import QuotaService
from .models import ExtractionResult
from .registry import ProcessorRegistry
from .text_extractor import LocalTextExtractor
from .processors.text import TextProcessor
from .processors.image import ImageProcessor
from .processors.pdf import PDFProcessor
from .processors.audio import AudioProcessor

logger = logging.getLogger(__name__)

# Minimum word count for OCR text to be considered usable
_MIN_MEANINGFUL_WORDS = 3
_MIN_MEANINGFUL_CHARS = 10


class ExtractionOrchestrator:
    """
    Routes incoming data to the correct InputProcessor, runs the local
    rule-based extractor, and falls back to the selected AI provider only
    when confidence is below the threshold and quota permits.
    """

    FALLBACK_THRESHOLD = 0.65

    def __init__(self) -> None:
        self.registry = ProcessorRegistry()
        self.registry.register(TextProcessor())
        self.registry.register(ImageProcessor())
        self.registry.register(PDFProcessor())
        self.registry.register(AudioProcessor())

        self.local_extractor = LocalTextExtractor()

    @staticmethod
    def get_ai_service(provider: str | None = None, api_key: str | None = None):
        """Instantiate the correct AI extraction service."""
        provider = (provider or "gemini").lower().strip()
        if provider == "openai":
            return OpenAIExtractionService(api_key=api_key or None)
        return GeminiExtractionService(api_key=api_key or None)

    # ── Public entrypoints ──

    async def extract(
        self,
        file_bytes: bytes,
        content_type: str,
        filename: str | None = None,
        session_id: str = "anonymous",
        quota_service: QuotaService | None = None,
        provider: str | None = None,
        api_key: str | None = None,
    ) -> ExtractionResult:
        """Process a file upload (image, PDF, audio)."""
        processor = self.registry.get_processor(content_type)

        if not processor:
            logger.warning("No local processor for %s → AI vision fallback", content_type)
            return await self._ai_fallback(file_bytes, content_type, session_id, quota_service, provider, api_key)

        try:
            extracted_text = await processor.extract_text(file_bytes, content_type, filename)
        except Exception as exc:
            logger.warning("Local processor failed for %s: %s → AI fallback", content_type, exc)
            return await self._ai_fallback(file_bytes, content_type, session_id, quota_service, provider, api_key)

        if not self._is_meaningful_text(extracted_text):
            logger.warning("Extracted text from %s not meaningful → AI fallback", content_type)
            return await self._ai_fallback(file_bytes, content_type, session_id, quota_service, provider, api_key)

        return self._run_local_then_fallback(extracted_text, session_id, quota_service, provider, api_key)

    async def extract_from_text(
        self,
        text: str,
        session_id: str = "anonymous",
        quota_service: QuotaService | None = None,
        provider: str | None = None,
        api_key: str | None = None,
    ) -> ExtractionResult:
        """Process typed or pasted plain text."""
        return self._run_local_then_fallback(text, session_id, quota_service, provider, api_key)

    # ── Internal ──

    def _run_local_then_fallback(
        self,
        text: str,
        session_id: str = "anonymous",
        quota_service: QuotaService | None = None,
        provider: str | None = None,
        api_key: str | None = None,
    ) -> ExtractionResult:
        items = self.local_extractor.extract(text)
        confidence = self._average_confidence(items)

        if confidence >= self.FALLBACK_THRESHOLD and items:
            # Local extraction is good enough — no quota consumed
            if quota_service:
                quota_service.increment_local(session_id)
            logger.info("Local extraction OK — %.2f confidence, %d items", confidence, len(items))
            return ExtractionResult(
                items=items,
                confidence=confidence,
                used_fallback=False,
                source="LocalTextExtractor",
                quota_remaining=quota_service.get_status(session_id)["remaining"] if quota_service else None,
            )

        # Local confidence is low — need AI, but check quota first
        if quota_service and not quota_service.can_use_gemini(session_id):
            logger.warning("Quota exhausted for session %s — returning low-confidence local results", session_id)
            return ExtractionResult(
                items=items,
                confidence=confidence,
                used_fallback=False,
                source="LocalTextExtractor",
                quota_exceeded=True,
                quota_remaining=0,
            )

        # Quota available (or no quota tracking) → call selected AI provider
        ai_service = self.get_ai_service(provider, api_key)
        provider_label = "OpenAI" if (provider or "").lower().strip() == "openai" else "Gemini"
        logger.info("Local confidence %.2f below threshold → %s fallback", confidence, provider_label)
        ai_items = ai_service.extract_items_from_text(text)

        if quota_service and not api_key:
            status = quota_service.increment_gemini(session_id)
            return ExtractionResult(
                items=ai_items,
                confidence=self._average_confidence(ai_items),
                used_fallback=True,
                source=f"{provider_label}ExtractionService",
                quota_remaining=status["remaining"],
            )

        return ExtractionResult(
            items=ai_items,
            confidence=self._average_confidence(ai_items),
            used_fallback=True,
            source=f"{provider_label}ExtractionService",
        )

    async def _ai_fallback(
        self,
        file_bytes: bytes,
        content_type: str,
        session_id: str = "anonymous",
        quota_service: QuotaService | None = None,
        provider: str | None = None,
        api_key: str | None = None,
    ) -> ExtractionResult:
        """Direct AI vision fallback for unknown types or local failures."""
        if quota_service and not quota_service.can_use_gemini(session_id):
            logger.warning("Quota exhausted for session %s — cannot run AI vision fallback", session_id)
            return ExtractionResult(
                items=[],
                confidence=0.0,
                used_fallback=False,
                source="LocalTextExtractor",
                quota_exceeded=True,
                quota_remaining=0,
            )

        ai_service = self.get_ai_service(provider, api_key)
        provider_label = "OpenAI" if (provider or "").lower().strip() == "openai" else "Gemini"
        logger.info("AI vision fallback starting — provider=%s, content_type=%s, bytes=%d", provider_label, content_type, len(file_bytes))
        items = ai_service.extract_items_from_file_bytes(file_bytes, content_type)
        logger.info("AI vision fallback completed — provider=%s, items=%d", provider_label, len(items))

        if quota_service and not api_key:
            status = quota_service.increment_gemini(session_id)
            return ExtractionResult(
                items=items,
                confidence=self._average_confidence(items),
                used_fallback=True,
                source=f"{provider_label}ExtractionService",
                quota_remaining=status["remaining"],
            )

        return ExtractionResult(
            items=items,
            confidence=self._average_confidence(items),
            used_fallback=True,
            source=f"{provider_label}ExtractionService",
        )

    @staticmethod
    def _average_confidence(items: list[ExtractedItem]) -> float:
        if not items:
            return 0.0
        return round(sum(item.confidence for item in items) / len(items), 2)

    @staticmethod
    def _is_meaningful_text(text: str) -> bool:
        if not text or len(text.strip()) < _MIN_MEANINGFUL_CHARS:
            return False
        words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", text)
        return len(words) >= _MIN_MEANINGFUL_WORDS
