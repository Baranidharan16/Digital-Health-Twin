"""Database engine and session factory (SQLAlchemy 2.x).

SQLite is used for the local prototype. Models use only portable column
types, so switching ``DHT_DATABASE_URL`` to PostgreSQL requires no code change.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        path = database_url.removeprefix("sqlite:///")
        if path and path != ":memory:" and not database_url.startswith("sqlite://:"):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


class Database:
    def __init__(self, database_url: str) -> None:
        self.engine = make_engine(database_url)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        from backend.app import models  # noqa: F401 - register models

        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        from backend.app import models  # noqa: F401

        Base.metadata.drop_all(self.engine)

    def session(self) -> Session:
        return self.session_factory()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = self.session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
