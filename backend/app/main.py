import logging
import os
import re
import uuid

from fastapi import FastAPI, Depends, File, Form, HTTPException, UploadFile, status, Response, Query, Header, Request
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import html

from app.database import Base, engine, SessionLocal
from app.db_models import EventDB, TaskDB
from sqlalchemy import text
from app.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    ExtractedItem,
    ItemUpdateRequest,
    BulkUpdateRequest,
    BulkDeleteRequest,
    BulkItemSaveRequest,
    BulkItemSaveResponse,
    EnhanceItemRequest,
    EnhanceItemResponse,
)
from app.services.extraction import ExtractionOrchestrator
from app.services.quota import QuotaService

import json as _json
from datetime import datetime, timedelta
from icalendar import Calendar, Event as ICalEvent, Todo as ICalTodo

logger = logging.getLogger(__name__)

# Orchestrator routes inputs to local processors and falls back to Gemini only when needed.
_orchestrator = ExtractionOrchestrator()

app = FastAPI(title="SnapCapture API")

Base.metadata.create_all(bind=engine)


# Local timezone used for all user-facing timestamps (ICS, exports, quotas)
_LOCAL_TZ = datetime.now().astimezone().tzinfo


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_device_id(x_device_id: str | None = Header(default=None)) -> str:
    """Read anonymous device ID from request header; generate UUID fallback if missing."""
    device_id = x_device_id if x_device_id else None
    if not device_id:
        return str(uuid.uuid4())
    if len(device_id) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Device-ID header (max 64 chars)",
        )
    return device_id


def get_provider(x_provider: str | None = Header(default=None)) -> str | None:
    return x_provider if x_provider else None


def get_api_key(x_api_key: str | None = Header(default=None)) -> str | None:
    return x_api_key if x_api_key else None


# CORS: allow comma-separated origins from env, fallback to localhost
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
allow_origins = [o.strip() for o in _allowed_origins.split(",") if o.strip()]

# Reject wildcard origins when credentials are enabled
if any("*" in o for o in allow_origins):
    logger.warning("ALLOWED_ORIGINS contains wildcard '*' with allow_credentials=True; filtering wildcards")
    allow_origins = [o for o in allow_origins if "*" not in o]
    if not allow_origins:
        allow_origins = ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["X-Device-ID", "X-Provider", "X-API-Key", "Content-Type"],
)


# ── Security headers middleware ──
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


# ── Simple in-memory rate limiter ──
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 60     # requests per window per client
_rate_limit_store: dict[str, list[float]] = {}


def _rate_limit_key(request: Request, device_id: str) -> str:
    client_ip = request.client.host if request.client else "unknown"
    return f"{client_ip}:{device_id}"


def check_rate_limit(request: Request, device_id: str = Depends(get_device_id)):
    key = _rate_limit_key(request, device_id)
    now = datetime.now().timestamp()
    window_start = now - _RATE_LIMIT_WINDOW
    timestamps = _rate_limit_store.get(key, [])
    timestamps = [ts for ts in timestamps if ts > window_start]
    if len(timestamps) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down.",
        )
    timestamps.append(now)
    _rate_limit_store[key] = timestamps
    return device_id


# ── Input sanitization ──
_MAX_TEXT_LENGTH = 50_000  # characters

def _sanitize_text(text: str | None) -> str | None:
    if text is None:
        return None
    # Strip control chars except newlines/tabs
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or (ord(ch) >= 32 and ord(ch) <= 0x10FFFF))
    # Basic HTML escape to neutralize accidental payloads
    text = html.escape(text)
    return text


def _sanitize_item_fields(item: ExtractedItem) -> ExtractedItem:
    """Sanitize text fields on an ExtractedItem to prevent stored XSS in exports."""
    item.title = _sanitize_text(item.title) or ""
    item.note = _sanitize_text(item.note)
    item.location = _sanitize_text(item.location)
    item.original_date = _sanitize_text(item.original_date)
    item.due_date = _sanitize_text(item.due_date)
    item.date = _sanitize_text(item.date)
    item.time = _sanitize_text(item.time)
    return item

def _db_obj_to_dict(obj):
    """Convert a SQLAlchemy row to a plain dict for JSON serialization."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _save_db_item(db: Session, model_cls, item: ExtractedItem, session_id: str | None = None):
    """Generic helper to persist an ExtractedItem into a DB table."""
    item = _sanitize_item_fields(item)
    now_iso = datetime.now().astimezone().isoformat()
    record = model_cls(
        user_id=item.user_id,
        session_id=session_id,
        title=item.title,
        status=item.status,
        original_date=item.original_date,
        due_date=item.due_date,
        date=item.date,
        time=item.time,
        location=item.location,
        confidence=item.confidence,
        note=item.note,
        source=item.source,
        created_at=now_iso,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _parse_event_datetime(date_str: str | None, time_str: str | None, original_date_str: str | None = None):
    """Convert DD.MM.YYYY, DD.MM., or DD.MM and HH:MM/HH.MMh into (dtstart, dtend) datetimes.
    Falls back to original_date_str if date_str is empty. All returned datetimes are
    timezone-aware in the server's local timezone so calendar apps do not shift them."""
    for candidate in (date_str, original_date_str):
        if not candidate:
            continue

        dt_start = None
        try:
            dt_start = datetime.strptime(candidate, "%d.%m.%Y")
        except ValueError:
            pass

        if dt_start is None:
            m = re.match(r"^(\d{1,2})\.(\d{1,2})\.?$", candidate)
            if m:
                day, month = int(m.group(1)), int(m.group(2))
                year = datetime.now().year
                try:
                    dt_start = datetime(year, month, day)
                except ValueError:
                    continue

        if dt_start is not None:
            # Attach local timezone so ICS is not interpreted as UTC
            dt_start = dt_start.replace(tzinfo=_LOCAL_TZ)

            normalized_time = None
            if time_str:
                t = time_str.lower().replace("h", "").replace(".", ":").strip()
                parts = t.split()
                if len(parts) == 2 and ":" in parts[0] and ":" in parts[1]:
                    normalized_time = f"{parts[0]}-{parts[1]}"
                else:
                    normalized_time = t

            dt_end = None
            if normalized_time:
                if "-" in normalized_time:
                    start_time, end_time = normalized_time.split("-", 1)
                    try:
                        h, m = map(int, start_time.strip().split(":"))
                        dt_start = dt_start.replace(hour=h, minute=m, second=0)
                    except ValueError:
                        pass
                    try:
                        eh, em = map(int, end_time.strip().split(":"))
                        dt_end = dt_start.replace(hour=eh, minute=em, second=0)
                    except ValueError:
                        dt_end = dt_start + timedelta(hours=1)
                else:
                    try:
                        h, m = map(int, normalized_time.strip().split(":"))
                        dt_start = dt_start.replace(hour=h, minute=m, second=0)
                    except ValueError:
                        pass
                    dt_end = dt_start + timedelta(hours=1)
            else:
                dt_end = dt_start + timedelta(hours=1)

            return dt_start, dt_end

    return None, None


# ── Routes ──

@app.get("/")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "service": "SnapCapture API"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    device_id: str = Depends(get_device_id),
    provider: str | None = Depends(get_provider),
    api_key: str | None = Depends(get_api_key),
    db: Session = Depends(get_db),
    _rate_limit: str = Depends(check_rate_limit),
):
    if len(request.text) > _MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Text too long. Maximum {_MAX_TEXT_LENGTH} characters.",
        )
    try:
        quota_service = QuotaService(db)
        result = await _orchestrator.extract_from_text(
            request.text,
            session_id=device_id,
            quota_service=quota_service,
            provider=provider,
            api_key=api_key,
        )
        return AnalyzeResponse(
            items=result.items,
            quota_exceeded=result.quota_exceeded,
            quota_remaining=result.quota_remaining,
        )
    except Exception as exc:
        logger.exception("Text analysis failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis failed. Please try again later.",
        ) from exc


@app.post("/tasks")
def save_task(
    item: ExtractedItem,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    if item.type != "task":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only task items can be saved here",
        )
    try:
        task = _save_db_item(db, TaskDB, item, session_id=device_id)
        return {"status": "saved", "item": _db_obj_to_dict(task)}
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to save task")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save task",
        ) from exc


@app.get("/tasks")
def get_tasks(device_id: str = Depends(get_device_id), db: Session = Depends(get_db)):
    try:
        tasks = db.query(TaskDB).filter(TaskDB.session_id == device_id).all()
        return {"items": [_db_obj_to_dict(t) for t in tasks]}
    except Exception as exc:
        logger.exception("Failed to load tasks")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load tasks",
        ) from exc


@app.post("/events")
def save_event(
    item: ExtractedItem,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    if item.type != "event":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only event items can be saved here",
        )
    try:
        event = _save_db_item(db, EventDB, item, session_id=device_id)
        return {"status": "saved", "item": _db_obj_to_dict(event)}
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to save event")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save event",
        ) from exc


@app.get("/events")
def get_events(device_id: str = Depends(get_device_id), db: Session = Depends(get_db)):
    try:
        events = db.query(EventDB).filter(EventDB.session_id == device_id).all()
        return {"items": [_db_obj_to_dict(e) for e in events]}
    except Exception as exc:
        logger.exception("Failed to load events")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load events",
        ) from exc


def _is_expired(date_str: str | None, time_str: str | None = None) -> bool:
    """Check if a given date (DD.MM.YYYY) is in the past. If time is provided, use it."""
    if not date_str:
        return False
    dt_start, _ = _parse_event_datetime(date_str, time_str)
    if dt_start is None:
        return False
    return dt_start < datetime.now(_LOCAL_TZ)


@app.patch("/tasks/{task_id}")
def update_task(task_id: int, req: ItemUpdateRequest, device_id: str = Depends(get_device_id), db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id, TaskDB.session_id == device_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    if req.status is not None:
        task.status = req.status
    if req.note is not None:
        task.note = req.note
    if req.title is not None:
        task.title = req.title
    if req.due_date is not None:
        task.due_date = req.due_date
    # Re-check expiration when date changes
    if req.due_date is not None:
        task.status = "expired" if _is_expired(task.due_date) else "open"
    db.commit()
    db.refresh(task)
    return {"status": "updated", "item": _db_obj_to_dict(task)}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, device_id: str = Depends(get_device_id), db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id, TaskDB.session_id == device_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    db.delete(task)
    db.commit()
    return {"status": "deleted"}


@app.patch("/events/{event_id}")
def update_event(event_id: int, req: ItemUpdateRequest, device_id: str = Depends(get_device_id), db: Session = Depends(get_db)):
    event = db.query(EventDB).filter(EventDB.id == event_id, EventDB.session_id == device_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    if req.status is not None:
        event.status = req.status
    if req.note is not None:
        event.note = req.note
    if req.title is not None:
        event.title = req.title
    if req.date is not None:
        event.date = req.date
    if req.time is not None:
        event.time = req.time
    # Re-check expiration when date or time changes
    if req.date is not None or req.time is not None:
        event.status = "expired" if _is_expired(event.date, event.time) else "open"
    db.commit()
    db.refresh(event)
    return {"status": "updated", "item": _db_obj_to_dict(event)}


@app.delete("/events/{event_id}")
def delete_event(event_id: int, device_id: str = Depends(get_device_id), db: Session = Depends(get_db)):
    event = db.query(EventDB).filter(EventDB.id == event_id, EventDB.session_id == device_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    db.delete(event)
    db.commit()
    return {"status": "deleted"}


# ── Bulk operations ──

@app.post("/tasks/bulk-update")
def bulk_update_tasks(
    req: BulkUpdateRequest,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    count = 0
    if req.ids:
        count = db.query(TaskDB).filter(TaskDB.id.in_(req.ids), TaskDB.session_id == device_id).update(
            {TaskDB.status: req.status}, synchronize_session=False
        )
        db.commit()
    return {"status": "updated", "count": count}


@app.post("/tasks/bulk-delete")
def bulk_delete_tasks(
    req: BulkDeleteRequest,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    count = 0
    if req.ids:
        count = db.query(TaskDB).filter(TaskDB.id.in_(req.ids), TaskDB.session_id == device_id).delete(
            synchronize_session=False
        )
        db.commit()
    return {"status": "deleted", "count": count}


@app.post("/events/bulk-update")
def bulk_update_events(
    req: BulkUpdateRequest,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    count = 0
    if req.ids:
        count = db.query(EventDB).filter(EventDB.id.in_(req.ids), EventDB.session_id == device_id).update(
            {EventDB.status: req.status}, synchronize_session=False
        )
        db.commit()
    return {"status": "updated", "count": count}


@app.post("/events/bulk-delete")
def bulk_delete_events(
    req: BulkDeleteRequest,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    count = 0
    if req.ids:
        count = db.query(EventDB).filter(EventDB.id.in_(req.ids), EventDB.session_id == device_id).delete(
            synchronize_session=False
        )
        db.commit()
    return {"status": "deleted", "count": count}


@app.post("/items/bulk-save", response_model=BulkItemSaveResponse)
def bulk_save_items(
    req: BulkItemSaveRequest,
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    tasks_saved = 0
    events_saved = 0
    errors = 0

    for item in req.items:
        try:
            if item.type == "task":
                _save_db_item(db, TaskDB, item, session_id=device_id)
                tasks_saved += 1
            elif item.type == "event":
                _save_db_item(db, EventDB, item, session_id=device_id)
                events_saved += 1
            else:
                errors += 1
        except Exception as exc:
            logger.warning("Failed to save item in bulk: %s", exc)
            db.rollback()
            errors += 1

    return BulkItemSaveResponse(
        status="saved",
        tasks_saved=tasks_saved,
        events_saved=events_saved,
        errors=errors,
    )


@app.post("/cleanup")
def cleanup_old_items(
    hours: int = Query(default=1, ge=1, le=168, description="Delete items older than this many hours"),
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    """Delete tasks and events older than the specified number of hours for this session.
    Defaults to 1 hour to enforce the temporary-buffer design."""
    cutoff = datetime.now().astimezone() - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()

    # Delete items with created_at older than cutoff, plus any legacy items with null created_at
    task_count = db.query(TaskDB).filter(
        TaskDB.session_id == device_id,
        (TaskDB.created_at < cutoff_iso) | (TaskDB.created_at == None)
    ).delete(synchronize_session=False)

    event_count = db.query(EventDB).filter(
        EventDB.session_id == device_id,
        (EventDB.created_at < cutoff_iso) | (EventDB.created_at == None)
    ).delete(synchronize_session=False)

    db.commit()
    total = task_count + event_count
    if total > 0:
        logger.info("Cleanup deleted %d tasks and %d events for session %s (older than %dh)", task_count, event_count, device_id[:8], hours)
    return {"status": "cleaned", "tasks_deleted": task_count, "events_deleted": event_count, "hours": hours}


# ── File upload limits ──
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB
_ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "application/pdf",
}
_ALLOWED_AUDIO_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/ogg",
}


def _normalize_content_type(ct: str | None) -> str | None:
    """Strip codec/parameters so 'audio/webm;codecs=opus' becomes 'audio/webm'."""
    if not ct:
        return None
    return ct.split(";")[0].strip().lower()


@app.post("/analyze-file", response_model=AnalyzeResponse)
async def analyze_file(
    file: UploadFile = File(...),
    device_id: str = Depends(get_device_id),
    provider: str | None = Depends(get_provider),
    api_key: str | None = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    if _normalize_content_type(file.content_type) not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}",
        )

    contents = await file.read()

    if len(contents) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 10 MB.",
        )

    try:
        quota_service = QuotaService(db)
        result = await _orchestrator.extract(
            contents,
            file.content_type,
            file.filename,
            session_id=device_id,
            quota_service=quota_service,
            provider=provider,
            api_key=api_key,
        )
        return AnalyzeResponse(
            items=result.items,
            quota_exceeded=result.quota_exceeded,
            quota_remaining=result.quota_remaining,
        )
    except Exception as exc:
        logger.exception("File analysis failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File analysis failed. Please try again later.",
        ) from exc


@app.post("/analyze-audio", response_model=AnalyzeResponse)
async def analyze_audio(
    file: UploadFile = File(...),
    device_id: str = Depends(get_device_id),
    provider: str | None = Depends(get_provider),
    api_key: str | None = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    if _normalize_content_type(file.content_type) not in _ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio type: {file.content_type}",
        )

    contents = await file.read()

    if len(contents) > _MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file too large. Maximum size is 25 MB.",
        )

    try:
        quota_service = QuotaService(db)
        result = await _orchestrator.extract(
            contents,
            file.content_type,
            file.filename,
            session_id=device_id,
            quota_service=quota_service,
            provider=provider,
            api_key=api_key,
        )
        return AnalyzeResponse(
            items=result.items,
            quota_exceeded=result.quota_exceeded,
            quota_remaining=result.quota_remaining,
        )
    except Exception as exc:
        logger.exception("Audio analysis failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audio analysis failed. Please try again later.",
        ) from exc


@app.get("/quota")
def get_quota(device_id: str = Depends(get_device_id), db: Session = Depends(get_db)):
    """Return current Gemini API quota status for this device."""
    try:
        quota_service = QuotaService(db)
        status_info = quota_service.get_status(device_id)
        return status_info
    except Exception as exc:
        logger.exception("Quota check failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Quota check failed.",
        ) from exc


@app.post("/enhance-item", response_model=EnhanceItemResponse)
async def enhance_item(
    req: EnhanceItemRequest,
    device_id: str = Depends(get_device_id),
    provider: str | None = Depends(get_provider),
    api_key: str | None = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """Refine a single poorly extracted item using the selected AI provider. Consumes 1 quota call."""
    quota_service = QuotaService(db)

    if not quota_service.can_use_gemini(device_id):
        return EnhanceItemResponse(
            item=req.item,
            quota_exceeded=True,
            quota_remaining=0,
        )

    try:
        ai_service = _orchestrator.get_ai_service(provider, api_key)
        refined = ai_service.refine_item(req.item, req.source_text)
        if refined is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Enhancement service temporarily unavailable. Please try again later.",
            )

        status_info = quota_service.increment_gemini(device_id)
        return EnhanceItemResponse(
            item=refined,
            quota_remaining=status_info["remaining"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Item enhancement failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Enhancement service temporarily unavailable. Please try again later.",
        ) from exc


@app.post("/enhance-item-file", response_model=EnhanceItemResponse)
async def enhance_item_file(
    file: UploadFile = File(...),
    item_json: str = Form(...),
    device_id: str = Depends(get_device_id),
    provider: str | None = Depends(get_provider),
    api_key: str | None = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """Refine a single poorly extracted item by sending the original file to AI vision. Consumes 1 quota call."""
    quota_service = QuotaService(db)

    if not quota_service.can_use_gemini(device_id):
        try:
            item_data = _json.loads(item_json)
            item = ExtractedItem(**item_data)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid item_json.",
            )
        return EnhanceItemResponse(
            item=item,
            quota_exceeded=True,
            quota_remaining=0,
        )

    try:
        item_data = _json.loads(item_json)
        item = ExtractedItem(**item_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid item_json: {exc}",
        ) from exc

    if _normalize_content_type(file.content_type) not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}",
        )

    contents = await file.read()
    if len(contents) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 10 MB.",
        )

    try:
        ai_service = _orchestrator.get_ai_service(provider, api_key)
        refined = ai_service.refine_item_with_vision(
            item, contents, file.content_type
        )
        if refined is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Enhancement service temporarily unavailable. Please try again later.",
            )

        status_info = quota_service.increment_gemini(device_id)
        return EnhanceItemResponse(
            item=refined,
            quota_remaining=status_info["remaining"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Vision item enhancement failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Enhancement service temporarily unavailable. Please try again later.",
        ) from exc


# ── Export ──

@app.get("/export/tasks/json")
def export_tasks_json(
    ids: List[int] = Query(default=None),
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(TaskDB).filter(TaskDB.session_id == device_id)
        if ids:
            query = query.filter(TaskDB.id.in_(ids))
        tasks = query.all()
        data = {
            "exported_at": datetime.now().astimezone().isoformat(),
            "count": len(tasks),
            "tasks": [_db_obj_to_dict(t) for t in tasks],
        }
        date_str = datetime.now().astimezone().strftime("%d%m%Y")
        return Response(
            content=_json.dumps(data, indent=2, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="snapcapture_tasks_{date_str}.json"'
            },
        )
    except Exception as exc:
        logger.exception("Task export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Export failed. Please try again later.",
        ) from exc


@app.get("/export/tasks/csv")
def export_tasks_csv(
    ids: List[int] = Query(default=None),
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    try:
        if ids:
            query = db.query(TaskDB).filter(TaskDB.id.in_(ids))
        else:
            query = db.query(TaskDB).filter(TaskDB.session_id == device_id)
        tasks = query.all()

        import io, csv
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Title", "Due Date", "Note", "Status", "Source"])
        for t in tasks:
            writer.writerow([
                t.title or "",
                t.due_date or "",
                t.note or "",
                t.status or "open",
                t.source or "",
            ])

        date_str = datetime.now().astimezone().strftime("%d%m%Y")
        return Response(
            content=out.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="snapcapture_tasks_{date_str}.csv"'
            },
        )
    except Exception as exc:
        logger.exception("Task CSV export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Export failed. Please try again later.",
        ) from exc


@app.get("/export/tasks/ics")
def export_tasks_ics(
    ids: List[int] = Query(default=None),
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    try:
        if ids:
            query = db.query(TaskDB).filter(TaskDB.id.in_(ids))
        else:
            query = db.query(TaskDB).filter(TaskDB.session_id == device_id)
        tasks = query.all()

        cal = Calendar()
        cal.add("prodid", "-//SnapCapture//BKlein Digital Labs//EN")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")
        cal.add("x-wr-calname", "SnapCapture Tasks")

        for t in tasks:
            todo = ICalTodo()
            todo.add("summary", t.title or "Untitled Task")
            todo.add("uid", f"snapcapture-task-{t.id}@bklein.digital")
            todo.add("dtstamp", datetime.now().astimezone())

            if t.due_date:
                # Try to parse due_date as datetime; skip if unparseable
                dt = _parse_event_datetime(t.due_date, None, t.original_date)[0]
                if dt:
                    todo.add("due", dt)

            if t.note:
                todo.add("description", t.note)

            if t.status == "done":
                todo.add("status", "COMPLETED")
            else:
                todo.add("status", "NEEDS-ACTION")

            cal.add_component(todo)

        date_str = datetime.now().astimezone().strftime("%d%m%Y")
        return Response(
            content=cal.to_ical(),
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="snapcapture_tasks_{date_str}.ics"'
            },
        )
    except Exception as exc:
        logger.exception("Task ICS export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Export failed. Please try again later.",
        ) from exc


@app.get("/export/events/ics")
def export_events_ics(
    ids: List[int] = Query(default=None),
    device_id: str = Depends(get_device_id),
    db: Session = Depends(get_db),
):
    try:
        if ids:
            query = db.query(EventDB).filter(EventDB.id.in_(ids))
        else:
            query = db.query(EventDB).filter(EventDB.session_id == device_id)
        events = query.all()

        cal = Calendar()
        cal.add("prodid", "-//SnapCapture//BKlein Digital Labs//EN")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")
        cal.add("x-wr-calname", "SnapCapture Events")

        for ev in events:
            ical_event = ICalEvent()
            ical_event.add("summary", ev.title or "Untitled Event")
            ical_event.add("uid", f"snapcapture-event-{ev.id}@bklein.digital")
            ical_event.add("dtstamp", datetime.now().astimezone())

            dt_start, dt_end = _parse_event_datetime(ev.date, ev.time, ev.original_date)
            if dt_start:
                ical_event.add("dtstart", dt_start)
                if dt_end:
                    ical_event.add("dtend", dt_end)
            else:
                # All-day event fallback — no usable date found
                ical_event.add("dtstart", datetime.now().astimezone().date())

            if ev.location:
                ical_event.add("location", ev.location)

            cal.add_component(ical_event)

        date_str = datetime.now().astimezone().strftime("%d%m%Y")
        return Response(
            content=cal.to_ical(),
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="snapcapture_events_{date_str}.ics"'
            },
        )
    except Exception as exc:
        logger.exception("Event export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Export failed. Please try again later.",
        ) from exc
