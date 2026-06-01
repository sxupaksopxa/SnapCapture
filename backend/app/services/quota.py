import logging
import os
from datetime import datetime

from sqlalchemy.orm import Session

from app.db_models import ApiUsageDB

logger = logging.getLogger(__name__)

_DEFAULT_DAILY_QUOTA = int(os.getenv("DAILY_GEMINI_QUOTA", "30"))


class QuotaService:
    """Tracks per-user daily Gemini API usage."""

    def __init__(self, db: Session, quota_limit: int | None = None) -> None:
        self.db = db
        self.quota_limit = quota_limit or _DEFAULT_DAILY_QUOTA

    def _today(self) -> str:
        return datetime.now().astimezone().strftime("%Y-%m-%d")

    def _get_or_create_record(self, session_id: str) -> ApiUsageDB:
        today = self._today()
        record = (
            self.db.query(ApiUsageDB)
            .filter(ApiUsageDB.session_id == session_id, ApiUsageDB.date == today)
            .first()
        )
        if not record:
            record = ApiUsageDB(
                session_id=session_id,
                date=today,
                gemini_calls=0,
                local_calls=0,
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
        return record

    def get_status(self, session_id: str) -> dict:
        """Return current quota status for a session."""
        record = self._get_or_create_record(session_id)
        remaining = max(0, self.quota_limit - record.gemini_calls)
        return {
            "used_today": record.gemini_calls,
            "limit": self.quota_limit,
            "remaining": remaining,
            "date": record.date,
        }

    def can_use_gemini(self, session_id: str) -> bool:
        """Check whether the session still has Gemini quota left."""
        status = self.get_status(session_id)
        return status["remaining"] > 0

    def increment_gemini(self, session_id: str) -> dict:
        """Consume one Gemini call. Returns updated status."""
        record = self._get_or_create_record(session_id)
        record.gemini_calls += 1
        self.db.commit()
        self.db.refresh(record)
        remaining = max(0, self.quota_limit - record.gemini_calls)
        logger.info("Quota: session=%s gemini_calls=%d remaining=%d", session_id, record.gemini_calls, remaining)
        return {
            "used_today": record.gemini_calls,
            "limit": self.quota_limit,
            "remaining": remaining,
            "date": record.date,
        }

    def increment_local(self, session_id: str) -> None:
        """Log a local extraction (no quota consumed)."""
        record = self._get_or_create_record(session_id)
        record.local_calls += 1
        self.db.commit()
