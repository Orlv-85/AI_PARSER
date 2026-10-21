"""Verified manifest input and isolated, durable weekly calculation."""
# pylint: disable=too-many-instance-attributes,protected-access

import copy
import fcntl
import hashlib
import json
import math
import os
import sqlite3
import time
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.core.ingestion.admission import bounded_evidence, evidence_hash
from app.core.provider_costs import PRICES, microdollars
from app.core.weekly.analytics import windows
from app.core.weekly.enrichment import BudgetExhausted, WeeklyEnricher
from app.core.weekly.input import instant, parsed, source_fingerprint
from app.core.weekly.narrative import explain
from app.core.weekly.worker import build_snapshot
from app.storage.journal_files import fingerprint as journal_fingerprint
from app.storage.journal_files import private_write
from app.storage.models_sql import Base, WeeklyJob, WeeklySnapshot
from app.storage.reenrich_pilot_journal import PilotJournal, PilotStopped
from app.storage.weekly import WeeklyStore, encoded, fingerprint
from app.web.models import WeeklyAnalyticsResponse

VERSION = "weekly-manifest-v4-2"
FILES = ("snapshot.json", "selection-manifest-v4.json", "source-evidence.json",
         "published-target.json", "handoff-receipt.json")


def code_hashes() -> dict:
    app_root = Path(__file__).resolve().parents[2]
    names = ("core/weekly/frozen.py", "core/weekly/input.py", "core/weekly/analytics.py",
             "core/weekly/enrichment.py", "core/weekly/worker.py", "core/weekly/topics.py",
             "core/weekly/narrative.py", "storage/weekly.py",
             "storage/reenrich_pilot_journal.py", "web/models.py")
    return {name: file_hash(app_root / name) for name in names}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_input(root: Path, expected: dict[str, str]) -> dict:
    # Check every byte hash before parsing corpus, including the receipt itself.
    if set(expected) != set(FILES):
        raise ValueError("All five public handoff file hashes are required")
    if any(file_hash(root / name) != expected[name] for name in FILES):
        raise ValueError("Private input hash differs from the public handoff")
    inputs = {name: json.loads((root / name).read_text()) for name in FILES}
    receipt = inputs["handoff-receipt.json"]
    for key, name in (("snapshot", FILES[0]), ("manifest", FILES[1]),
                      ("source_evidence", FILES[2]), ("published_target", FILES[3])):
        if receipt[key]["sha256"] != expected[name]:
            raise ValueError("Handoff receipt hash mismatch")
    if inputs[FILES[1]].get("revision") != 4:
        raise ValueError("Only selection manifest revision 4 is supported")
    return inputs


# pylint: disable=too-many-boolean-expressions
def _admission_refs(row: dict, record: dict, snapshot: dict, bundle: dict) -> list[dict]:
    refs = []
    ledger = {r["id"]: r for r in snapshot["tables"]["admission_decisions"]}
    mass = {r["article_id"]: r for r in bundle["mass_results"]}
    state = f"Title: {row['title'][:1024]}\nContent: {row['content'][:16000]}"
    for ref in record["admission_refs"]:
        kind = ref["kind"]
        if kind == "admission_ledger":
            decision = ledger[ref["id"]]
            candidate = parsed(decision["payload"])["candidate"]
            if (decision["decision"] == "accept" and decision["provider_status"] == "ok"
                    and decision["source_id"] == row["source_id"]
                    and decision["url_canonical_hash"] == row["canonical_hash"]
                    and decision["evidence_hash"] == evidence_hash(
                        bounded_evidence(SimpleNamespace(**candidate)))
                    and candidate.get("title") == row["title"]
                    and candidate.get("content")
                    and row["content"].startswith(candidate["content"])):
                refs.append(ref)
        elif kind in {"cached_mass_admission", "applied_mass_admission"}:
            result = mass.get(row["article_id"], {})
            if (result.get("outcome") == "kept" and not result.get("operator_review_required")
                    and result.get("assessment", {}).get("admission_choice")
                    == "accepted_ai_editorial" and result.get("source_hash")
                    == ref["source_hash"] == source_fingerprint(state)):
                refs.append(ref)
        elif kind == "article_admission_proof" and ref["source_hash"] == source_fingerprint(state):
            refs.append(ref)
    return refs


def packet_from_manifest(inputs: dict) -> dict:
    snapshot, manifest, bundle = (inputs[name] for name in FILES[:3])
    packet = {k: v for k, v in snapshot["runtime_freeze"].items()
              if k not in {"observations", "included_ids", "excluded_observations"}}
    articles = {r["id"]: r for r in snapshot["tables"]["articles"]}
    if (len(manifest["records"]) != len(articles)
            or {r["article_id"] for r in manifest["records"]} != set(articles)):
        raise ValueError("Manifest does not account for the complete current Article scope")
    periods = windows(date.fromisoformat(manifest["report_date"]))
    indices = {"W0": 0, "W1": 1, "H2": 2, "H3": 3, "H4": 4}
    observations, unassigned = [], []
    tombstones = {r["canonical_hash"] for r in manifest["deleted_article_tombstones"]}
    for record in manifest["records"]:
        article = articles[record["article_id"]]
        if article["url_canonical_hash"] != record["canonical_hash"]:
            raise ValueError("Article canonical identity differs")
        if not record["window"]:
            unassigned.append({"article_id": article["id"], "date_class": record["date_class"],
                               "possible_windows": record["possible_windows"],
                               "unresolved_reasons": record["unresolved_reasons"]})
            continue
        if record["canonical_hash"] in tombstones or article["publication_status"] == "conflict":
            raise ValueError("Deleted or conflicting Article selected")
        page = bundle["pages"].get(str(article["id"]))
        content = article.get("content") or ""
        title = article["title"]
        if record["text_origin"] == "saved_page":
            if (not page or not page["integrity_ok"]
                    or source_fingerprint(page["evidence"]) != record["source_evidence_ref"]
                    or page["evidence"]["quality"] != "extracted"):
                raise ValueError("Saved source evidence is incompatible")
            content = page["text"]
            title = page["evidence"].get("title") or title
        elif record["text_origin"] == "admission_candidate":
            ledger = {r["id"]: r for r in snapshot["tables"]["admission_decisions"]}
            candidates = [parsed(ledger[r["id"]]["payload"])["candidate"].get("content") or ""
                          for r in record["admission_refs"] if r["kind"] == "admission_ledger"]
            content = next((c for c in candidates if hashlib.sha256(c.encode()).hexdigest()
                            == record["source_text_sha256"]), "")
        if hashlib.sha256(content.encode()).hexdigest() != record["source_text_sha256"]:
            raise ValueError("Selected source body differs from manifest")
        stamp = instant(record["effective_published_at"])
        interval = record["possible_utc_interval"]
        index = indices[record["window"]]
        start, end = periods[index]
        if stamp is not None:
            if not start <= stamp < end:
                raise ValueError("Publication instant is outside the assigned week")
        elif (not interval or not start <= instant(interval["start"])
              or not instant(interval["end"]) <= end):
            raise ValueError("Calendar interval crosses the assigned week")
        row = {"id": f"article-{article['id']}", "article_id": article["id"],
               "source_id": article["source_id"], "canonical_hash": record["canonical_hash"],
               "title": title, "summary": None, "content": content,
               "url": article["url_canonical"], "publisher": record["publisher"],
               "published_at": stamp.isoformat() if stamp else None,
               "calendar_date": record["calendar_date"], "publication_interval": interval,
               "publication_precision": record["effective_precision"], "window_index": index,
               "publication_provenance": "verified_manifest_evidence", "admission_required": True,
               "historical_observation_ids": record["observation_ids"],
               "source_text_sha256": record["source_text_sha256"]}
        row["admission_refs"] = _admission_refs(row, record, snapshot, bundle)
        row["admission_state"] = "accepted_compatible" if row["admission_refs"] else "unresolved"
        observations.append(row)
    packet.update({"pipeline_revision": VERSION, "report_date": manifest["report_date"],
                   "observations": observations, "included_ids": [r["id"] for r in observations],
                   "unassigned_articles": unassigned, "excluded_observations":
                   [{"id": r["id"], "reason": r["reason"]} for r in manifest["observations"]],
                   "input_complete": True, "history_complete": False,
                   "quality_counters": {"articles_accounted": len(articles),
                     "retrieved": len(observations), "unassigned_dates": manifest["counts"][
                         "unassigned"]["total"], "ambiguous_week_boundary": manifest["counts"][
                         "boundary_ambiguous"]["total"],
                     "outside_scope": manifest["counts"]["outside_scope"]["total"],
                     "calendar_inputs": sum(r["published_at"] is None for r in observations),
                     "admission_unresolved": sum(r["admission_state"] != "accepted_compatible"
                                                 for r in observations)}})
    return packet


def compatible_assignments(snapshot: dict, packet: dict, enricher: WeeklyEnricher) -> list[dict]:
    """Recompute full keys on the selected input; never import pilot progress/provenance."""
    cache = {r["key"]: r for r in snapshot["pilot_cache"]["decisions"] if r["task"] == "assignment"}
    result = {}
    topics = {t["id"] for t in packet["topics"]}
    for row in packet["observations"]:
        if row["admission_state"] != "accepted_compatible":
            continue
        key = enricher._key("assignment", {"text": enricher.assignment_text(row)})
        decision = cache.get(key)
        payload = parsed(decision["payload"]) if decision else {}
        if (set(payload) == {"topic_id", "eligible", "possible_topics", "classification_complete"}
                and payload.get("classification_complete") is True
                and isinstance(payload.get("eligible"), bool)
                and payload.get("topic_id") in topics | {None}
                and isinstance(payload.get("possible_topics"), list)
                and set(payload["possible_topics"]) <= topics):
            result[key] = {"key": key, "task": "assignment", "payload": payload}
    return list(result.values())


@contextmanager
def locked(root: Path):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_mode & 0o077:
        raise ValueError("Run directory must have private permissions")
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def prepare(input_root: Path, root: Path, hashes: dict, caps: dict, settings: Settings) -> dict:
    if root.resolve() == input_root.resolve() or input_root.resolve() in root.resolve().parents:
        raise ValueError("Run artifacts must be separate from immutable stage 1 input")
    inputs = verified_input(input_root, hashes)
    packet = packet_from_manifest(inputs)
    settings = settings.model_copy(update=packet["provider_configuration"])
    service = WeeklyEnricher(settings, None, None, packet["topics"],  # type: ignore[arg-type]
                            packet["taxonomy_version"])
    imported = compatible_assignments(inputs[FILES[0]], packet, service)
    frozen = {"version": VERSION, "input_hashes": hashes, "prices": PRICES,
              "code_hashes": code_hashes(),
              "caps_usd": caps, "packet": packet, "imports": imported,
              "admission_source": "jev_on_selected_source_text",
              "admission_configuration": {k: getattr(settings, k) for k in (
                  "semantic_admission_policy_version", "semantic_admission_prompt_version")}}
    with locked(root):
        path = root / "frozen.json"
        if path.exists() and fingerprint(json.loads(path.read_text())) != fingerprint(frozen):
            raise ValueError("Frozen revision differs; use a separate private run directory")
        journal = PilotJournal(root / "journal.sqlite3", fingerprint(frozen), caps)
        journal.close()
        if not path.exists():
            private_write(path, frozen)
    return {"input_fingerprint": fingerprint(frozen), "scope": len(packet["observations"]),
            "weeks": dict(Counter(r["window_index"] for r in packet["observations"])),
            "quality": packet["quality_counters"], "imported_assignments": len(imported),
            "caps_usd": caps, "paid_calls": 0}


def _copy_recovery_database(source, root, name, identities, caps):
    old_id, identity = identities
    with sqlite3.connect(f"file:{source / name}?mode=ro", uri=True) as original:
        if original.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Recovery source database is corrupt")
        if name == "journal.sqlite3":
            expected = journal_fingerprint({"identity": old_id, "caps_micro_usd": caps})
            if original.execute("SELECT value FROM identity").fetchone()[0] != expected:
                raise ValueError("Recovery source journal identity differs")
            if original.execute("SELECT 1 FROM calls WHERE state='inflight'").fetchone():
                raise ValueError("Concurrent inflight dispatch cannot be reviewed")
        elif (original.execute("SELECT count(*) FROM weekly_snapshots").fetchone()[0]
              or original.execute("SELECT 1 FROM weekly_jobs WHERE id!=? OR lease_token "
                                  "IS NOT NULL", (old_id,)).fetchone()):
            raise ValueError("Recovery requires one stopped unpublished job")
        with sqlite3.connect(root / name) as copied:
            original.backup(copied)
            if name == "journal.sqlite3":
                copied.execute("UPDATE identity SET value=?", (journal_fingerprint(
                    {"identity": identity, "caps_micro_usd": caps}),))
            else:
                copied.execute("UPDATE weekly_jobs SET id=?,input_fingerprint=?,"
                               "status='pending',error=NULL WHERE id=?",
                               (identity, identity, old_id))
    (root / name).chmod(0o600)


def recover(input_root: Path, source: Path, root: Path, expected_hash: str, reason: str) -> dict:
    """Copy a stopped revision with complete accounting into a new code revision."""
    if not reason.strip() or source.resolve() == root.resolve():
        raise ValueError("Recovery requires a review reason and a separate directory")
    with locked(source), locked(root):
        if file_hash(source / "frozen.json") != expected_hash:
            raise ValueError("Recovery source hash differs from the reviewed checkpoint")
        old = json.loads((source / "frozen.json").read_text())
        if old["version"] != VERSION or old["prices"] != PRICES:
            raise ValueError("Recovery source version/pricing differs")
        if old["packet"] != packet_from_manifest(verified_input(input_root, old["input_hashes"])):
            raise ValueError("Recovery would change frozen input")
        old_id = fingerprint(old)
        lineage = {"parent_identity": old_id, "parent_frozen_sha256": expected_hash,
                   "parent_journal_sha256": file_hash(source / "journal.sqlite3"),
                   "parent_weekly_sha256": file_hash(source / "weekly.sqlite")}
        new = {**old, "code_hashes": code_hashes(), "lineage": lineage,
               "transport_recovery": {"reason": reason, "max_attempts": 2}}
        identity = fingerprint(new)
        if (root / "frozen.json").exists():
            if json.loads((root / "frozen.json").read_text()) != new:
                raise ValueError("Recovery destination belongs to a different revision")
            return {"input_fingerprint": identity, "already_prepared": True}
        if any(path.name != "run.lock" for path in root.iterdir()):
            raise ValueError("Recovery destination must be empty")
        caps = {k: microdollars(v) for k, v in old["caps_usd"].items()}
        for name in ("journal.sqlite3", "weekly.sqlite"):
            _copy_recovery_database(source, root, name, (old_id, identity), caps)
        journal = PilotJournal(root / "journal.sqlite3", identity, old["caps_usd"],
                               transport_review_reason=reason)
        try:
            failed = journal.db.execute("SELECT key FROM calls WHERE state='failed'").fetchall()
            for (key,) in failed:
                if not journal.review_transport_failure(key, reason):
                    raise ValueError("Non-transport failure still requires separate review")
            private_write(root / "recovery-receipt.json", {"lineage": lineage,
                "identity": identity, "usage": journal.report(), "scope": len(
                    new["packet"]["observations"]), "provider_dispatches": 0})
        finally:
            journal.close()
        private_write(root / "frozen.json", new)
        return {"input_fingerprint": identity, "scope": len(new["packet"]["observations"]),
                "provider_dispatches": 0, "lineage": lineage}


SECTIONS = ("new", "trending_up", "trending_down", "other_signals")
PROSE_FIELDS = {"summary", "claims", "narrative_mode", "narrative_reason", "narrative_support",
               "narrative_diagnostics"}


def narrative_invariants(payload: dict) -> dict:
    """Exact comparison of everything except explicitly authorized prose/provenance."""
    value = copy.deepcopy(payload)
    for key in ("snapshot_id", "input_fingerprint", "revision", "generated_at", "narrative_mode"):
        value.pop(key, None)
    for key in ("durable_provider_usage", "provider_calls", "provider_tokens",
                "narrative_revision"):
        value["quality"].pop(key, None)
    for section in SECTIONS:
        value[section] = [{k: v for k, v in item.items() if k not in PROSE_FIELDS}
                          for item in value[section]]
    return value


# pylint: disable=too-many-branches
def prepare_narrative_revision(source: Path, root: Path, expected_hash: str,
                               topics: list[str], settings: Settings, *,
                               reuse_root: Path | None = None) -> dict:
    """Preserve completed calculation and paid artifacts; freeze a prose-only revision."""
    if source.resolve() == root.resolve() or not topics or len(topics) != len(set(topics)):
        raise ValueError("Separate root and distinct selected topics required")
    with ExitStack() as locks:
        locks.enter_context(locked(source))
        if reuse_root and reuse_root.resolve() != source.resolve():
            locks.enter_context(locked(reuse_root))
        locks.enter_context(locked(root))
        if file_hash(source / "candidate.json") != expected_hash:
            raise ValueError("Parent candidate differs from the reviewed hash")
        old = json.loads((source / "frozen.json").read_text())
        parent = json.loads((source / "candidate.json").read_text())
        if old["version"] != VERSION or old["prices"] != PRICES:
            raise ValueError("Parent version/pricing differs")
        old_id = fingerprint(old)
        paid_source = reuse_root or source
        paid_frozen = json.loads((paid_source / "frozen.json").read_text())
        paid_identity = fingerprint(paid_frozen)
        if reuse_root and (paid_frozen.get("lineage", {}).get("parent_candidate_sha256")
                           != expected_hash or paid_frozen["packet"] != old["packet"]
                           or paid_frozen["caps_usd"] != old["caps_usd"]):
            raise ValueError("Reused paid artifacts belong to a different calculation")
        if parent["snapshot_id"] != old_id or parent["input_fingerprint"] != old_id:
            raise ValueError("Parent candidate identity differs")
        available = {i["topic_id"] for section in SECTIONS for i in parent[section]}
        if not set(topics) <= available:
            raise ValueError("Unknown selected topic")
        config = {k: getattr(settings, k) for k in (
            "weekly_narrative_prompt_version", "weekly_narrative_input_byte_cap",
            "weekly_narrative_output_token_cap")}
        lineage = {"parent_identity": old_id, "parent_candidate_sha256": expected_hash,
                   "parent_frozen_sha256": file_hash(source / "frozen.json"),
                   "parent_journal_sha256": file_hash(source / "journal.sqlite3"),
                   "parent_weekly_sha256": file_hash(source / "weekly.sqlite"),
                   "reused_artifacts_identity": paid_identity,
                   "reused_frozen_sha256": file_hash(paid_source / "frozen.json"),
                   "reused_journal_sha256": file_hash(paid_source / "journal.sqlite3"),
                   "reused_weekly_sha256": file_hash(paid_source / "weekly.sqlite")}
        new = {**old, "code_hashes": code_hashes(), "lineage": lineage,
               "narrative_revision": {"topics": topics, "configuration": config,
                                      "invariants_sha256": fingerprint(
                                          narrative_invariants(parent))}}
        identity = fingerprint(new)
        if (root / "frozen.json").exists():
            if json.loads((root / "frozen.json").read_text()) != new:
                raise ValueError("Narrative revision differs; use a separate root")
            return {"input_fingerprint": identity, "already_prepared": True}
        if any(p.name != "run.lock" for p in root.iterdir()):
            raise ValueError("Narrative destination must be empty")
        caps = {k: microdollars(v) for k, v in old["caps_usd"].items()}
        for name in ("journal.sqlite3", "weekly.sqlite"):
            with sqlite3.connect(f"file:{paid_source / name}?mode=ro", uri=True) as original:
                if original.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Parent database is corrupt")
                if name == "journal.sqlite3":
                    if original.execute("SELECT value FROM identity").fetchone()[0] != (
                        journal_fingerprint({"identity": paid_identity, "caps_micro_usd": caps})
                    ) or original.execute("SELECT 1 FROM calls WHERE state='inflight'").fetchone():
                        raise ValueError("Parent journal identity/inflight dispatch differs")
                elif original.execute("SELECT 1 FROM weekly_jobs WHERE lease_token "
                                      "IS NOT NULL").fetchone():
                    raise ValueError("Parent weekly job is leased")
                with sqlite3.connect(root / name) as copied:
                    original.backup(copied)
                    if name == "journal.sqlite3":
                        copied.execute("UPDATE identity SET value=?", (journal_fingerprint(
                            {"identity": identity, "caps_micro_usd": caps}),))
            (root / name).chmod(0o600)
        private_write(root / "parent-candidate.json", parent)
        private_write(root / "frozen.json", new)
        return {"input_fingerprint": identity, "lineage": lineage, "provider_dispatches": 0}


def narrative_parent(root: Path, frozen: dict) -> dict:
    if file_hash(root / "parent-candidate.json") != frozen["lineage"]["parent_candidate_sha256"]:
        raise ValueError("Narrative parent bytes differ")
    parent = json.loads((root / "parent-candidate.json").read_text())
    if fingerprint(narrative_invariants(parent)) != (
        frozen["narrative_revision"]["invariants_sha256"]
    ):
        raise ValueError("Narrative parent invariants differ")
    return dict(parent)


def revise_narratives(root: Path, frozen: dict, service: WeeklyEnricher) -> dict:
    payload = copy.deepcopy(narrative_parent(root, frozen))
    definitions = {t["id"]: t for t in payload["topic_registry"]}
    items = {i["topic_id"]: i for section in SECTIONS for i in payload[section]}
    for topic_id in frozen["narrative_revision"]["topics"]:
        explain(items[topic_id], service, definitions[topic_id])
    modes = [i.get("narrative_mode", "template") for s in SECTIONS for i in payload[s]]
    payload["narrative_mode"] = ("deepseek" if all(m == "deepseek" for m in modes)
                                 else "mixed" if "deepseek" in modes else "template")
    payload["input_fingerprint"] = fingerprint(frozen)
    payload["quality"]["narrative_revision"] = frozen["narrative_revision"] | {
        "parent_identity": frozen["lineage"]["parent_identity"]}
    if fingerprint(narrative_invariants(payload)) != (
        frozen["narrative_revision"]["invariants_sha256"]
    ):
        raise ValueError("Narrative revision changed calculated facts")
    return payload


class JournalEnricher(WeeklyEnricher):
    def __init__(self, *args, journal, **kwargs):
        super().__init__(*args, **kwargs)
        self.journal = journal

    def _post(self, provider: str, body: dict, kind: str) -> dict:
        secret = self.settings.jev_api_key if provider == "jev" else self.settings.ds_api_key
        if not secret or not secret.get_secret_value().strip():
            raise PilotStopped("provider_credentials_missing")
        if len(encoded(body).encode()) > self.input_cap(kind):
            raise ValueError("Provider input cap exceeded")
        timeout = (self.settings.jev_timeout_seconds if provider == "jev"
                   else self.settings.weekly_deepseek_timeout_seconds)
        self.client.timeout = httpx.Timeout(min(timeout, max(0.1,
            self.settings.weekly_wall_seconds - (time.monotonic() - self.started))))
        return dict(self.journal.call(provider, body, self.client, secret.get_secret_value(),
                                     before_dispatch=lambda: self._budget(kind)))


def weekly_reservation(provider, body):
    # Reserve bytes plus framing; do not apply assumed chars/token or cache discounts.
    size = len(encoded(body).encode()) + 2048
    if size > 64000 or (provider == "deepseek" and not 1 <= body.get("max_tokens", 0) <= 4096):
        raise ValueError("Provider conservative request bound exceeded")
    return math.ceil((64000 if provider == "jev" else size) * PRICES[provider]["input"]
                     + (0 if provider == "jev" else body["max_tokens"] *
                        PRICES[provider]["output"]))


def run(root: Path, settings: Settings) -> dict:
    os.umask(0o077)
    with locked(root):
        frozen = json.loads((root / "frozen.json").read_text())
        if frozen["version"] != VERSION or frozen["prices"] != PRICES:
            raise ValueError("Frozen code/pricing revision differs")
        if frozen["code_hashes"] != code_hashes():
            raise ValueError("Code differs from the frozen calculation revision")
        identity = fingerprint(frozen)
        packet = frozen["packet"]
        engine = create_engine(f"sqlite:///{root / 'weekly.sqlite'}")
        Base.metadata.create_all(engine)
        journal = PilotJournal(root / "journal.sqlite3", identity, frozen["caps_usd"],
            key_function=lambda p, b: fingerprint({"provider": p, "body": b, "version": VERSION}),
            reservation_function=weekly_reservation,
            transport_review_reason=frozen.get("transport_recovery", {}).get("reason"))
        try:
            with Session(engine) as session, httpx.Client(timeout=60) as client:
                store = WeeklyStore(session)
                job = session.get(WeeklyJob, identity)
                if job is None:
                    if (not frozen.get("narrative_revision")
                            and session.scalar(select(WeeklyJob.id).limit(1))):
                        raise ValueError("Isolated database belongs to a different revision")
                    session.add(WeeklyJob(id=identity, report_date=date.fromisoformat(
                        packet["report_date"]), methodology_version=packet["methodology_version"],
                        input_fingerprint=identity, input_payload=encoded(packet), status="pending",
                        attempts=0, created_at=datetime.now(UTC)))
                    session.commit()
                for decision in frozen["imports"]:
                    store.save_decision(decision["key"], decision["task"], decision["payload"])
                saved = session.get(WeeklySnapshot, identity)
                if saved is not None:
                    private_write(root / "candidate.json", json.loads(saved.payload))
                    private_write(root / "usage.json", journal.report())
                    return {"status": "complete", "snapshot_id": identity,
                            "usage": journal.report(), "candidate_sha256": file_hash(
                                root / "candidate.json")}
                claim = store.claim(settings.weekly_wall_seconds, job_id=identity)
                if claim is None:
                    return {"status": "leased", "usage": journal.report()}
                packet = {**packet, "job_id": identity}
                settings = settings.model_copy(update={**packet["provider_configuration"],
                    **frozen["admission_configuration"],
                    **frozen.get("narrative_revision", {}).get("configuration", {})})
                service = JournalEnricher(settings, store, client, packet["topics"],
                    packet["taxonomy_version"], journal=journal)
                try:
                    payload = (revise_narratives(root, frozen, service) if frozen.get(
                        "narrative_revision") else build_snapshot(packet, service))
                    payload["quality"]["durable_provider_usage"] = journal.report()
                    WeeklyAnalyticsResponse.model_validate(payload)
                    # Publication is ONLY into this isolated SQLite candidate database.
                    store.publish(identity, claim[1], payload, packet)
                    private_write(root / "candidate.json", payload)
                    status = "complete"
                except (BudgetExhausted, PilotStopped) as exc:
                    store.retry(identity, claim[1], str(exc))
                    status = "retry"
                except Exception as exc:
                    store.retry(identity, claim[1], type(exc).__name__)
                    raise
                private_write(root / "usage.json", journal.report())
                return {"status": status, "snapshot_id": identity, "usage": journal.report()}
        finally:
            journal.close()
            engine.dispose()


def publish_prepared(root: Path, store: WeeklyStore, expected_sha256: str, *,
                     expected_previous_snapshot_id: str | None = None) -> dict:
    """Stage 4 only: validate and publish a reviewed payload without any provider replay."""
    path = root / "candidate.json"
    if file_hash(path) != expected_sha256:
        raise ValueError("Candidate hash differs from the reviewed payload")
    payload = json.loads(path.read_text())
    frozen = json.loads((root / "frozen.json").read_text())
    if frozen["code_hashes"] != code_hashes():
        raise ValueError("Code differs from the frozen publication revision")
    if frozen.get("narrative_revision"):
        narrative_parent(root, frozen)
        if fingerprint(narrative_invariants(payload)) != (
            frozen["narrative_revision"]["invariants_sha256"]
        ):
            raise ValueError("Narrative publication changed calculated facts")
    identity = fingerprint(frozen)
    packet = frozen["packet"]
    WeeklyAnalyticsResponse.model_validate(payload)
    if (payload.get("snapshot_id") != identity or payload.get("input_fingerprint") != identity
            or payload["report_date"] != packet["report_date"]
            or payload["data_cutoff"] != packet["data_cutoff"]
            or payload.get("methodology_version") != packet["methodology_version"]
            or set(payload["included_observation_ids"]) != set(packet["included_ids"])
            or {r["id"] for r in payload["assignments"]} != set(packet["included_ids"])):
        raise ValueError("Candidate provenance differs from the frozen revision")
    existing = store.session.get(WeeklySnapshot, identity)
    if existing is not None:
        return {"snapshot_id": identity, "revision": existing.revision, "already_stored": True}
    store.lock_date(date.fromisoformat(packet["report_date"]))
    current = store.published(date.fromisoformat(packet["report_date"]))
    if expected_previous_snapshot_id is not None and (
        (current["snapshot_id"] if current else "absent") != expected_previous_snapshot_id
    ):
        raise ValueError("Target publication drifted from the reviewed snapshot")
    job = store.session.get(WeeklyJob, identity)
    if job is None:
        store.session.add(WeeklyJob(id=identity,
            report_date=date.fromisoformat(packet["report_date"]),
            methodology_version=packet["methodology_version"], input_fingerprint=identity,
            input_payload=encoded(packet), status="pending", attempts=0,
            created_at=datetime.now(UTC)))
        store.session.commit()
    elif json.loads(job.input_payload) != packet:
        raise ValueError("Target job input differs from the frozen revision")
    claim = store.claim(900, job_id=identity)
    if claim is None:
        raise ValueError("Target job cannot be leased")
    # The final registry may include the engine's validated emerging topics.
    publish_packet = {**packet, "topics": payload["topic_registry"],
                      "taxonomy_version": payload["taxonomy_version"]}
    store.publish(identity, claim[1], payload, publish_packet)
    return {"snapshot_id": identity, "revision": payload["revision"], "provider_calls": 0}
