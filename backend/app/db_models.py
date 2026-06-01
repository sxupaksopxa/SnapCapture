from sqlalchemy import Column, Float, Integer, String, Boolean, Index

from app.database import Base


class ApiUsageDB(Base):
    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    gemini_calls = Column(Integer, default=0, nullable=False)
    local_calls = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("idx_api_usage_session_date", "session_id", "date"),
    )


class TaskDB(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    # user_id is reserved for future user-account support; session_id is the current isolation key.
    user_id = Column(String, default="1", nullable=False)
    session_id = Column(String, nullable=False, index=True)

    title = Column(String, nullable=False)

    status = Column(String, default="open", nullable=False)

    original_date = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    date = Column(String, nullable=True)
    time = Column(String, nullable=True)

    location = Column(String, nullable=True)
    note = Column(String, nullable=True)

    source = Column(String, nullable=True)

    created_at = Column(String, nullable=True)
    updated_at = Column(String, nullable=True)
    expires_at = Column(String, nullable=True)
    exported_at = Column(String, nullable=True)

    confidence = Column(Float, default=0.0)


class EventDB(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    # user_id is reserved for future user-account support; session_id is the current isolation key.
    user_id = Column(String, default="1", nullable=False)
    session_id = Column(String, nullable=False, index=True)

    title = Column(String, nullable=False)

    status = Column(String, default="open", nullable=False)

    original_date = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    date = Column(String, nullable=True)
    time = Column(String, nullable=True)

    location = Column(String, nullable=True)
    note = Column(String, nullable=True)

    source = Column(String, nullable=True)

    created_at = Column(String, nullable=True)
    updated_at = Column(String, nullable=True)
    expires_at = Column(String, nullable=True)
    exported_at = Column(String, nullable=True)

    confidence = Column(Float, default=0.0)
