"""Apply the verified October 2026 source repairs without deleting source history."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.config.sources import load_sources
from app.storage.models_sql import Source

REPAIR_KEYS = {
    "deepmind_blog", "microsoft_ai_blog", "rainbird", "linguamatics", "vellum_blog",
    "dify_blog", "theagi_company_blog", "e2b_blog", "promptengineering_blog",
    "outerbounds_blog",
}
DUPLICATE_KEY = "deepmind-google-blog-rss-xml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit repairs; default is dry-run")
    parser.add_argument("--backup", type=Path, help="Required new backup file when using --apply")
    args = parser.parse_args()
    if args.apply and args.backup is None:
        parser.error("--apply requires --backup")
    settings = get_settings()
    configs = {config.id: config for config in load_sources(settings.sources_path)}
    if not REPAIR_KEYS <= configs.keys():
        parser.error("Sources file is missing a required repair configuration")
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session, session.begin():
            sources = list(session.scalars(select(Source).where(
                Source.source_key.in_(REPAIR_KEYS | {DUPLICATE_KEY})
            ).with_for_update()))
            existing = {source.source_key: source for source in sources}
            duplicate = existing.get(DUPLICATE_KEY)
            canonical = existing.get("deepmind_blog")
            if duplicate is not None and (
                canonical is None
                or duplicate.url != str(configs["deepmind_blog"].url)
            ):
                raise ValueError("DeepMind duplicate no longer matches the verified repair")
            updates = []
            for source in sources:
                changes = {}
                if source.source_key in REPAIR_KEYS:
                    config = configs[source.source_key]
                    for field, value in {"url": str(config.url), "type": config.type,
                                         "name": config.name}.items():
                        if getattr(source, field) != value:
                            changes[field] = value
                    if "url" in changes or "type" in changes:
                        changes.update(etag=None, last_modified=None, last_checked_at=None,
                                       last_status_code=None)
                elif source.enabled:
                    changes["enabled"] = False
                if changes:
                    updates.append((source, changes))
            plan = [{"source_id": source.id, "source_key": source.source_key,
                     "before": {field: getattr(source, field) for field in changes},
                     "after": changes} for source, changes in updates]
            if args.apply and plan:
                snapshot = [{column.name: getattr(source, column.name)
                             for column in Source.__table__.columns} for source in sources]
                payload = {"created_at": datetime.now(UTC), "plan": plan, "sources": snapshot}
                args.backup.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(args.backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2, default=str)
                    handle.write("\n")
                for source, changes in updates:
                    for field, value in changes.items():
                        setattr(source, field, value)
            print(json.dumps({"applied": args.apply, "changes": plan}, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
