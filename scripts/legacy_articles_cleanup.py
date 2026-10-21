"""Prepare, screen, rehearse and apply a frozen JEV cleanup without crawling or weekly runs."""
import argparse
import fcntl
import json
import os
import threading
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import httpx
from sqlalchemy import create_engine, insert, text

from app.config.settings import Settings
from app.core.ingestion.legacy_cleanup import MAX_NON_AI_RELEVANCE, MIN_REJECT_CONFIDENCE
from app.storage.cleanup_journal import CleanupJournal, CleanupStopped
from app.storage.legacy_cleanup import (
    _typed,
    apply_cleanup,
    build_manifest,
    encoded,
    fingerprint,
    normalize_snapshot,
    private_write,
    read_tables,
    restore_cleanup,
    verify_manifest,
)
from app.storage.models_sql import Base


def prepare(args):
    snapshot = normalize_snapshot(json.loads(args.snapshot.read_text()))
    args.run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    private_write(args.run_dir / 'snapshot.json', snapshot)
    manifest = build_manifest(snapshot, {})
    private_write(args.run_dir / 'manifest.json', manifest)
    print(encoded({'snapshot_hash': manifest['snapshot_hash'], 'counts': manifest['counts'],
                   'articles': len(manifest['entries']),
                   'maximum_requests': manifest['counts'].get('unchecked', 0)}))


def load(args):
    snapshot = normalize_snapshot(json.loads((args.run_dir / 'snapshot.json').read_text()))
    manifest = json.loads((args.run_dir / 'manifest.json').read_text())
    verify_manifest(snapshot, manifest)
    return snapshot, manifest


def screen(args):
    snapshot, manifest = load(args)
    settings = Settings()
    if (not settings.jev_api_key or not settings.jev_api_key.get_secret_value().strip()
            or settings.jev_model != snapshot['screening']['model']):
        raise SystemExit('Pinned JEV model/key unavailable')
    journal = CleanupJournal(args.run_dir / 'journal.sqlite', {
        'snapshot_hash': fingerprint(snapshot), 'screening': snapshot['screening']})
    stopped = None
    rows = {row['id']: row for row in snapshot['tables']['articles']}
    local = threading.local()
    workers = []
    identity = {'snapshot_hash': fingerprint(snapshot), 'screening': snapshot['screening']}

    def evaluate(entry):
        if not hasattr(local, 'store'):
            local.store = CleanupJournal(args.run_dir / 'journal.sqlite', identity)
            local.client = httpx.Client(timeout=settings.jev_timeout_seconds, headers={
                'Authorization': 'Bearer ' + settings.jev_api_key.get_secret_value().strip(),
            })
            workers.append((local.store, local.client))
        return local.store.evaluate(rows[entry['article_id']], entry['key'],
                                    snapshot['screening']['model'], local.client,
                                    args.budget_usd, args.max_requests)

    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            pending = set()
            entries = iter(e for e in manifest['entries'] if e['reason'] != 'current_cached_accept')
            completed = 0
            while True:
                while not stopped and len(pending) < args.concurrency:
                    entry = next(entries, None)
                    if entry is None:
                        break
                    pending.add(pool.submit(evaluate, entry))
                if not pending:
                    break
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        future.result()
                    except CleanupStopped as exc:
                        stopped = str(exc)
                    completed += 1
                if completed % 100 == 0:
                    print(encoded(journal.usage()), flush=True)
    finally:
        manifest = build_manifest(snapshot, journal.verdicts())
        private_write(args.run_dir / 'manifest.json', manifest)
        usage = journal.usage()
        private_write(args.run_dir / 'usage.json', usage)
        journal.close()
        for store, client in workers:
            store.close()
            client.close()
    print(encoded({'counts': manifest['counts'], 'usage': usage, 'stopped': stopped,
                   'manifest_hash': manifest['manifest_hash']}))


def rehearse(args):
    snapshot, manifest = load(args)
    engine = create_engine(os.environ['AINEWS_CLEANUP_TEST_DATABASE_URL'])
    if (engine.dialect.name != 'postgresql' or engine.url.host not in {'127.0.0.1', 'localhost'}
            or engine.url.database not in {'legacy_cleanup_test', 'legacy_cleanup_rehearsal'}):
        raise SystemExit('Rehearsal requires a separate local legacy_cleanup PostgreSQL test DB')
    with engine.connect() as connection:
        if connection.execute(text("SELECT COUNT(*) FROM information_schema.tables "
                                   "WHERE table_schema='public'")).scalar():
            raise SystemExit('Rehearsal database must be empty')
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            rows = snapshot['tables'].get(table.name, [])
            for row in rows:
                connection.execute(insert(table).values(_typed(table.name, row)))
            if rows and 'id' in table.c and table.c.id.autoincrement is True:
                connection.execute(text(f"SELECT setval(pg_get_serial_sequence('{table.name}', "
                                        "'id'), (SELECT MAX(id) FROM " + table.name + "))"))
    before = fingerprint(snapshot['tables'])
    result = apply_cleanup(engine, snapshot, manifest, args.run_dir / 'rehearsal-backup.json')
    backup = json.loads((args.run_dir / 'rehearsal-backup.json').read_text())
    # A new row after snapshot must survive targeted restore unchanged.
    table = Base.metadata.tables['articles']
    probe = dict(snapshot['tables']['articles'][0])
    probe.pop('id')
    probe.update(url='https://cleanup-rehearsal.invalid/new',
                 url_canonical='https://cleanup-rehearsal.invalid/new',
                 url_canonical_hash='f' * 64)
    with engine.begin() as connection:
        probe_id = connection.execute(insert(table).values(_typed('articles', probe))
                                      .returning(table.c.id)).scalar_one()
    restore_cleanup(engine, backup)
    with engine.connect() as connection:
        after = read_tables(connection)
        new = [row for row in after['articles'] if row['id'] == probe_id]
        if len(new) != 1:
            raise SystemExit('Targeted restore lost post-snapshot row')
        after['articles'] = [row for row in after['articles'] if row['id'] != probe_id]
        # Compare sorted sets: row order is not an invariant of a database.
        if any(sorted(map(fingerprint, after[name])) != sorted(map(fingerprint, rows))
               for name, rows in snapshot['tables'].items()):
            raise SystemExit('Targeted restore did not restore exact snapshot rows')
    receipt = {'snapshot_hash': manifest['snapshot_hash'],
               'manifest_hash': manifest['manifest_hash'],
               'dialect': 'postgresql', 'restored': True, 'post_snapshot_row_preserved': True,
               'deleted': len(result['deleted_ids']), 'before_tables_hash': before,
               'backup_hash': fingerprint(backup)}
    private_write(args.run_dir / 'restore-verification.json', receipt)
    print(encoded(receipt))
    engine.dispose()


def apply(args):
    snapshot, manifest = load(args)
    receipt = json.loads((args.run_dir / 'restore-verification.json').read_text())
    if any(receipt.get(key) != value for key, value in {
        'snapshot_hash': manifest['snapshot_hash'], 'manifest_hash': manifest['manifest_hash'],
        'dialect': 'postgresql', 'restored': True, 'post_snapshot_row_preserved': True,
    }.items()):
        raise SystemExit('Matching PostgreSQL restore verification required')
    settings = Settings()
    if (not settings.semantic_admission_enabled or not settings.jev_enabled
            or settings.weekly_v2_enabled or snapshot['screening'] != {
                'model': settings.jev_model,
                'policy_version': settings.semantic_admission_policy_version,
                'prompt_version': settings.semantic_admission_prompt_version,
            }):
        raise SystemExit('Production admission/weekly safeguards differ from snapshot')
    if not args.collector_coordinated:
        raise SystemExit('Coordinate collector before apply')
    engine = create_engine(str(settings.database_url))
    result = apply_cleanup(engine, snapshot, manifest, args.run_dir / 'apply-backup.json')
    if not (args.run_dir / 'apply-result.json').exists():
        private_write(args.run_dir / 'apply-result.json', result)
    print(encoded(result))
    engine.dispose()


def review(args):
    snapshot, manifest = load(args)
    rows = {row['id']: row for row in snapshot['tables']['articles']}
    entries = []
    for entry in manifest['entries']:
        if entry['outcome'] != 'unresolved':
            continue
        assessment = entry.get('assessment', {})
        choice = assessment.get('admission_choice')
        confidence = assessment.get('admission_confidence')
        reasons = []
        row = rows[entry['article_id']]
        if choice == 'insufficient_evidence':
            reasons.append('jev_insufficient_evidence')
        else:
            if confidence is None:
                reasons.append('missing_admission_confidence')
            elif confidence < MIN_REJECT_CONFIDENCE:
                reasons.append('admission_confidence_below_threshold')
            if choice == 'non_ai':
                if len((row.get('content') or row.get('summary') or '').strip()) < 160:
                    reasons.append('short_saved_evidence')
                if assessment.get('relevance_score', 1) > MAX_NON_AI_RELEVANCE:
                    reasons.append('relevance_not_low')
            elif choice == 'non_editorial' and entry.get('prefilter') is None:
                reasons.append('no_deterministic_corroboration')
        entries.append({**entry, 'review_reasons': reasons,
                        'summary': row.get('summary'), 'saved_content_excerpt':
                        (row.get('content') or '')[:1000]})
    report = {'snapshot_hash': manifest['snapshot_hash'],
              'manifest_hash': manifest['manifest_hash'], 'screening': manifest['screening'],
              'count': len(entries), 'reason_counts': dict(Counter(
                  reason for entry in entries for reason in entry['review_reasons'])),
              'entries': entries}
    private_write(args.run_dir / 'review-unresolved.json', report)
    print(encoded({key: value for key, value in report.items() if key != 'entries'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('prepare', 'screen', 'rehearse', 'apply', 'status', 'review'):
        item = sub.add_parser(command)
        item.add_argument('--run-dir', type=Path, required=True)
        if command == 'prepare':
            item.add_argument('--snapshot', type=Path, required=True)
        elif command == 'screen':
            item.add_argument('--budget-usd', type=float, required=True)
            item.add_argument('--max-requests', type=int, required=True)
            item.add_argument('--concurrency', type=int, choices=range(1, 9), default=4)
        elif command == 'apply':
            item.add_argument('--collector-coordinated', action='store_true')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args)
        return
    with (args.run_dir / 'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'status':
            _, manifest = load(args)
            print(encoded({'counts': dict(Counter(e['outcome'] for e in manifest['entries'])),
                           'manifest_hash': manifest['manifest_hash']}))
        else:
            {'screen': screen, 'rehearse': rehearse, 'apply': apply, 'review': review}[
                args.command](args)


if __name__ == '__main__':
    main()
