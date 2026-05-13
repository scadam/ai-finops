"""Coordinator that runs ingestion jobs against the Repository.

Every ``run_*`` method follows the same shape:

* receives a puller instance (typically built by :class:`MicrosoftAuthFactory`),
* runs ``fetch`` then ``normalise``,
* writes via the matching ``Repository`` method (which enforces
  ``source_system`` and rejects unattributed rows),
* records an :class:`IngestionRunRow` so the ``GET /api/v1/data-sources``
  endpoint can render last-success time and SDK call.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..db import Repository

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    job: str
    sdk_call: str = ""
    rows_in: int = 0
    rows_written: int = 0
    untagged_rows: int = 0
    error: str | None = None
    skipped: bool = False

    @property
    def status(self) -> str:
        if self.skipped:
            return "skipped"
        if self.error:
            return "error"
        return "ok"


def _sdk_call(puller: Any, default: str = "") -> str:
    return str(getattr(puller, "sdk_call", default) or default)


class IngestionRunner:
    """Wire pullers/importers to the persistence layer."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    # ==================================================================
    # Existing pullers
    # ==================================================================
    def run_credits(self, puller: Any) -> IngestionResult:
        result = IngestionResult(job="graph_credits", sdk_call=_sdk_call(puller))
        try:
            raw = puller.fetch()
            events = list(puller.normalise(raw))
            result.rows_in = len(raw)
            result.rows_written = self._repo.insert_cost_events(events)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Credits ingestion failed: %s", exc)
            result.error = str(exc)
        self._record(result)
        return result

    def run_licenses(self, puller: Any) -> IngestionResult:
        result = IngestionResult(job="graph_licenses", sdk_call=_sdk_call(puller))
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
        self._record(result)
        return result

    def run_focus(self, importer: Any, source: Any) -> IngestionResult:
        result = IngestionResult(job="azure_focus", sdk_call="FOCUS CSV importer")
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
        self._record(result)
        return result

    # ==================================================================
    # Plug-and-play SDK pullers (Part 1)
    # ==================================================================
    def run_agents(self, directory_puller: Any, usage_puller: Any | None = None) -> IngestionResult:
        result = IngestionResult(job="agent365", sdk_call=_sdk_call(directory_puller))
        try:
            raw = directory_puller.fetch()
            agent_rows = list(directory_puller.normalise_agents(raw))
            for ar in agent_rows:
                self._repo.upsert_agent(**ar)
            result.rows_in = len(raw)
            result.rows_written = len(agent_rows)
            owner_rows: list[dict[str, Any]] = []
            for ar in agent_rows:
                owners = directory_puller.fetch_owners(ar["agent_id"])
                owner_rows.extend(directory_puller.normalise_owners(ar["agent_id"], owners))
            if owner_rows:
                self._repo.upsert_agent_owners(owner_rows)
            if usage_puller is not None:
                usage_raw = usage_puller.fetch()
                events = list(usage_puller.normalise(usage_raw))
                if events:
                    written = self._repo.insert_cost_events(events)
                    result.rows_written += written
                    result.rows_in += len(usage_raw)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent365 ingestion failed: %s", exc)
            result.error = str(exc)
        self._record(result)
        return result

    def run_entra_directory(self, puller: Any) -> IngestionResult:
        result = IngestionResult(job="entra_directory", sdk_call=_sdk_call(puller))
        try:
            skus = puller.fetch_subscribed_skus()
            users = puller.fetch_users_with_signin()
            pop_rows = list(puller.normalise_licensed_population(skus, users))
            result.rows_in = len(users)
            result.rows_written = self._repo.insert_licensed_population(pop_rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Entra directory ingestion failed: %s", exc)
            result.error = str(exc)
        self._record(result)
        return result

    def run_purview(self, puller: Any) -> IngestionResult:
        result = IngestionResult(job="purview", sdk_call=_sdk_call(puller))
        try:
            labels = puller.fetch_sensitivity_labels()
            dlp = puller.fetch_dlp_policies()
            classifications = puller.fetch_classifications()
            rows = list(puller.normalise_labels(labels, dlp, classifications))
            result.rows_in = len(labels)
            result.rows_written = self._repo.upsert_sensitivity_labels(rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Purview ingestion failed: %s", exc)
            result.error = str(exc)
        self._record(result)
        return result

    def run_defender(self, puller: Any) -> IngestionResult:
        result = IngestionResult(job="defender", sdk_call=_sdk_call(puller))
        try:
            alerts = puller.fetch_alerts()
            rows = list(puller.normalise_alerts(alerts))
            try:
                scores = puller.fetch_secure_scores()
                rows.extend(puller.normalise_secure_score(scores))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Secure-score fetch failed: %s", exc)
            result.rows_in = len(alerts)
            result.rows_written = self._repo.insert_risk_signals(rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Defender ingestion failed: %s", exc)
            result.error = str(exc)
        self._record(result)
        return result

    def run_power_platform(self, puller: Any) -> IngestionResult:
        result = IngestionResult(job="power_platform", sdk_call=_sdk_call(puller))
        try:
            envs = puller.fetch_environments()
            dlp = puller.fetch_dlp_policies()
            rows = list(puller.normalise_environments(envs, dlp))
            result.rows_in = len(envs)
            result.rows_written = self._repo.upsert_power_platform_environments(rows)
            credit_events: list[dict[str, Any]] = []
            for env in rows:
                cap = puller.fetch_capacity(env["environment_id"])
                credit_events.extend(
                    puller.normalise_capacity_events(env["environment_id"], cap)
                )
            if credit_events:
                self._repo.insert_cost_events(credit_events)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Power Platform ingestion failed: %s", exc)
            result.error = str(exc)
        self._record(result)
        return result

    def run_azure_inventory(self, puller: Any) -> IngestionResult:
        result = IngestionResult(job="azure_inventory", sdk_call=_sdk_call(puller))
        try:
            raw = puller.fetch()
            rows = list(puller.normalise(raw))
            result.rows_in = len(raw)
            result.rows_written = self._repo.upsert_azure_inventory(rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Azure inventory ingestion failed: %s", exc)
            result.error = str(exc)
        self._record(result)
        return result

    def run_cost_management(self, puller: Any, importer: Any | None = None) -> IngestionResult:
        result = IngestionResult(job="cost_management", sdk_call=_sdk_call(puller))
        try:
            from .azure_focus_importer import FocusImporter

            importer = importer or FocusImporter(source_system=puller.source_system)
            adapters = puller.fetch()
            tagged, untagged = importer.split_tagged(adapters)
            events = list(importer.to_cost_events(tagged))
            untagged_rows = list(importer.to_untagged_rows(untagged))
            result.rows_in = len(adapters)
            result.rows_written = self._repo.insert_cost_events(events)
            result.untagged_rows = self._repo.insert_untagged_rows(untagged_rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Cost Management ingestion failed: %s", exc)
            result.error = str(exc)
        self._record(result)
        return result

    # ==================================================================
    # Fan-out helper used by /api/v1/ingestion/run
    # ==================================================================
    def run_enabled(self, jobs: dict[str, Any]) -> list[IngestionResult]:
        """Run only the pullers explicitly enabled by the caller.

        ``jobs`` is a mapping of job-name -> kwargs dict for the matching
        ``run_*`` method. Unknown job names are skipped with an error.
        """
        method_map = {
            "agent365": "run_agents",
            "entra_directory": "run_entra_directory",
            "purview": "run_purview",
            "defender": "run_defender",
            "power_platform": "run_power_platform",
            "azure_inventory": "run_azure_inventory",
            "cost_management": "run_cost_management",
            "graph_credits": "run_credits",
            "graph_licenses": "run_licenses",
        }
        results: list[IngestionResult] = []
        for job, kwargs in jobs.items():
            method_name = method_map.get(job)
            if not method_name:
                results.append(IngestionResult(job=job, error=f"Unknown job: {job}"))
                continue
            method = getattr(self, method_name)
            try:
                results.append(method(**kwargs))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Job %s failed: %s", job, exc)
                results.append(IngestionResult(job=job, error=str(exc)))
        return results

    # ==================================================================
    def _record(self, result: IngestionResult) -> None:
        try:
            self._repo.record_ingestion_run(
                job=result.job,
                sdk_call=result.sdk_call,
                rows_in=result.rows_in,
                rows_written=result.rows_written,
                untagged_rows=result.untagged_rows,
                status=result.status,
                error=result.error,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not record ingestion run for %s: %s", result.job, exc)
