"""Coordinator that runs ingestion jobs against the Repository."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..db import Repository

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    job: str
    rows_in: int = 0
    rows_written: int = 0
    untagged_rows: int = 0
    error: str | None = None


class IngestionRunner:
    """Wire pullers/importers to the persistence layer."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    def run_credits(self, puller: Any) -> IngestionResult:
        result = IngestionResult(job="graph_credits")
        try:
            raw = puller.fetch()
            events = list(puller.normalise(raw))
            result.rows_in = len(raw)
            result.rows_written = self._repo.insert_cost_events(events)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Credits ingestion failed: %s", exc)
            result.error = str(exc)
        return result

    def run_licenses(self, puller: Any) -> IngestionResult:
        result = IngestionResult(job="graph_licenses")
        try:
            skus = puller.fetch_skus()
            try:
                counts = puller.fetch_active_user_counts()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Active user counts unavailable: %s", exc)
                counts = {}
            events = list(puller.normalise(skus, counts))
            result.rows_in = len(skus)
            result.rows_written = self._repo.insert_cost_events(events)
        except Exception as exc:  # noqa: BLE001
            logger.exception("License ingestion failed: %s", exc)
            result.error = str(exc)
        return result

    def run_focus(self, importer: Any, source: Any) -> IngestionResult:
        result = IngestionResult(job="azure_focus")
        try:
            rows = importer.parse(source)
            tagged, untagged = importer.split_tagged(rows)
            events = list(importer.to_cost_events(tagged))
            untagged_rows = list(importer.to_untagged_rows(untagged))
            result.rows_in = len(rows)
            result.rows_written = self._repo.insert_cost_events(events)
            result.untagged_rows = self._repo.insert_untagged_rows(untagged_rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("FOCUS ingestion failed: %s", exc)
            result.error = str(exc)
        return result
