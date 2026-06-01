from pydantic import BaseModel
from app.models import ExtractedItem


class ExtractionResult(BaseModel):
    items: list[ExtractedItem]
    confidence: float
    used_fallback: bool
    source: str
    quota_exceeded: bool = False
    quota_remaining: int | None = None
