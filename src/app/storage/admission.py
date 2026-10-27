from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models_sql import AdmissionDecision as AdmissionDecisionRow
from app.storage.models_sql import CollectionStatus

PAUSED_MESSAGE = (
    "News collection is paused because AI screening is unavailable. "
    "Admin: please check the AI providers and configuration."
)


def get_collection_status(session: Session) -> CollectionStatus:
    row = session.get(CollectionStatus, 1)
    if row is None:
        row = CollectionStatus(id=1, paused=False, message=None, updated_at=datetime.now(UTC))
        session.add(row)
        session.flush()
    return row


def read_collection_status(session: Session) -> tuple[bool, str | None]:
    row = session.get(CollectionStatus, 1)
    if row is None:
        return False, None
    return bool(row.paused), row.message if row.paused else None


def set_collection_paused(session: Session) -> None:
    row = get_collection_status(session)
    row.paused = True
    row.message = PAUSED_MESSAGE
    row.updated_at = datetime.now(UTC)
    session.flush()


def clear_collection_paused(session: Session) -> None:
    row = get_collection_status(session)
    row.paused = False
    row.message = None
    row.updated_at = datetime.now(UTC)
    session.flush()


def get_cached_decision(session: Session, key: str) -> AdmissionDecisionRow | None:
    stmt = select(AdmissionDecisionRow).where(AdmissionDecisionRow.key == key).limit(1)
    return session.execute(stmt).scalar_one_or_none()


def upsert_pending(
    session: Session,
    *,
    key: str,
    url_canonical_hash: str,
    source_id: int | None,
    payload: dict[str, Any],
    evidence_hash: str,
    policy_version: str,
    model: str,
    force_pending: bool = False,
) -> None:
    row = get_cached_decision(session, key)
    if row is None:
        row = AdmissionDecisionRow(
            key=key,
            url_canonical_hash=url_canonical_hash,
            source_id=source_id,
            payload=json.dumps({"candidate": payload}, ensure_ascii=True),
            evidence_hash=evidence_hash,
            policy_version=policy_version,
            model=model,
            provider_status="pending",
            attempts=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(row)
    else:
        if not force_pending and row.provider_status == "ok" and row.decision is not None:
            return
        if (
            not force_pending
            and row.provider_status == "settled"
            and row.reason == "stale_pending"
        ):
            return
        row.source_id = source_id
        row.payload = json.dumps({"candidate": payload}, ensure_ascii=True)
        row.decision = None
        row.reason = None
        row.provider_status = "pending"
        row.attempts = (row.attempts or 0) + 1
        row.updated_at = datetime.now(UTC)
    session.flush()


def settle_pending(
    session: Session,
    *,
    key: str,
    provider_status: str = "settled",
    decision: str | None = None,
    reason: str | None = None,
) -> None:
    row = get_cached_decision(session, key)
    if row is None:
        return
    row.provider_status = provider_status
    if decision is not None:
        row.decision = decision
    if reason is not None:
        row.reason = reason
    row.updated_at = datetime.now(UTC)
    session.flush()


def record_decision(
    session: Session,
    *,
    key: str,
    decision: str,
    reason: str,
    provider_status: str = "ok",
    payload: dict[str, Any] | None = None,
) -> None:
    row = get_cached_decision(session, key)
    if row is None:
        return
    row.decision = decision
    row.reason = reason
    row.provider_status = provider_status
    if payload is not None:
        try:
            current = json.loads(row.payload or "{}")
        except ValueError:
            current = {}
        if not isinstance(current, dict):
            current = {}
        current["assessment"] = payload
        row.payload = json.dumps(current, ensure_ascii=True)
    row.updated_at = datetime.now(UTC)
    session.flush()


def list_pending(
    session: Session, *, source_id: int, limit: int = 50,
) -> list[AdmissionDecisionRow]:
    stmt = (
        select(AdmissionDecisionRow)
        .where(AdmissionDecisionRow.source_id == source_id)
        .where(AdmissionDecisionRow.provider_status == "pending")
        .order_by(AdmissionDecisionRow.updated_at.asc(), AdmissionDecisionRow.id.asc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())
