from typing import Literal, Optional, List
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50000)


class EnhanceItemRequest(BaseModel):
    item: "ExtractedItem"
    source_text: str = Field(..., min_length=1)


class ExtractedItem(BaseModel):
    user_id: str = "1"
    session_id: Optional[str] = None
    type: Literal["task", "event"]
    title: str
    status: Literal["open", "done", "exported", "expired"] = "open"
    original_date: Optional[str] = None
    due_date: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    note: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None
    exported_at: Optional[str] = None
    confidence: float = 0.0


class ItemUpdateRequest(BaseModel):
    status: Optional[Literal["open", "done", "exported", "expired"]] = None
    note: Optional[str] = None
    title: Optional[str] = None
    due_date: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None


class AnalyzeResponse(BaseModel):
    items: List[ExtractedItem]
    quota_exceeded: bool = False
    quota_remaining: int | None = None


class BulkUpdateRequest(BaseModel):
    ids: List[int]
    status: Literal["open", "done", "exported", "expired"]


class BulkDeleteRequest(BaseModel):
    ids: List[int]


class BulkItemSaveRequest(BaseModel):
    items: List[ExtractedItem]


class BulkItemSaveResponse(BaseModel):
    status: str
    tasks_saved: int
    events_saved: int
    errors: int


class EnhanceItemResponse(BaseModel):
    item: ExtractedItem
    quota_exceeded: bool = False
    quota_remaining: int | None = None
