import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Resolve absolute path so the DB is stable regardless of cwd
_BASE_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _BASE_DIR / "snapcapture.db"

_db_path = os.getenv("DATABASE_PATH", str(_DEFAULT_DB_PATH))
DATABASE_URL = f"sqlite:///{_db_path}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
