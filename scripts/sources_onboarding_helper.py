#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

try:
    import httpx
    from lxml import html as lxml_html
except Exception:  # pragma: no cover - optional for lint-only mode
    httpx = None
    lxml_html = None


SECTION_DEFAULT = "User-curated: AI agents"
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


@dataclass
class EntrySpan:
    source_id: str
    start_line: int
    end_line: int
    text: str


def ensure_src_path() -> None:
    src_root = str(SRC_ROOT)
    if src_root not in sys.path:
        sys.path.insert(0, src_root)


def db_ids_arg(value: str | None) -> list[int]:
    if not value:
        return []
    ids: list[int] = []
    for part in value.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        ids.append(int(stripped))
    return ids


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "sources" not in raw:
        raise ValueError("expected mapping with top-level 'sources'")
    return raw


def find_section_bounds(text: str, section_substring: str) -> tuple[int, int]:
    lines = text.splitlines()
    start = -1
    end = len(lines)
    for idx, line in enumerate(lines, start=1):
        if line.strip().startswith("# ---") and section_substring in line:
            start = idx
            continue
        if start != -1 and idx > start and line.strip().startswith("# ---"):
            end = idx - 1
            break
    if start == -1:
        raise ValueError(f"section not found: {section_substring!r}")
    return start, end


def parse_entry_spans(text: str, start_line: int, end_line: int) -> dict[str, EntrySpan]:
    lines = text.splitlines()
    spans: dict[str, EntrySpan] = {}
    current_id: str | None = None
    current_start: int | None = None
    for line_no in range(start_line, end_line + 1):
        line = lines[line_no - 1]
        match = re.match(r"\s*-\s+id:\s+([a-z0-9_-]+)\s*$", line)
        if match:
            if current_id is not None and current_start is not None:
                body = "\n".join(lines[current_start - 1 : line_no - 1])
                spans[current_id] = EntrySpan(current_id, current_start, line_no - 1, body)
            current_id = match.group(1)
            current_start = line_no
    if current_id is not None and current_start is not None:
        body = "\n".join(lines[current_start - 1 : end_line])
        spans[current_id] = EntrySpan(current_id, current_start, end_line, body)
    return spans


def source_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for src in data.get("sources", []):
        if isinstance(src, dict) and "id" in src:
            out[str(src["id"])] = src
    return out


def ids_in_section(text: str, section: str) -> list[str]:
    start, end = find_section_bounds(text, section)
    return list(parse_entry_spans(text, start, end).keys())


def line_of(span: EntrySpan, pattern: str) -> int | None:
    for offset, line in enumerate(span.text.splitlines(), start=0):
        if pattern in line:
            return span.start_line + offset
    return None


def selector_flags(selector: str) -> list[str]:
    flags: list[str] = []
    s = selector.strip()
    if s == "a[href]" or re.search(r"(^|,\s*)a\[href\](,|$)", s):
        flags.append("active_a_href")
    if '[href*="/"]' in s:
        flags.append("very_broad_any_path_substring")
    if '[href*="/blog/"]' in s:
        flags.append("wide_blog_substring")
    if '[href*="/learn/"]' in s:
        flags.append("wide_learn_substring")
    if 'article a[href^="https://' in s and "h2 a[" not in s and "h3 a[" not in s:
        flags.append("domain_wide_article_anchor")
    if "__" in s and "_disabled_placeholder_" in s:
        flags.append("disabled_placeholder")
    return flags


def has_disable_comment(span: EntrySpan) -> bool:
    return any(line.strip().startswith("#") for line in span.text.splitlines())


def cmd_lint(args: argparse.Namespace) -> int:
    path = Path(args.sources)
    text = load_text(path)
    data = load_yaml(path)
    s_map = source_map(data)
    start, end = find_section_bounds(text, args.section)
    spans = parse_entry_spans(text, start, end)

    failures: list[str] = []
    warnings: list[str] = []

    print(f"Section: {args.section} ({path}:{start}-{end})")
    print(f"Entries: {len(spans)}")

    for source_id, span in spans.items():
        src = s_map.get(source_id)
        if not src:
            warnings.append(f"{source_id}: present in text block but missing in YAML parse")
            continue
        if src.get("type") != "html":
            continue
        enabled = src.get("enabled", True)
        html = src.get("html") or {}
        selector = str(html.get("link_selector", "")).strip()
        flags = selector_flags(selector)
        selector_line = line_of(span, "link_selector:")
        enabled_line = line_of(span, "enabled:")

        if not enabled:
            if "disabled_placeholder" not in flags:
                warnings.append(
                    f"{source_id}:{selector_line or '?'} disabled html source without placeholder selector"
                )
            if not has_disable_comment(span):
                warnings.append(f"{source_id}:{enabled_line or '?'} disabled source lacks inline comment")
            continue

        if "active_a_href" in flags:
            failures.append(f"{source_id}:{selector_line or '?'} uses a[href]")
        if "very_broad_any_path_substring" in flags:
            failures.append(f"{source_id}:{selector_line or '?'} uses [href*=\"/\"]")
        if "wide_blog_substring" in flags:
            failures.append(f"{source_id}:{selector_line or '?'} uses wide /blog/ substring matcher")
        if "wide_learn_substring" in flags:
            failures.append(f"{source_id}:{selector_line or '?'} uses wide /learn/ substring matcher")
        if "domain_wide_article_anchor" in flags:
            warnings.append(f"{source_id}:{selector_line or '?'} article-wide domain selector may over-capture")

    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(f"- {item}")
    if warnings:
        print("\nWARNINGS:")
        for item in warnings:
            print(f"- {item}")

    if not failures and not warnings:
        print("\nOK: no lint findings for this section")
    elif not failures:
        print("\nOK (warnings only)")

    return 1 if failures else 0


def candidate_selectors(url: str) -> list[str]:
    u = url.lower()
    candidates = [
        'a[href^="/blog/"]:not([href="/blog"]):not([href="/blog/"])',
        'a[href^="./blog/"]:not([href="./blog"])',
        'a[href^="https://"]',
        'a[href^="/learn/"]:not([href="/learn"]):not([href="/learn/"])',
        'a[href^="./learn/"]:not([href="./learn"])',
        'a[href^="/changelog/"], a[href^="/changelog"]',
        'article h2 a[href], article h3 a[href]',
        "main a[href]",
    ]
    if "/learn" in u:
        return [
            'a[href^="/learn/"]:not([href="/learn"]):not([href="/learn/"])',
            'a[href^="./learn/"]:not([href="./learn"])',
            'article h2 a[href], article h3 a[href]',
            "main a[href]",
        ]
    if "autogen" in u:
        return ['a[href^="/autogen/0.2/blog/"]:not([href*="/tags/"])', "article a[href]", "main a[href]"]
    if "docs.langchain.com" in u or "langsmith" in u:
        return ['main a[href^="/langsmith/changelog"]', "main a[href]", "article a[href]"]
    return candidates


def selector_link_count(page_html: str, base_url: str, selector: str) -> tuple[int, list[str], str | None]:
    if lxml_html is None:
        return 0, [], "lxml unavailable"
    try:
        tree = lxml_html.fromstring(page_html)
        nodes = tree.cssselect(selector)
    except Exception as exc:
        return 0, [], str(exc)
    links: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        href = (node.attrib.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
    return len(links), links, None


def cmd_probe(args: argparse.Namespace) -> int:
    if httpx is None or lxml_html is None:
        print("probe requires httpx and lxml", file=sys.stderr)
        return 2

    path = Path(args.sources)
    text = load_text(path)
    data = load_yaml(path)
    s_map = source_map(data)

    ids: list[str] = [x.strip() for x in args.ids.split(",") if x.strip()] if args.ids else ids_in_section(text, args.section)

    client = httpx.Client(timeout=args.timeout, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    try:
        for source_id in ids:
            src = s_map.get(source_id)
            if not src:
                print(f"\n=== {source_id}\nmissing in YAML")
                continue
            if src.get("type") != "html":
                continue
            url = str(src.get("url", ""))
            print(f"\n=== {source_id} ({'enabled' if src.get('enabled', True) else 'disabled'})")
            print(f"url: {url}")
            try:
                resp = client.get(url)
                print(f"status: {resp.status_code} final: {resp.url}")
                if resp.status_code >= 400:
                    continue
                tree = lxml_html.fromstring(resp.text)
                current = ((src.get("html") or {}).get("link_selector")) if isinstance(src.get("html"), dict) else None
                selectors = [current] if current else []
                for cand in candidate_selectors(url):
                    if cand and cand not in selectors:
                        selectors.append(cand)

                for sel in selectors[: args.max_selectors]:
                    if not sel:
                        continue
                    try:
                        nodes = tree.cssselect(sel)
                    except Exception as exc:
                        print(f"  selector ERROR {sel!r}: {exc}")
                        continue
                    links: list[str] = []
                    seen: set[str] = set()
                    for node in nodes:
                        href = (node.attrib.get("href") or "").strip()
                        if not href:
                            continue
                        absolute = urljoin(str(resp.url), href)
                        if absolute in seen:
                            continue
                        seen.add(absolute)
                        links.append(absolute)
                    print(f"  selector: {sel}")
                    print(f"    links: {len(links)}")
                    for sample in links[: args.sample]:
                        print(f"    - {sample}")
            except Exception as exc:
                print(f"error: {type(exc).__name__}: {exc}")
    finally:
        client.close()
    return 0


def pick_selector(url: str, page_html: str, current: str | None) -> tuple[str | None, list[str]]:
    selectors: list[str] = []
    if current:
        selectors.append(current)
    for cand in candidate_selectors(url):
        if cand not in selectors:
            selectors.append(cand)

    scored: list[tuple[int, int, str, list[str]]] = []
    notes: list[str] = []
    for sel in selectors:
        count, links, err = selector_link_count(page_html, url, sel)
        if err is not None:
            notes.append(f"selector error {sel!r}: {err}")
            continue
        score = 0
        if 1 <= count <= 120:
            score += 10
        if 3 <= count <= 80:
            score += 10
        if '[href^="/blog/"]' in sel or '[href^="./blog/"]' in sel or '[href^="/learn/"]' in sel:
            score += 4
        if "h2 a[" in sel or "h3 a[" in sel:
            score += 6
        if '[href*="/blog/"]' in sel or '[href*="/learn/"]' in sel:
            score -= 4
        if 'a[href]' in sel and sel.strip() == "a[href]":
            score -= 20
        if count == 0:
            score -= 50
        # Prefer current selector if it looks healthy.
        if current and sel == current and count > 0:
            score += 2
        scored.append((score, count, sel, links))

    if not scored:
        return None, notes
    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    best = scored[0]
    notes.append(f"picked score={best[0]} count={best[1]} selector={best[2]}")
    return best[2], notes


def cmd_suggest_patch(args: argparse.Namespace) -> int:
    if httpx is None:
        print("suggest-patch requires httpx/lxml installed", file=sys.stderr)
        return 2
    path = Path(args.sources)
    text = load_text(path)
    data = load_yaml(path)
    s_map = source_map(data)
    ids = [x.strip() for x in args.ids.split(",") if x.strip()] if args.ids else ids_in_section(text, args.section)

    client = httpx.Client(timeout=args.timeout, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    try:
        for source_id in ids:
            src = s_map.get(source_id)
            if not src or src.get("type") != "html":
                continue
            if src.get("enabled", True) is False and not args.include_disabled:
                continue
            url = str(src.get("url", ""))
            print(f"\n# {source_id} ({url})")
            try:
                r = client.get(url)
                print(f"# status={r.status_code} final={r.url}")
                if r.status_code >= 400:
                    print("# skip: non-200")
                    continue
                current = None
                if isinstance(src.get("html"), dict):
                    current = src["html"].get("link_selector")
                best, notes = pick_selector(str(r.url), r.text, str(current) if current else None)
                for note in notes[:3]:
                    print(f"# {note}")
                if not best:
                    print("# no selector suggestion")
                    continue
                print("html:")
                print(f"  link_selector: {best}")
                print("  extraction_strategy: readability")
            except Exception as exc:
                print(f"# error: {type(exc).__name__}: {exc}")
    finally:
        client.close()
    return 0


def update_link_selector_in_entry(entry_text: str, new_selector: str) -> tuple[str, bool]:
    lines = entry_text.splitlines()
    changed = False
    for i, line in enumerate(lines):
        if "link_selector:" not in line:
            continue
        indent = line.split("link_selector:", 1)[0]
        new_line = f"{indent}link_selector: {new_selector}"
        if line != new_line:
            lines[i] = new_line
            changed = True
        return "\n".join(lines), changed
    return entry_text, False


def extract_link_selector_line(entry_text: str) -> tuple[int | None, str | None]:
    for i, line in enumerate(entry_text.splitlines(), start=1):
        if "link_selector:" in line:
            return i, line
    return None, None


def replace_entry_in_text(full_text: str, span: EntrySpan, new_entry_text: str) -> str:
    lines = full_text.splitlines()
    before = lines[: span.start_line - 1]
    after = lines[span.end_line :]
    middle = new_entry_text.splitlines()
    rebuilt = before + middle + after
    return "\n".join(rebuilt) + ("\n" if full_text.endswith("\n") else "")


def cmd_apply_suggested(args: argparse.Namespace) -> int:
    if httpx is None:
        print("apply-suggested requires httpx/lxml installed", file=sys.stderr)
        return 2

    path = Path(args.sources)
    text = load_text(path)
    data = load_yaml(path)
    s_map = source_map(data)
    ids = [x.strip() for x in args.ids.split(",") if x.strip()] if args.ids else ids_in_section(text, args.section)

    updated_text = text
    applied = 0
    client = httpx.Client(timeout=args.timeout, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    try:
        for source_id in ids:
            # Recompute spans each iteration because line ranges shift after edits.
            start, end = find_section_bounds(updated_text, args.section)
            spans = parse_entry_spans(updated_text, start, end)
            span = spans.get(source_id)
            src = s_map.get(source_id)
            if not span or not src or src.get("type") != "html":
                continue
            if src.get("enabled", True) is False and not args.include_disabled:
                continue

            url = str(src.get("url", ""))
            current_selector = None
            if isinstance(src.get("html"), dict):
                current_selector = src["html"].get("link_selector")

            try:
                resp = client.get(url)
                if resp.status_code >= 400:
                    print(f"\n{source_id}: skip status={resp.status_code} url={resp.url}")
                    continue
                best, notes = pick_selector(str(resp.url), resp.text, str(current_selector) if current_selector else None)
                if not best:
                    print(f"\n{source_id}: no selector suggestion")
                    continue
                new_entry_text, changed = update_link_selector_in_entry(span.text, best)
                _, old_line = extract_link_selector_line(span.text)
                rel_line, new_line = extract_link_selector_line(new_entry_text)
                abs_line = span.start_line + rel_line - 1 if rel_line is not None else None
                print(f"\n{source_id}")
                print(f"  url: {resp.url}")
                for note in notes[:2]:
                    print(f"  note: {note}")
                print(f"  current: {current_selector}")
                print(f"  best:    {best}")
                if args.diff and old_line and new_line:
                    print(f"  diff ({path}:{abs_line or '?'})")
                    print(f"  - {old_line.strip()}")
                    print(f"  + {new_line.strip()}")
                if not changed:
                    print("  result: unchanged")
                    continue
                if args.write:
                    updated_text = replace_entry_in_text(updated_text, span, new_entry_text)
                    applied += 1
                    print("  result: applied")
                else:
                    print("  result: dry-run (use --write to apply)")
            except Exception as exc:
                print(f"\n{source_id}: error {type(exc).__name__}: {exc}")
    finally:
        client.close()

    if args.write and applied:
        path.write_text(updated_text, encoding="utf-8")
        print(f"\nWrote {path} (updated {applied} source(s))")
    elif args.write:
        print("\nNo changes written")
    return 0


def cmd_fetch_check(args: argparse.Namespace) -> int:
    path = Path(args.sources)
    text = load_text(path)
    data = load_yaml(path)
    s_map = source_map(data)
    ids = [x.strip() for x in args.ids.split(",") if x.strip()] if args.ids else ids_in_section(text, args.section)

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    try:
        placeholders = ",".join("?" for _ in ids)
        if not ids:
            print("No source ids selected")
            return 0
        print(f"DB: {args.db}")
        cur.execute(
            f"""
            SELECT s.source_key, COUNT(a.id) AS cnt, MAX(a.discovered_at) AS last_seen
            FROM sources s
            LEFT JOIN articles a ON a.source_id = s.id
            WHERE s.source_key IN ({placeholders})
            GROUP BY s.source_key
            ORDER BY cnt DESC, s.source_key
            """,
            ids,
        )
        rows = cur.fetchall()
        print(f"Section IDs: {len(ids)}")
        print("\nCounts:")
        for key, cnt, last_seen in rows:
            status = "DISABLED" if s_map.get(key, {}).get("enabled", True) is False else "ENABLED"
            print(f"- {key}: {cnt} ({status}) last_seen={last_seen}")

        zero_enabled = [
            key
            for key, cnt, _ in rows
            if cnt == 0 and s_map.get(key, {}).get("enabled", True) and s_map.get(key, {}).get("type") == "html"
        ]
        if zero_enabled:
            print("\nEnabled HTML with zero articles:")
            for key in zero_enabled:
                print(f"- {key}")

        cur.execute(
            "SELECT run_id, started_at, finished_at, status, fetched_count, new_count, duplicate_count, error_count "
            "FROM fetch_runs ORDER BY rowid DESC LIMIT ?",
            (args.runs,),
        )
        runs = cur.fetchall()
        if runs:
            print("\nRecent fetch_runs:")
            for r in runs:
                print(
                    f"- run_id={r[0]} status={r[3]} fetched={r[4]} new={r[5]} dup={r[6]} errors={r[7]} "
                    f"started={r[1]} finished={r[2]}"
                )
        if args.fetch_log:
            log_path = Path(args.fetch_log)
            if not log_path.exists():
                print(f"\nFetch log not found: {log_path}")
            else:
                print(f"\nErrors from fetch log (filtered to section ids): {log_path}")
                shown = 0
                for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if "source_fetch_failed" not in line:
                        continue
                    try:
                        payload = json.loads(line)
                    except Exception:
                        continue
                    source_id = payload.get("source_id")
                    if source_id not in ids:
                        continue
                    shown += 1
                    cause = payload.get("cause_type") or payload.get("error_type")
                    msg = (payload.get("cause_message") or payload.get("error_message") or "").replace("\n", " ")
                    print(f"- {source_id}: {cause} :: {msg[:220]}")
                if shown == 0:
                    print("- none")
    finally:
        conn.close()
    return 0


def cmd_db_bootstrap(args: argparse.Namespace) -> int:
    ensure_src_path()

    from app.config.sources import bootstrap_sources_into_db
    from app.storage.models_sql import Base
    from app.storage.source_repo import SourceRepo

    engine = create_engine(args.database_url, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)
    session = session_factory()
    try:
        repo = SourceRepo(session)
        imported_sources = bootstrap_sources_into_db(path=Path(args.sources), repo=repo)
        session.commit()
        print(f"Imported {len(imported_sources)} source row(s) from {args.sources} into {args.database_url}")
        for source in imported_sources[: args.limit]:
            print(f"- {source.source_key}: {source.type} {source.url}")
        if len(imported_sources) > args.limit:
            print(f"... truncated {len(imported_sources) - args.limit} additional row(s)")
    finally:
        session.close()
        engine.dispose()
    return 0


def cmd_db_export(args: argparse.Namespace) -> int:
    ensure_src_path()

    from app.core.sources.onboarding import export_approved_sources_yaml

    engine = create_engine(args.database_url, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        snapshot = export_approved_sources_yaml(session=session)
    finally:
        session.close()
        engine.dispose()

    output_path = Path(args.output)
    output_path.write_text(snapshot, encoding="utf-8")
    print(f"Wrote approved-source snapshot to {output_path}")
    return 0


def cmd_db_review(args: argparse.Namespace) -> int:
    ensure_src_path()

    from app.storage.models_sql import SourceCandidate

    engine = create_engine(args.database_url, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        stmt = select(SourceCandidate).order_by(SourceCandidate.id.asc())
        if args.batch_id is not None:
            stmt = stmt.where(SourceCandidate.batch_id == args.batch_id)
        if args.status:
            stmt = stmt.where(SourceCandidate.status == args.status)
        rows = session.execute(stmt.limit(args.limit)).scalars().all()
        if not rows:
            print("No source candidates matched the filter")
            return 0
        for row in rows:
            print(
                f"- id={row.id} batch={row.batch_id} status={row.status} "
                f"validation={row.validation_status} type={row.candidate_type} url={row.normalized_url}"
            )
    finally:
        session.close()
        engine.dispose()
    return 0


def cmd_db_validate(args: argparse.Namespace) -> int:
    ensure_src_path()

    from app.core.sources.onboarding import run_source_validation_batch

    candidate_ids = db_ids_arg(args.ids)
    if args.batch_id is None and not candidate_ids:
        print("db-validate requires --batch-id or --ids", file=sys.stderr)
        return 2

    engine = create_engine(args.database_url, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        results = run_source_validation_batch(
            session=session,
            batch_id=args.batch_id,
            candidate_ids=candidate_ids or None,
        )
        session.commit()
        if not results:
            print("No source candidates were selected for validation")
            return 0
        for result in results:
            detail = result.validation_error or "ok"
            print(
                f"- id={result.candidate_id} status={result.status} "
                f"detected_type={result.detected_type} detail={detail}"
            )
    finally:
        session.close()
        engine.dispose()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Helper for YAML seeding and DB-backed source onboarding flows"
    )
    parser.add_argument("--sources", default="sources.yaml", help="Path to sources.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    lint = sub.add_parser("lint", help="Static lint for a section in sources.yaml")
    lint.add_argument("--section", default=SECTION_DEFAULT, help="Section header substring")
    lint.set_defaults(func=cmd_lint)

    probe = sub.add_parser("probe", help="Fetch HTML pages and compare current/candidate selectors")
    probe.add_argument("--section", default=SECTION_DEFAULT, help="Section header substring")
    probe.add_argument("--ids", help="Comma-separated source ids (defaults to all ids in section)")
    probe.add_argument("--timeout", type=float, default=20.0)
    probe.add_argument("--sample", type=int, default=5)
    probe.add_argument("--max-selectors", type=int, default=6)
    probe.set_defaults(func=cmd_probe)

    suggest = sub.add_parser("suggest-patch", help="Print candidate html: YAML snippets for HTML sources")
    suggest.add_argument("--section", default=SECTION_DEFAULT, help="Section header substring")
    suggest.add_argument("--ids", help="Comma-separated source ids")
    suggest.add_argument("--timeout", type=float, default=20.0)
    suggest.add_argument("--include-disabled", action="store_true")
    suggest.set_defaults(func=cmd_suggest_patch)

    apply_suggested = sub.add_parser(
        "apply-suggested",
        help="Apply suggested link_selector values for selected HTML sources (dry-run by default)",
    )
    apply_suggested.add_argument("--section", default=SECTION_DEFAULT, help="Section header substring")
    apply_suggested.add_argument("--ids", help="Comma-separated source ids")
    apply_suggested.add_argument("--timeout", type=float, default=20.0)
    apply_suggested.add_argument("--include-disabled", action="store_true")
    apply_suggested.add_argument("--diff", action="store_true", help="Show line-level diff for link_selector")
    apply_suggested.add_argument("--write", action="store_true", help="Write changes to sources.yaml")
    apply_suggested.set_defaults(func=cmd_apply_suggested)

    check = sub.add_parser("fetch-check", help="Summarize DB results for a section after fetch runs")
    check.add_argument("--section", default=SECTION_DEFAULT, help="Section header substring")
    check.add_argument("--ids", help="Comma-separated source ids")
    check.add_argument("--db", default="data/ai_news.db", help="SQLite DB path")
    check.add_argument("--runs", type=int, default=5, help="How many recent fetch_runs to show")
    check.add_argument("--fetch-log", help="Optional fetch log path to summarize source_fetch_failed lines")
    check.set_defaults(func=cmd_fetch_check)

    db_bootstrap = sub.add_parser(
        "db-bootstrap",
        help="Import sources.yaml into the DB-backed sources registry",
    )
    db_bootstrap.add_argument(
        "--database-url",
        default="sqlite:///./data/ai_news.db",
        help="SQLAlchemy database URL",
    )
    db_bootstrap.add_argument("--limit", type=int, default=20, help="How many imported rows to print")
    db_bootstrap.set_defaults(func=cmd_db_bootstrap)

    db_export = sub.add_parser(
        "db-export",
        help="Export enabled DB-backed sources to a deterministic YAML snapshot",
    )
    db_export.add_argument(
        "--database-url",
        default="sqlite:///./data/ai_news.db",
        help="SQLAlchemy database URL",
    )
    db_export.add_argument(
        "--output",
        default="tmp/approved_sources.snapshot.yaml",
        help="Path for the generated YAML snapshot",
    )
    db_export.set_defaults(func=cmd_db_export)

    db_review = sub.add_parser(
        "db-review",
        help="List DB-backed source candidates for review",
    )
    db_review.add_argument(
        "--database-url",
        default="sqlite:///./data/ai_news.db",
        help="SQLAlchemy database URL",
    )
    db_review.add_argument("--batch-id", type=int, help="Optional import batch id")
    db_review.add_argument("--status", help="Optional candidate status filter")
    db_review.add_argument("--limit", type=int, default=50, help="Maximum candidates to print")
    db_review.set_defaults(func=cmd_db_review)

    db_validate = sub.add_parser(
        "db-validate",
        help="Run DB-backed candidate validation for a batch or explicit ids",
    )
    db_validate.add_argument(
        "--database-url",
        default="sqlite:///./data/ai_news.db",
        help="SQLAlchemy database URL",
    )
    db_validate.add_argument("--batch-id", type=int, help="Validate all candidates in a batch")
    db_validate.add_argument("--ids", help="Comma-separated candidate ids")
    db_validate.set_defaults(func=cmd_db_validate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
