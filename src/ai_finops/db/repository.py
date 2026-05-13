"""Repository for the AI FinOps cost ledger.

All API endpoints route through this class; it isolates SQLAlchemy
queries from FastAPI request handlers so we can unit-test them and
swap the DB engine without touching the API layer.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..domain.enums import Meter
from .models import (
    AgentRow,
    AnomalyRow,
    BudgetRow,
    CostEventRow,
    OptimisationRow,
    UntaggedSpendRow,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


def _d(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None:
        return ZERO
    return Decimal(str(v))


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


class Repository:
    """Synchronous repository wrapping a SQLAlchemy ``sessionmaker``."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------
    def upsert_agent(self, **fields: Any) -> dict[str, Any]:
        agent_id = fields.get("agent_id")
        if not agent_id:
            raise ValueError("upsert_agent requires agent_id")
        with self._sf() as s:
            row = s.get(AgentRow, agent_id)
            if row is None:
                row = AgentRow(**fields)
                s.add(row)
            else:
                for k, v in fields.items():
                    if k == "agent_id":
                        continue
                    if hasattr(row, k):
                        setattr(row, k, v)
                row.updated_at = _now()
            s.commit()
            s.refresh(row)
            return _row_to_dict(row)

    def list_agents(
        self,
        environment: str | None = None,
        cost_center: str | None = None,
        agent_type: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._sf() as s:
            stmt = select(AgentRow)
            if environment:
                stmt = stmt.where(AgentRow.environment == environment)
            if cost_center:
                stmt = stmt.where(AgentRow.cost_center == cost_center)
            if agent_type:
                stmt = stmt.where(AgentRow.agent_type == agent_type)
            stmt = stmt.order_by(AgentRow.agent_name)
            return [_row_to_dict(r) for r in s.scalars(stmt).all()]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._sf() as s:
            row = s.get(AgentRow, agent_id)
            return _row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # Cost events
    # ------------------------------------------------------------------
    def insert_cost_events(self, events: Iterable[Mapping[str, Any]]) -> int:
        count = 0
        with self._sf() as s:
            for ev in events:
                payload = dict(ev)
                payload.setdefault("id", f"ce-{uuid.uuid4().hex[:16]}")
                # Coerce decimals
                for f in ("cost_actual_usd", "cost_shadow_usd", "discount_applied_usd"):
                    if f in payload and payload[f] is not None:
                        payload[f] = _d(payload[f])
                # Strip timezone if present
                ts = payload.get("timestamp")
                if isinstance(ts, datetime) and ts.tzinfo is not None:
                    payload["timestamp"] = ts.astimezone(UTC).replace(tzinfo=None)
                s.add(CostEventRow(**payload))
                count += 1
            s.commit()
        return count

    def list_cost_events(
        self,
        limit: int = 100,
        offset: int = 0,
        meter: str | None = None,
        agent_id: str | None = None,
        cost_center: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        with self._sf() as s:
            stmt = select(CostEventRow)
            count_stmt = select(func.count()).select_from(CostEventRow)
            if meter:
                stmt = stmt.where(CostEventRow.meter == meter)
                count_stmt = count_stmt.where(CostEventRow.meter == meter)
            if agent_id:
                stmt = stmt.where(CostEventRow.agent_id == agent_id)
                count_stmt = count_stmt.where(CostEventRow.agent_id == agent_id)
            if cost_center:
                stmt = stmt.where(CostEventRow.cost_center == cost_center)
                count_stmt = count_stmt.where(CostEventRow.cost_center == cost_center)
            if since:
                stmt = stmt.where(CostEventRow.timestamp >= since)
                count_stmt = count_stmt.where(CostEventRow.timestamp >= since)
            if until:
                stmt = stmt.where(CostEventRow.timestamp <= until)
                count_stmt = count_stmt.where(CostEventRow.timestamp <= until)
            stmt = stmt.order_by(CostEventRow.timestamp.desc()).limit(limit).offset(offset)
            items = [_row_to_dict(r) for r in s.scalars(stmt).all()]
            total = int(s.scalar(count_stmt) or 0)
            return {"items": items, "limit": limit, "offset": offset, "total": total}

    # ------------------------------------------------------------------
    # Cost summary / trends / credits / licenses
    # ------------------------------------------------------------------
    def cost_summary(self) -> dict[str, Any]:
        with self._sf() as s:
            now = _now()
            month_start = datetime(now.year, now.month, 1)
            prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

            def _meter_sum(start: datetime, end: datetime, meter: str | None = None) -> Decimal:
                stmt = select(func.coalesce(func.sum(CostEventRow.cost_actual_usd), 0)).where(
                    CostEventRow.timestamp >= start, CostEventRow.timestamp < end
                )
                if meter:
                    stmt = stmt.where(CostEventRow.meter == meter)
                return _d(s.scalar(stmt))

            month_end = datetime(
                now.year + (1 if now.month == 12 else 0),
                1 if now.month == 12 else now.month + 1, 1,
            )
            total_month = _meter_sum(month_start, month_end)
            azure_month = _meter_sum(month_start, month_end, Meter.AZURE_CONSUMPTION.value)

            prev_total = _meter_sum(prev_month_start, month_start)
            mom_pct = float((total_month - prev_total) / prev_total * 100) if prev_total > 0 else 0.0

            credits_shadow_stmt = (
                select(func.coalesce(func.sum(CostEventRow.credits_shadow), 0))
                .where(CostEventRow.timestamp >= month_start)
            )
            credits_billed_stmt = (
                select(func.coalesce(func.sum(CostEventRow.credits_consumed), 0))
                .where(
                    CostEventRow.timestamp >= month_start,
                    CostEventRow.b2e_zero_rated.is_(False),
                    CostEventRow.meter == Meter.COPILOT_CREDITS.value,
                )
            )
            credits_billed = int(s.scalar(credits_billed_stmt) or 0)
            credits_shadow = int(s.scalar(credits_shadow_stmt) or 0)

            pack_size = 25000
            packs = max(1, (credits_billed + pack_size - 1) // pack_size) if credits_billed else 0
            pack_capacity = packs * pack_size
            pack_fill = (
                float(min(100.0, (credits_billed / pack_capacity) * 100))
                if pack_capacity
                else 0.0
            )

            top_model_stmt = (
                select(CostEventRow.model_id, func.sum(CostEventRow.cost_actual_usd).label("c"))
                .where(
                    CostEventRow.timestamp >= month_start,
                    CostEventRow.meter == Meter.AZURE_CONSUMPTION.value,
                    CostEventRow.model_id.isnot(None),
                )
                .group_by(CostEventRow.model_id)
                .order_by(func.sum(CostEventRow.cost_actual_usd).desc())
                .limit(1)
            )
            top_model_row = s.execute(top_model_stmt).first()
            top_model = top_model_row[0] if top_model_row else None

            opt_stmt = select(func.coalesce(func.sum(OptimisationRow.monthly_saving_usd), 0)).where(
                OptimisationRow.dismissed.is_(False)
            )
            opt_count_stmt = select(func.count()).select_from(OptimisationRow).where(
                OptimisationRow.dismissed.is_(False)
            )
            opt_total = _d(s.scalar(opt_stmt))
            opt_count = int(s.scalar(opt_count_stmt) or 0)

            budget_stmt = select(func.coalesce(func.sum(BudgetRow.amount_usd), 0)).where(
                BudgetRow.scope == "", BudgetRow.period == "monthly"
            )
            budget_amount = _d(s.scalar(budget_stmt))
            budget_pct = float(total_month / budget_amount * 100) if budget_amount > 0 else 0.0

            by_meter_stmt = (
                select(CostEventRow.meter, func.coalesce(func.sum(CostEventRow.cost_actual_usd), 0))
                .where(CostEventRow.timestamp >= month_start)
                .group_by(CostEventRow.meter)
            )
            by_meter = {row[0]: str(_d(row[1])) for row in s.execute(by_meter_stmt).all()}
            for m in (Meter.PER_SEAT.value, Meter.COPILOT_CREDITS.value, Meter.AZURE_CONSUMPTION.value):
                by_meter.setdefault(m, "0")

            return {
                "total_monthly_usd": str(total_month),
                "budget_amount_usd": str(budget_amount),
                "budget_pct": round(budget_pct, 2),
                "mom_change_pct": round(mom_pct, 2),
                "credits_billed": credits_billed,
                "credits_shadow": credits_shadow,
                "credits_pack_fill_pct": round(pack_fill, 2),
                "azure_consumption_usd": str(azure_month),
                "top_model": top_model,
                "optimisation_potential_usd": str(opt_total),
                "recommendation_count": opt_count,
                "by_meter": by_meter,
            }

    def cost_trends(self, months: int = 6) -> list[dict[str, Any]]:
        with self._sf() as s:
            now = _now()
            results: list[dict[str, Any]] = []
            year, month = now.year, now.month
            cursor_starts: list[datetime] = []
            for _ in range(months):
                cursor_starts.append(datetime(year, month, 1))
                month -= 1
                if month == 0:
                    month = 12
                    year -= 1
            cursor_starts.reverse()
            for start in cursor_starts:
                end_year = start.year + (1 if start.month == 12 else 0)
                end_month = 1 if start.month == 12 else start.month + 1
                end = datetime(end_year, end_month, 1)
                stmt = (
                    select(
                        CostEventRow.meter,
                        func.coalesce(func.sum(CostEventRow.cost_actual_usd), 0),
                    )
                    .where(CostEventRow.timestamp >= start, CostEventRow.timestamp < end)
                    .group_by(CostEventRow.meter)
                )
                buckets = {row[0]: _d(row[1]) for row in s.execute(stmt).all()}
                license_c = buckets.get(Meter.PER_SEAT.value, ZERO)
                credits_c = buckets.get(Meter.COPILOT_CREDITS.value, ZERO)
                azure_c = buckets.get(Meter.AZURE_CONSUMPTION.value, ZERO)
                results.append(
                    {
                        "period": start.strftime("%Y-%m"),
                        "license_cost_usd": str(license_c),
                        "credits_cost_usd": str(credits_c),
                        "azure_cost_usd": str(azure_c),
                        "total_cost_usd": str(license_c + credits_c + azure_c),
                    }
                )
            return results

    def credit_usage(self) -> dict[str, Any]:
        with self._sf() as s:
            now = _now()
            month_start = datetime(now.year, now.month, 1)
            base = select(CostEventRow).where(
                CostEventRow.meter == Meter.COPILOT_CREDITS.value,
                CostEventRow.timestamp >= month_start,
            )
            charged_stmt = select(
                func.coalesce(func.sum(CostEventRow.credits_consumed), 0)
            ).where(
                CostEventRow.meter == Meter.COPILOT_CREDITS.value,
                CostEventRow.timestamp >= month_start,
                CostEventRow.b2e_zero_rated.is_(False),
            )
            zero_rated_stmt = select(
                func.coalesce(func.sum(CostEventRow.credits_shadow), 0)
            ).where(
                CostEventRow.meter == Meter.COPILOT_CREDITS.value,
                CostEventRow.timestamp >= month_start,
                CostEventRow.b2e_zero_rated.is_(True),
            )
            cost_stmt = select(
                func.coalesce(func.sum(CostEventRow.cost_actual_usd), 0)
            ).where(
                CostEventRow.meter == Meter.COPILOT_CREDITS.value,
                CostEventRow.timestamp >= month_start,
            )
            charged = int(s.scalar(charged_stmt) or 0)
            zero_rated = int(s.scalar(zero_rated_stmt) or 0)
            cost_total = _d(s.scalar(cost_stmt))

            pack_size = 25000
            pack_unit_cost = Decimal("200")
            packs = (charged + pack_size - 1) // pack_size if charged else 0
            pack_credits_used = min(charged, packs * pack_size)
            pack_credits_remaining = max(0, packs * pack_size - charged)
            payg_overflow = max(0, charged - packs * pack_size)
            cost_pack = pack_unit_cost * Decimal(packs)
            cost_payg = Decimal("0.01") * Decimal(payg_overflow)

            by_agent_stmt = (
                select(
                    CostEventRow.agent_id,
                    CostEventRow.agent_name,
                    func.coalesce(func.sum(CostEventRow.credits_consumed), 0),
                    func.coalesce(func.sum(CostEventRow.credits_shadow), 0),
                    func.coalesce(func.sum(CostEventRow.cost_actual_usd), 0),
                )
                .where(
                    CostEventRow.meter == Meter.COPILOT_CREDITS.value,
                    CostEventRow.timestamp >= month_start,
                )
                .group_by(CostEventRow.agent_id, CostEventRow.agent_name)
                .order_by(func.sum(CostEventRow.credits_consumed).desc())
            )
            by_agent = [
                {
                    "agent_id": r[0],
                    "agent_name": r[1],
                    "credits_charged": int(r[2] or 0),
                    "credits_shadow": int(r[3] or 0),
                    "cost_usd": str(_d(r[4])),
                }
                for r in s.execute(by_agent_stmt).all()
            ]
            # ensure base used (lint friendliness)
            del base
            return {
                "total_credits_charged": charged,
                "total_credits_zero_rated": zero_rated,
                "pack_credits_used": pack_credits_used,
                "pack_credits_remaining": pack_credits_remaining,
                "payg_overflow_credits": payg_overflow,
                "cost_pack_usd": str(cost_pack),
                "cost_payg_usd": str(cost_payg),
                "cost_total_usd": str(cost_total),
                "by_agent": by_agent,
            }

    def license_summary(self) -> list[dict[str, Any]]:
        with self._sf() as s:
            now = _now()
            month_start = datetime(now.year, now.month, 1)
            stmt = (
                select(
                    CostEventRow.sku_id,
                    func.coalesce(func.sum(CostEventRow.assigned_users), 0),
                    func.coalesce(func.sum(CostEventRow.active_users_7d), 0),
                    func.coalesce(func.sum(CostEventRow.cost_actual_usd), 0),
                )
                .where(
                    CostEventRow.meter == Meter.PER_SEAT.value,
                    CostEventRow.timestamp >= month_start,
                    CostEventRow.sku_id.isnot(None),
                )
                .group_by(CostEventRow.sku_id)
            )
            results = []
            for sku, assigned, active, cost in s.execute(stmt).all():
                assigned_i = int(assigned or 0)
                active_i = int(active or 0)
                cost_d = _d(cost)
                util = float(active_i / assigned_i * 100) if assigned_i else 0.0
                per_seat = (cost_d / Decimal(assigned_i)) if assigned_i else ZERO
                results.append(
                    {
                        "license_type": sku,
                        "total_assigned": assigned_i,
                        "total_active": active_i,
                        "utilisation_pct": round(util, 2),
                        "cost_per_seat_usd": str(per_seat.quantize(Decimal("0.01"))),
                        "monthly_total_usd": str(cost_d),
                    }
                )
            return results

    # ------------------------------------------------------------------
    # Optimisations
    # ------------------------------------------------------------------
    def list_optimisations(
        self,
        category: str | None = None,
        effort: str | None = None,
        min_saving: Decimal | float | None = None,
        include_dismissed: bool = False,
    ) -> list[dict[str, Any]]:
        with self._sf() as s:
            stmt = select(OptimisationRow)
            if not include_dismissed:
                stmt = stmt.where(OptimisationRow.dismissed.is_(False))
            if category:
                stmt = stmt.where(OptimisationRow.category == category)
            if effort:
                stmt = stmt.where(OptimisationRow.implementation_effort == effort)
            if min_saving is not None:
                stmt = stmt.where(OptimisationRow.monthly_saving_usd >= _d(min_saving))
            stmt = stmt.order_by(OptimisationRow.monthly_saving_usd.desc())
            return [_row_to_dict(r) for r in s.scalars(stmt).all()]

    def dismiss_optimisation(self, opt_id: str, reason: str) -> dict[str, Any] | None:
        with self._sf() as s:
            row = s.get(OptimisationRow, opt_id)
            if row is None:
                return None
            row.dismissed = True
            row.dismissed_reason = reason
            row.dismissed_at = _now()
            s.commit()
            s.refresh(row)
            return _row_to_dict(row)

    def replace_recommendations(
        self, agent_id: str, recs: Sequence[Mapping[str, Any]]
    ) -> int:
        with self._sf() as s:
            s.execute(delete(OptimisationRow).where(OptimisationRow.agent_id == agent_id))
            count = 0
            for r in recs:
                payload = dict(r)
                payload.setdefault("id", f"opt-{uuid.uuid4().hex[:16]}")
                payload.setdefault("agent_id", agent_id)
                for f in ("monthly_saving_usd", "before_cost_usd", "after_cost_usd"):
                    if f in payload and payload[f] is not None:
                        payload[f] = _d(payload[f])
                s.add(OptimisationRow(**payload))
                count += 1
            s.commit()
            return count

    # ------------------------------------------------------------------
    # Budgets
    # ------------------------------------------------------------------
    def list_budgets(self) -> list[dict[str, Any]]:
        with self._sf() as s:
            now = _now()
            month_start = datetime(now.year, now.month, 1)
            results = []
            for row in s.scalars(select(BudgetRow).order_by(BudgetRow.created_at)).all():
                stmt = select(func.coalesce(func.sum(CostEventRow.cost_actual_usd), 0)).where(
                    CostEventRow.timestamp >= month_start
                )
                scope = (row.scope or "").strip()
                if scope.startswith("cost_center:"):
                    stmt = stmt.where(CostEventRow.cost_center == scope.split(":", 1)[1])
                elif scope.startswith("agent:"):
                    stmt = stmt.where(CostEventRow.agent_id == scope.split(":", 1)[1])
                elif scope.startswith("env:"):
                    stmt = stmt.where(CostEventRow.environment == scope.split(":", 1)[1])
                consumed = _d(s.scalar(stmt))
                pct = float(consumed / row.amount_usd * 100) if row.amount_usd > 0 else 0.0
                if pct >= 100:
                    status = "exceeded"
                elif pct >= float(row.alert_threshold_pct):
                    status = "warning"
                else:
                    status = "on_track"
                results.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "amount_usd": str(_d(row.amount_usd)),
                        "period": row.period,
                        "alert_threshold_pct": float(row.alert_threshold_pct),
                        "scope": row.scope,
                        "owner": row.owner,
                        "consumed_usd": str(consumed),
                        "consumed_pct": round(pct, 2),
                        "status": status,
                    }
                )
            return results

    def create_budget(self, **fields: Any) -> dict[str, Any]:
        payload = dict(fields)
        payload.setdefault("id", f"bud-{uuid.uuid4().hex[:12]}")
        if "amount_usd" in payload and payload["amount_usd"] is not None:
            payload["amount_usd"] = _d(payload["amount_usd"])
        with self._sf() as s:
            row = BudgetRow(**payload)
            s.add(row)
            s.commit()
            s.refresh(row)
            return _row_to_dict(row)

    # ------------------------------------------------------------------
    # Anomalies
    # ------------------------------------------------------------------
    def list_anomalies(
        self,
        severity: str | None = None,
        acknowledged: bool | None = None,
    ) -> list[dict[str, Any]]:
        with self._sf() as s:
            stmt = select(AnomalyRow)
            if severity:
                stmt = stmt.where(AnomalyRow.severity == severity)
            if acknowledged is not None:
                stmt = stmt.where(AnomalyRow.acknowledged.is_(acknowledged))
            stmt = stmt.order_by(AnomalyRow.detected_at.desc())
            return [_row_to_dict(r) for r in s.scalars(stmt).all()]

    def add_anomaly(self, **fields: Any) -> dict[str, Any]:
        payload = dict(fields)
        payload.setdefault("id", f"ano-{uuid.uuid4().hex[:12]}")
        for f in ("expected_cost_usd", "actual_cost_usd"):
            if f in payload and payload[f] is not None:
                payload[f] = _d(payload[f])
        with self._sf() as s:
            row = AnomalyRow(**payload)
            s.add(row)
            s.commit()
            s.refresh(row)
            return _row_to_dict(row)

    def acknowledge_anomaly(
        self, anomaly_id: str, action: str, by: str
    ) -> dict[str, Any] | None:
        with self._sf() as s:
            row = s.get(AnomalyRow, anomaly_id)
            if row is None:
                return None
            row.acknowledged = True
            row.acknowledged_action = action
            row.acknowledged_by = by
            row.acknowledged_at = _now()
            s.commit()
            s.refresh(row)
            return _row_to_dict(row)

    def replace_anomalies(self, anomalies: Sequence[Mapping[str, Any]]) -> int:
        with self._sf() as s:
            s.execute(delete(AnomalyRow))
            count = 0
            for a in anomalies:
                payload = dict(a)
                payload.setdefault("id", f"ano-{uuid.uuid4().hex[:12]}")
                for f in ("expected_cost_usd", "actual_cost_usd"):
                    if f in payload and payload[f] is not None:
                        payload[f] = _d(payload[f])
                s.add(AnomalyRow(**payload))
                count += 1
            s.commit()
            return count

    # ------------------------------------------------------------------
    # Untagged spend
    # ------------------------------------------------------------------
    def insert_untagged_rows(self, rows: Iterable[Mapping[str, Any]]) -> int:
        count = 0
        with self._sf() as s:
            for r in rows:
                payload = dict(r)
                payload.setdefault("id", f"unt-{uuid.uuid4().hex[:12]}")
                if "cost_usd" in payload and payload["cost_usd"] is not None:
                    payload["cost_usd"] = _d(payload["cost_usd"])
                s.add(UntaggedSpendRow(**payload))
                count += 1
            s.commit()
        return count

    def list_untagged_rows(self) -> list[dict[str, Any]]:
        with self._sf() as s:
            stmt = select(UntaggedSpendRow).order_by(UntaggedSpendRow.detected_at.desc())
            return [_row_to_dict(r) for r in s.scalars(stmt).all()]

    # ------------------------------------------------------------------
    # FOCUS export
    # ------------------------------------------------------------------
    def focus_rows(self, since: datetime | None = None) -> list[dict[str, Any]]:
        with self._sf() as s:
            stmt = select(CostEventRow)
            if since:
                stmt = stmt.where(CostEventRow.timestamp >= since)
            rows: list[dict[str, Any]] = []
            for r in s.scalars(stmt).all():
                if r.meter == Meter.COPILOT_CREDITS.value:
                    qty = r.credits_consumed or 0
                    unit = "credits"
                elif r.meter == Meter.AZURE_CONSUMPTION.value:
                    qty = (r.tokens_input or 0) + (r.tokens_output or 0)
                    unit = "tokens"
                else:
                    qty = r.assigned_users or 0
                    unit = "seats"
                service_name = r.azure_service or r.meter
                category = "AI and Machine Learning"
                rows.append(
                    {
                        "BillingPeriodStart": r.focus_billing_period or "",
                        "ChargePeriodStart": r.timestamp.isoformat() if r.timestamp else "",
                        "BilledCost": str(_d(r.cost_actual_usd)),
                        "EffectiveCost": str(_d(r.cost_actual_usd) - _d(r.discount_applied_usd)),
                        "ServiceName": service_name,
                        "ServiceCategory": category,
                        "ResourceId": r.azure_resource_id or "",
                        "ResourceName": r.agent_name or "",
                        "ResourceType": r.agent_type or "",
                        "Tags.AgentId": r.agent_id or "",
                        "Tags.CostCenter": r.cost_center or "",
                        "Tags.Owner": r.owner or "",
                        "Tags.Environment": r.environment or "",
                        "UsageQuantity": qty,
                        "UsageUnit": unit,
                    }
                )
            return rows

    # ------------------------------------------------------------------
    # Convenience: distinct azure services from recent cost events
    # ------------------------------------------------------------------
    def recent_azure_services(self, since: datetime) -> list[str]:
        with self._sf() as s:
            stmt = (
                select(CostEventRow.azure_service)
                .where(
                    CostEventRow.timestamp >= since,
                    CostEventRow.meter == Meter.AZURE_CONSUMPTION.value,
                    CostEventRow.azure_service.isnot(None),
                )
                .distinct()
            )
            return [r for r in s.scalars(stmt).all() if r]

    # ------------------------------------------------------------------
    # Aggregations used by anomaly detector
    # ------------------------------------------------------------------
    def daily_token_totals(self, days: int = 30) -> dict[tuple[str, str], int]:
        """Return {(date_iso, agent_id): total_tokens} for the last ``days`` days."""
        since = _now() - timedelta(days=days)
        with self._sf() as s:
            stmt = (
                select(
                    func.date(CostEventRow.timestamp),
                    CostEventRow.agent_id,
                    func.coalesce(func.sum(CostEventRow.tokens_input), 0),
                    func.coalesce(func.sum(CostEventRow.tokens_output), 0),
                )
                .where(
                    CostEventRow.timestamp >= since,
                    CostEventRow.meter == Meter.AZURE_CONSUMPTION.value,
                )
                .group_by(func.date(CostEventRow.timestamp), CostEventRow.agent_id)
            )
            out: dict[tuple[str, str], int] = {}
            for d, agent_id, ti, to in s.execute(stmt).all():
                out[(str(d), agent_id)] = int(ti or 0) + int(to or 0)
            return out

    def credit_totals_per_agent(self, days: int) -> dict[str, int]:
        since = _now() - timedelta(days=days)
        with self._sf() as s:
            stmt = (
                select(
                    CostEventRow.agent_id,
                    func.coalesce(func.sum(CostEventRow.credits_consumed), 0),
                )
                .where(
                    CostEventRow.timestamp >= since,
                    CostEventRow.meter == Meter.COPILOT_CREDITS.value,
                )
                .group_by(CostEventRow.agent_id)
            )
            return {r[0]: int(r[1] or 0) for r in s.execute(stmt).all()}

    def invocation_count_per_agent(self, days: int) -> dict[str, int]:
        since = _now() - timedelta(days=days)
        with self._sf() as s:
            stmt = (
                select(CostEventRow.agent_id, func.count())
                .where(CostEventRow.timestamp >= since)
                .group_by(CostEventRow.agent_id)
            )
            return {r[0]: int(r[1] or 0) for r in s.execute(stmt).all()}

    # ------------------------------------------------------------------
    # Bulk helpers used by seed CLI
    # ------------------------------------------------------------------
    def truncate_all(self) -> None:
        with self._sf() as s:
            for tbl in (
                AnomalyRow,
                OptimisationRow,
                BudgetRow,
                UntaggedSpendRow,
                CostEventRow,
                AgentRow,
            ):
                s.execute(delete(tbl))
            s.commit()

    def grouped_credits_by_agent_for_month(self) -> dict[str, int]:
        """Sum of consumed credits per agent for the current month."""
        now = _now()
        month_start = datetime(now.year, now.month, 1)
        with self._sf() as s:
            stmt = (
                select(
                    CostEventRow.agent_id,
                    func.coalesce(func.sum(CostEventRow.credits_consumed), 0),
                )
                .where(
                    CostEventRow.timestamp >= month_start,
                    CostEventRow.meter == Meter.COPILOT_CREDITS.value,
                )
                .group_by(CostEventRow.agent_id)
            )
            return {r[0]: int(r[1] or 0) for r in s.execute(stmt).all()}


def _grouped_by_two(items: Iterable[Any], key1: str, key2: str) -> dict[tuple, list]:
    out: dict[tuple, list] = defaultdict(list)
    for it in items:
        out[(it[key1], it[key2])].append(it)
    return out
