"""Prepare or resume an isolated weekly candidate from verified manifest v4."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.core.weekly_frozen import (
    prepare,
    prepare_narrative_revision,
    publish_prepared,
    recover,
    run,
)
from app.storage.weekly import WeeklyStore


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Verify input and freeze; no provider calls")
    prep.add_argument("--input-root", required=True, type=Path)
    prep.add_argument("--root", required=True, type=Path)
    prep.add_argument("--hashes", required=True, type=Path, help="Public handoff SHA256 map")
    prep.add_argument("--total-budget-usd", required=True)
    prep.add_argument("--jev-budget-usd", required=True)
    prep.add_argument("--deepseek-budget-usd", required=True)
    recovery = commands.add_parser("recover", help="Copy stopped input/cache/journal; no models")
    recovery.add_argument("--input-root", required=True, type=Path)
    recovery.add_argument("--source-root", required=True, type=Path)
    recovery.add_argument("--root", required=True, type=Path)
    recovery.add_argument("--source-frozen-sha256", required=True)
    recovery.add_argument("--review-reason", required=True)
    prose = commands.add_parser("revise-narratives", help="Freeze a prose-only revision; no models")
    prose.add_argument("--source-root", required=True, type=Path)
    prose.add_argument("--root", required=True, type=Path)
    prose.add_argument("--candidate-sha256", required=True)
    prose.add_argument("--topics", required=True, nargs="+")
    prose.add_argument("--reuse-root", type=Path, help="Preserve a stopped prose run's paid artifacts")
    runner = commands.add_parser("run", help="Resume exactly the frozen revision")
    runner.add_argument("--root", required=True, type=Path)
    runner.add_argument("--approve-paid", required=True, action="store_true")
    runner.add_argument("--env-file", type=Path, default=Path(".env"))
    publisher = commands.add_parser("publish", help="Stage 4: import reviewed payload; no models")
    publisher.add_argument("--root", required=True, type=Path)
    publisher.add_argument("--candidate-sha256", required=True)
    publisher.add_argument("--database-url-env", required=True, help="Environment variable name")
    publisher.add_argument("--expected-previous-snapshot-id", help="Refuse concurrent pointer drift")
    publisher.add_argument("--approve-publication", required=True, action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.input_root, args.root, json.loads(args.hashes.read_text()),
                         {"total": args.total_budget_usd, "jev": args.jev_budget_usd,
                          "deepseek": args.deepseek_budget_usd}, Settings())
    elif args.command == "recover":
        result = recover(args.input_root, args.source_root, args.root,
                         args.source_frozen_sha256, args.review_reason)
    elif args.command == "run":
        result = run(args.root, Settings(_env_file=args.env_file))
    elif args.command == "revise-narratives":
        result = prepare_narrative_revision(args.source_root, args.root,
                                           args.candidate_sha256, args.topics, Settings(),
                                           reuse_root=args.reuse_root)
    else:
        engine = create_engine(os.environ[args.database_url_env])
        try:
            with Session(engine) as session:
                result = publish_prepared(args.root, WeeklyStore(session), args.candidate_sha256,
                    expected_previous_snapshot_id=args.expected_previous_snapshot_id)
        finally:
            engine.dispose()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
