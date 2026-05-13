"""SQLAlchemy engine + session factory cache."""
from __future__ import annotations

import logging
from pathlib import Path
from threading import RLock

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

logger = logging.getLogger(__name__)

_LOCK = RLock()
_ENGINES: dict[str, Engine] = {}
_FACTORIES: dict[str, sessionmaker[Session]] = {}


def _ensure_sqlite_dir(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw = url[len("sqlite:///"):]
    if not raw or raw == ":memory:":
        return
    Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)


def get_engine(url: str) -> Engine:
    """Get (or build + cache) the SQLAlchemy engine for ``url``."""
    with _LOCK:
        engine = _ENGINES.get(url)
        if engine is not None:
            return engine
        _ensure_sqlite_dir(url)
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        engine = create_engine(url, connect_args=connect_args, future=True)
        _ENGINES[url] = engine
        return engine


def get_session_factory(url: str) -> sessionmaker[Session]:
    """Get (or build + cache) a sessionmaker for ``url``."""
    with _LOCK:
        factory = _FACTORIES.get(url)
        if factory is not None:
            return factory
        engine = get_engine(url)
        factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        _FACTORIES[url] = factory
        return factory


def init_db(url: str) -> Engine:
    """Create tables (idempotent) and return the engine."""
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    logger.info("Initialised database at %s", url)
    return engine


def reset_caches() -> None:
    """Test helper — clear cached engines/factories (not normally called)."""
    with _LOCK:
        for engine in _ENGINES.values():
            engine.dispose()
        _ENGINES.clear()
        _FACTORIES.clear()
