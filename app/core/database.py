"""SQLAlchemy 2.x database infrastructure.

SQLite-specific engine options stay in this module so Domain and API
code remain database-agnostic.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_directory(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return
    database = url.database
    if not database or database == ":memory:":
        return
    db_path = Path(database)
    if db_path.parent and str(db_path.parent) not in {".", ""}:
        db_path.parent.mkdir(parents=True, exist_ok=True)


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _build_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    _ensure_sqlite_directory(database_url)
    kwargs: dict = {}
    if url.get_backend_name() == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
        if url.database == ":memory:":
            kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)
    _enable_sqlite_foreign_keys(engine)
    return engine


engine = _build_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection(db: Session) -> bool:
    db.execute(text("SELECT 1"))
    return True
