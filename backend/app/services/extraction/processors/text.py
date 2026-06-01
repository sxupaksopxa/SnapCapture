from .base import InputProcessor


class TextProcessor(InputProcessor):
    """Handles raw text / markdown pasted by the user."""

    supported_types = {"text/plain", "text/markdown", "text/x-markdown"}

    async def extract_text(self, file_bytes: bytes, content_type: str, filename: str | None = None) -> str:
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1", errors="ignore")
