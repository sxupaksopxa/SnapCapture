from .processors.base import InputProcessor


class ProcessorRegistry:
    """Maintains a list of input processors and routes MIME types to them."""

    def __init__(self) -> None:
        self._processors: list[InputProcessor] = []

    def register(self, processor: InputProcessor) -> None:
        self._processors.append(processor)

    def get_processor(self, content_type: str) -> InputProcessor | None:
        for processor in self._processors:
            if processor.can_handle(content_type):
                return processor
        return None

    def list_supported_types(self) -> set[str]:
        types: set[str] = set()
        for p in self._processors:
            types.update(p.supported_types)
        return types
