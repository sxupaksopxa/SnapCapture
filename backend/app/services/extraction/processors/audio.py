import os
import tempfile
import logging

from faster_whisper import WhisperModel

from .base import InputProcessor

logger = logging.getLogger(__name__)


class AudioProcessor(InputProcessor):
    """Transcribe audio to text using local faster-whisper."""

    supported_types = {
        "audio/webm",
        "audio/wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/m4a",
        "audio/ogg",
    }

    def __init__(self, model_size: str = "small") -> None:
        self._model_size = model_size
        self._model: WhisperModel | None = None

    def _load_model(self) -> WhisperModel:
        if self._model is None:
            logger.info("Loading Whisper model: %s", self._model_size)
            self._model = WhisperModel(
                self._model_size, device="cpu", compute_type="int8"
            )
        return self._model

    async def extract_text(self, file_bytes: bytes, content_type: str, filename: str | None = None) -> str:
        base_type = content_type.split(";")[0].strip().lower()
        suffix = (
            ".webm"
            if "webm" in base_type
            else ".mp3" if "mp3" in base_type else ".wav"
        )
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            model = self._load_model()
            segments, info = model.transcribe(tmp_path, beam_size=5, language=None)
            logger.info(
                "Whisper detected language: %s (probability %.2f)",
                info.language,
                info.language_probability,
            )
            text = " ".join([segment.text for segment in segments]).strip()
            logger.info("Whisper transcribed %d chars", len(text))
            return text
        finally:
            os.unlink(tmp_path)
