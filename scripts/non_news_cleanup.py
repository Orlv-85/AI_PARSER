"""Export ingestion tables read-only, report proposed removals, and save restore SQL."""
import argparse
import json
import os
from pathlib import Path

from app.storage.non_news_cleanup import build_cleanup_plan, export_database, restoration_sql


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, help="Existing consistent JSON table export")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.export:
        export = json.loads(args.export.read_text())
    else:
        export = export_database(os.environ["AINEWS_DATABASE_URL"])
    plan = build_cleanup_plan(export)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, content in {
        "dry-run.json": json.dumps(plan, indent=2) + "\n",
        "backup.json": json.dumps(export, indent=2, default=str) + "\n",
        "restore.sql": restoration_sql(export, plan),
    }.items():
        path = args.output / name
        path.write_text(content)
        path.chmod(0o600)
    print(json.dumps({k: v for k, v in plan.items() if k.endswith("count") or k.endswith("reason")
                      or k in {"candidate_sha256", "scanned_articles", "dependency_counts"}}, indent=2))


if __name__ == "__main__":
    main()
