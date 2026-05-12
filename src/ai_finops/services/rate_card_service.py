"""RateCardService — hot-reloads rate card YAML files from disk.

Per copilot-instructions.md §4 / §11 / §13:
  * Reload from disk on app start and every 60 minutes.
  * Flag ``stale_since`` when a file's effective_date is older than 7 days.
  * NEVER hardcode a price in Python — every price MUST come from here.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Rate cards we expect under ``rate_card_dir``.
RATE_CARD_FILES = {
    "per_seat": "per_seat.yaml",
    "copilot_credits": "copilot_credits.yaml",
    "azure_openai": "azure_openai.yaml",
    "foundry_agent_service": "foundry_agent_service.yaml",
    "ai_search": "ai_search.yaml",
    "azure_infrastructure": "azure_infrastructure.yaml",
}


@dataclass
class RateCardEntry:
    name: str
    data: dict[str, Any]
    effective_date: date | None
    loaded_at: datetime
    source_path: Path

    def is_stale(self, max_age_days: int) -> bool:
        if self.effective_date is None:
            return True
        return (date.today() - self.effective_date) > timedelta(days=max_age_days)


@dataclass
class RateCards:
    """Convenient typed access wrapper around the loaded YAML dicts."""

    per_seat: dict[str, Any] = field(default_factory=dict)
    copilot_credits: dict[str, Any] = field(default_factory=dict)
    azure_openai: dict[str, Any] = field(default_factory=dict)
    foundry_agent_service: dict[str, Any] = field(default_factory=dict)
    ai_search: dict[str, Any] = field(default_factory=dict)
    azure_infrastructure: dict[str, Any] = field(default_factory=dict)


class RateCardService:
    """Thread-safe loader/cache for the YAML rate cards."""

    def __init__(self, rate_card_dir: Path | str, stale_days: int = 7) -> None:
        self._dir = Path(rate_card_dir)
        self._stale_days = stale_days
        self._lock = threading.RLock()
        self._entries: dict[str, RateCardEntry] = {}
        self._cards = RateCards()
        self.load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load(self) -> None:
        """Read all rate card files from disk. Idempotent and thread-safe."""
        with self._lock:
            entries: dict[str, RateCardEntry] = {}
            cards = RateCards()
            for key, filename in RATE_CARD_FILES.items():
                path = self._dir / filename
                if not path.is_file():
                    logger.warning("Rate card file missing: %s", path)
                    continue
                with path.open("r", encoding="utf-8") as fh:
                    data: dict[str, Any] = yaml.safe_load(fh) or {}
                effective_date = self._parse_effective_date(data.get("effective_date"))
                entry = RateCardEntry(
                    name=key,
                    data=data,
                    effective_date=effective_date,
                    loaded_at=datetime.now(UTC),
                    source_path=path,
                )
                entries[key] = entry
                setattr(cards, key, data)
                if entry.is_stale(self._stale_days):
                    logger.warning(
                        "Rate card '%s' is stale (effective_date=%s, loaded_at=%s).",
                        key, effective_date, entry.loaded_at,
                    )
            self._entries = entries
            self._cards = cards
            logger.info("Loaded %d rate card files from %s", len(entries), self._dir)

    @staticmethod
    def _parse_effective_date(raw: Any) -> date | None:
        if raw is None:
            return None
        if isinstance(raw, date):
            return raw
        if isinstance(raw, datetime):
            return raw.date()
        try:
            return datetime.fromisoformat(str(raw)).date()
        except ValueError:
            logger.warning("Unparseable effective_date: %r", raw)
            return None

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    @property
    def cards(self) -> RateCards:
        with self._lock:
            return self._cards

    def get(self, key: str) -> dict[str, Any]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                raise KeyError(f"Unknown rate card: {key}")
            return entry.data

    def status(self) -> list[dict[str, Any]]:
        """Return health/refresh metadata for every rate card."""
        with self._lock:
            return [
                {
                    "name": e.name,
                    "effective_date": e.effective_date.isoformat() if e.effective_date else None,
                    "loaded_at": e.loaded_at.isoformat(),
                    "source_path": str(e.source_path),
                    "is_stale": e.is_stale(self._stale_days),
                    "stale_threshold_days": self._stale_days,
                }
                for e in self._entries.values()
            ]
