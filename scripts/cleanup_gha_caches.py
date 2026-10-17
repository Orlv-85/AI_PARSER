#!/usr/bin/env python3
"""Delete GitHub Actions caches, keeping the newest N non-default refs.

Caches of the default branch are never touched: every other ref can read them.
Caches written by tag/feature refs are only reusable by that ref itself, so
only the most recent refs are worth keeping.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

FIELDS = "id,key,ref,sizeInBytes,createdAt"


def select_deletions(caches: list[dict], default_ref: str, keep: int) -> list[dict]:
    newest: dict[str, str] = {}
    for cache in caches:
        ref = cache["ref"]
        if ref != default_ref and cache["createdAt"] > newest.get(ref, ""):
            newest[ref] = cache["createdAt"]
    keep_refs = set(sorted(newest, key=newest.__getitem__, reverse=True)[:keep])
    return [c for c in caches if c["ref"] != default_ref and c["ref"] not in keep_refs]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", type=int, default=5, help="newest non-default refs to keep")
    parser.add_argument("--default-ref", default="refs/heads/master")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-json", help="read `gh cache list --json` output from a file")
    args = parser.parse_args()

    if args.from_json:
        with open(args.from_json, encoding="utf-8") as fh:
            caches = json.load(fh)
    else:
        out = subprocess.run(
            ["gh", "cache", "list", "--limit", "1000", "--json", FIELDS],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        caches = json.loads(out)

    doomed = select_deletions(caches, args.default_ref, args.keep)
    size_mb = sum(c["sizeInBytes"] for c in doomed) / 1e6
    print(f"{len(caches)} caches total, {len(doomed)} to delete ({size_mb:.1f} MB)")
    if args.dry_run:
        return 0
    for cache in doomed:
        subprocess.run(["gh", "cache", "delete", str(cache["id"])], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
