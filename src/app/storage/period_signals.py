"""Storage for Period AI Signals (017): load the input of a period, upsert and read reports.

Reads the 006 tables (snapshots, coverage, evidence) and writes only `period_signal_*`
(signals_period.md, Invariants).
"""
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Row, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.daily.signals_entities import Reconciliation, reconcile
from app.core.daily.signals_extract import EXTRACTION_VERSION
from app.core.daily.signals_model import DayCoverage
from app.core.periodic.period_model import (
    PeriodInput,
    PreviousPeriod,
    period_days,
    previous_start,
)
from app.storage.daily_signals import DailySignalRepo
from app.storage.models_sql import (
    AIEntity,
    DailySignalReport,
    PeriodSignalBrief,
    PeriodSignalReport,
    SignalMention,
)

LOGGER = logging.getLogger(__name__)

# The helper path of the weekly risers needs the 7 days before the period (14 days in total).
LOOKBACK_DAYS = 7


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class PeriodContext:
    """Run-wide reads shared by every period of one run (one reconciliation, one coverage)."""
    result: Reconciliation
    evidence: Mapping[int, SignalMention]
    coverage: Mapping[date, DayCoverage]
    entity_ids: Mapping[str, int]


class PeriodSignalRepo:
    def __init__(self, session: Session, *, comparable_from: date,
                 publisher_overrides: Mapping[str, str] | None = None) -> None:
        self.session = session
        self.comparable_from = comparable_from
        self.daily = DailySignalRepo(session, comparable_from=comparable_from,
                                     publisher_overrides=publisher_overrides)

    # Input --------------------------------------------------------------------------------------
    def context(self) -> PeriodContext:
        """Reconcile the stored evidence in memory (nothing is persisted) and read coverage."""
        evidence, rows = self.daily.load_evidence()
        result = reconcile(evidence, self.daily.overrides())
        ids: dict[str, int] = dict(self.session.execute(  # type: ignore[arg-type]
            select(AIEntity.entity_key, AIEntity.id)).all())
        return PeriodContext(result=result, evidence=rows, coverage=self.daily.coverage(),
                             entity_ids=ids)

    def snapshots(self, days: list[date]) -> dict[date, dict[str, Any]]:
        """Stored daily payloads of the days; an unreadable payload counts as no snapshot."""
        out: dict[date, dict[str, Any]] = {}
        rows = self.session.execute(select(DailySignalReport.report_date, DailySignalReport.payload)
                                    .where(DailySignalReport.report_date.in_(days)))
        for day, payload in rows:
            try:
                data = json.loads(payload)
            except (ValueError, TypeError):
                LOGGER.error("period_signals_snapshot_unreadable report_date=%s", day.isoformat())
                continue
            if isinstance(data, dict):
                out[day] = data
        return out

    def previous(self, kind: str, start: date) -> PreviousPeriod | None:
        """The stored previous period of the same kind, or None (missing or unreadable)."""
        row = self.get_report(kind, previous_start(kind, start))
        if row is None:
            return None
        try:
            payload = json.loads(row.payload)
            return PreviousPeriod(
                status=row.status, publishers=int(payload["coverage"]["publishers"]),
                event_stories={str(k): int(v) for k, v in
                               payload["event_mix"]["stories_by_type"].items()})
        except (ValueError, TypeError, KeyError, AttributeError):
            LOGGER.error("period_signals_previous_unreadable kind=%s start=%s", kind,
                         row.period_start.isoformat())
            return None

    def load_input(self, kind: str, start: date, *, ctx: PeriodContext | None = None,
                   generated_at: datetime | None = None) -> PeriodInput:
        """Input of one period: its days plus the 7 days before (helper path), the stored
        snapshots, coverage, evidence and the stored previous period."""
        ctx = ctx or self.context()
        probe = PeriodInput(kind=kind, start=start, snapshots={}, coverage={}, observations={},
                            entities={}, entity_ids={}, extraction_version=EXTRACTION_VERSION,
                            generated_at=generated_at or _now(),
                            comparable_from=self.comparable_from)
        days = probe.days
        wanted = [days[0] - timedelta(days=i) for i in range(LOOKBACK_DAYS, 0, -1)] + days
        observations = self.daily.observations(ctx.result, ctx.evidence, wanted)
        return PeriodInput(
            kind=kind, start=start, snapshots=self.snapshots(days),
            coverage={d: c for d, c in ctx.coverage.items() if d in set(wanted)},
            observations=observations, entities=ctx.result.entities,
            entity_ids=ctx.entity_ids, extraction_version=EXTRACTION_VERSION,
            generated_at=probe.generated_at, comparable_from=self.comparable_from,
            previous=self.previous(kind, start))

    # Reports ------------------------------------------------------------------------------------
    def get_report(self, kind: str, start: date) -> PeriodSignalReport | None:
        return self.session.scalar(select(PeriodSignalReport).where(
            PeriodSignalReport.period_kind == kind, PeriodSignalReport.period_start == start))

    def save_report(self, payload: Mapping[str, Any], digest: str) -> bool:
        """Upsert one period; False (and no write) when the stored payload hash is the same."""
        kind, start = str(payload["period_kind"]), date.fromisoformat(payload["period_start"])
        row = self.get_report(kind, start)
        if row is not None and row.payload_hash == digest:
            return False
        values = {"period_end": date.fromisoformat(payload["period_end"]),
                  "methodology_version": str(payload["methodology_version"]),
                  "extraction_version": str(payload["extraction_version"]),
                  "status": str(payload["status"]), "payload_hash": digest,
                  "thresholds": json.dumps(payload["thresholds"], sort_keys=True),
                  "payload": json.dumps(payload, sort_keys=True),
                  "coverage": json.dumps(payload["coverage"], sort_keys=True),
                  "updated_at": _now()}
        if row is None:
            try:
                with self.session.begin_nested():
                    self.session.add(PeriodSignalReport(
                        period_kind=kind, period_start=start, created_at=_now(), **values))
                    self.session.flush()
                return True
            except IntegrityError:
                row = self.get_report(kind, start)
                if row is None:
                    raise
        for key, value in values.items():
            setattr(row, key, value)
        self.session.flush()
        return True

    def latest(self, kind: str, statuses: tuple[str, ...] | None = None
               ) -> PeriodSignalReport | None:
        query = select(PeriodSignalReport).where(PeriodSignalReport.period_kind == kind)
        if statuses is not None:
            query = query.where(PeriodSignalReport.status.in_(statuses))
        return self.session.scalar(query.order_by(PeriodSignalReport.period_start.desc()).limit(1))

    def index(self, kind: str | None = None) -> list[Row[Any]]:
        """Stored periods, newest first (small columns only; payloads are not loaded)."""
        query = select(
            PeriodSignalReport.period_kind, PeriodSignalReport.period_start,
            PeriodSignalReport.period_end, PeriodSignalReport.status,
            PeriodSignalReport.updated_at)
        if kind is not None:
            query = query.where(PeriodSignalReport.period_kind == kind)
        return list(self.session.execute(query.order_by(
            PeriodSignalReport.period_start.desc(), PeriodSignalReport.period_kind)))

    # Briefs -------------------------------------------------------------------------------------
    def digest_items(self, kind: str, start: date) -> list[dict[str, str]]:
        """Published digest items of the period days, day by day (brief input)."""
        return [item for day in period_days(kind, start) for item in self.daily.digest_items(day)]

    def get_brief(self, kind: str, start: date) -> PeriodSignalBrief | None:
        return self.session.scalar(select(PeriodSignalBrief).where(
            PeriodSignalBrief.period_kind == kind, PeriodSignalBrief.period_start == start))

    def save_brief(self, kind: str, start: date, *, brief_version: str, model: str,
                   input_hash: str, status: str, payload: Mapping[str, Any],
                   reason: str | None = None) -> PeriodSignalBrief:
        """Insert or replace the period's brief row (same upsert pattern as `save_report`)."""
        if status not in ("ok", "invalid"):
            raise ValueError(status)
        values = {"brief_version": brief_version, "model": model, "input_hash": input_hash,
                  "status": status, "reason": reason,
                  "payload": json.dumps(dict(payload), sort_keys=True), "updated_at": _now()}
        row = self.get_brief(kind, start)
        if row is None:
            try:
                with self.session.begin_nested():
                    row = PeriodSignalBrief(period_kind=kind, period_start=start,
                                            created_at=_now(), **values)
                    self.session.add(row)
                    self.session.flush()
                return row
            except IntegrityError:
                row = self.get_brief(kind, start)
                if row is None:
                    raise
        for key, value in values.items():
            setattr(row, key, value)
        self.session.flush()
        return row
