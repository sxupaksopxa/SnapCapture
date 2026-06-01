from abc import ABC, abstractmethod


class InputProcessor(ABC):
    """Base class for all input-type processors."""

    @property
    @abstractmethod
    def supported_types(self) -> set[str]:
        """MIME types this processor can handle."""
        ...

    @abstractmethod
    async def extract_text(self, file_bytes: bytes, content_type: str, filename: str | None = None) -> str:
        """Convert raw input bytes into plain text."""
        ...

    def can_handle(self, content_type: str) -> bool:
        # Strip parameters like ;codecs=opus so audio/webm;codecs=opus matches audio/webm
        base_type = content_type.split(";")[0].strip().lower()
        return base_type in self.supported_types
