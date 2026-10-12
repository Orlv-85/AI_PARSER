"""Prepare or resume an isolated weekly candidate from verified manifest v4."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.core.weekly_frozen import prepare, publish_prepared, run
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
    runner = commands.add_parser("run", help="Resume exactly the frozen revision")
    runner.add_argument("--root", required=True, type=Path)
    runner.add_argument("--approve-paid", required=True, action="store_true")
    runner.add_argument("--env-file", type=Path, default=Path(".env"))
    publisher = commands.add_parser("publish", help="Stage 4: import reviewed payload; no models")
    publisher.add_argument("--root", required=True, type=Path)
    publisher.add_argument("--candidate-sha256", required=True)
    publisher.add_argument("--database-url-env", required=True, help="Environment variable name")
    publisher.add_argument("--approve-publication", required=True, action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.input_root, args.root, json.loads(args.hashes.read_text()),
                         {"total": args.total_budget_usd, "jev": args.jev_budget_usd,
                          "deepseek": args.deepseek_budget_usd}, Settings())
    elif args.command == "run":
        result = run(args.root, Settings(_env_file=args.env_file))
    else:
        engine = create_engine(os.environ[args.database_url_env])
        try:
            with Session(engine) as session:
                result = publish_prepared(args.root, WeeklyStore(session), args.candidate_sha256)
        finally:
            engine.dispose()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
