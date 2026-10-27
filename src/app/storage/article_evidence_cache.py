"""Private, resumable source-page cache. No providers or production writes."""
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from lxml import html as lxml_html
from lxml.etree import LxmlError  # pylint: disable=no-name-in-module

from app.ingest.date_evidence import extract_date_evidence
from app.ingest.fetcher import BOT_TOKEN, DEFAULT_USER_AGENT
from app.ingest.html import extract_article_text
from app.ingest.page_filter import url_exclusion_reason
from app.storage.journal_files import fingerprint, private_write

CACHE_VERSION = "article-source-cache-1"
EXTRACTION_VERSION = "article-source-extraction-1"
_BLOCK_TITLE = re.compile(
    r"access denied|just a moment|verify you are human|captcha|page not found|"
    r"404 not found|sign in|log in|enable javascript", re.I)
_PAYWALL = re.compile(r"subscribe to (?:continue|read)|subscription required|"
                      r"already a subscriber\?? (?:log|sign) in", re.I)


class HostUnavailableError(RuntimeError):
    """A source requested pacing or repeatedly returned service unavailable."""


def url_key(url: str) -> str:
    return hashlib.sha256(url.split("#", 1)[0].encode()).hexdigest()


def validate_source_url(url: str) -> None:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if (parts.scheme not in {"http", "https"} or not host or parts.username
            or host == "localhost" or host.endswith((".localhost", ".local", ".internal"))):
        raise ValueError("Invalid public source URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("Non-public source address")


def private_bytes(path: Path, value: bytes) -> None:
    staged = path.with_suffix(path.suffix + ".next")
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, path)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def inspect_page(page_html: str, original_url: str, final_url: str) -> dict[str, Any]:
    """Extraction quality is not an admission verdict or deletion authorization."""
    tree = lxml_html.fromstring(page_html)
    dates = extract_date_evidence(page_html, final_url)
    title_nodes = tree.xpath('//h1 | //meta[@property="og:title"] | //title')
    title = ""
    for tag in ("h1", "meta", "title"):
        matches = [node for node in title_nodes if node.tag == tag]
        if matches:
            title = " ".join((matches[0].get("content") or matches[0].text_content()).split())
            if title:
                break
    issues: list[str] = []
    redirected = original_url.rstrip("/") != final_url.rstrip("/")
    if redirected and url_exclusion_reason(final_url):
        issues.append("redirect_to_non_article")
    if _BLOCK_TITLE.search(title):
        issues.append("blocked_or_error_page")
    article_markers = tree.xpath('//article | //main | //meta[@property="og:type" '
                                 'and @content="article"]')
    if not title or (not article_markers and not dates["candidates"]):
        issues.append("article_identity_unverified")
    for node in tree.xpath('//script[@type="application/ld+json"]'):
        # Access restrictions are retained as quality signals, even if an excerpt extracts.
        if re.search(r'"isAccessibleForFree"\s*:\s*(?:false|"false")', node.text or "", re.I):
            issues.append("paywall")
    try:
        content = extract_article_text(page_html, final_url) or ""
    except (ValueError, TypeError, AttributeError, LxmlError):
        content = ""
        issues.append("extraction_failed")
    if len(content.strip()) < 300:
        issues.append("short_or_empty_extraction")
    if _PAYWALL.search(content[:2000]):
        issues.append("paywall")
    canonical = tree.xpath('//link[contains(concat(" ", @rel, " "), " canonical ")]/@href')
    return {"version": EXTRACTION_VERSION, "title": title, "text": content,
            "date_evidence": dates, "quality": "unresolved" if issues else "extracted",
            "issues": sorted(set(issues)), "canonical_hint": canonical[0] if canonical else None,
            "admission": "not_evaluated"}


class PageCache:
    """One durable attempt per exact source URL; restart never refetches an attempt."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        (root / "pages").mkdir(exist_ok=True, mode=0o700)

    def page_dir(self, url: str) -> Path:
        path = self.root / "pages" / url_key(url)
        path.mkdir(exist_ok=True, mode=0o700)
        return path

    def attempt(self, url: str) -> dict[str, Any] | None:
        path = self.page_dir(url) / "attempt.json"
        return json.loads(path.read_text()) if path.exists() else None

    def begin(self, url: str) -> bool:
        if self.attempt(url) is not None:
            return False
        private_write(self.page_dir(url) / "attempt.json", {
            "version": CACHE_VERSION, "url": url, "state": "started",
            "started_at": datetime.now(UTC).isoformat(), "model_calls": 0})
        return True

    def finish(self, url: str, result: dict[str, Any]) -> None:
        private_write(self.page_dir(url) / "attempt.json", {
            **(self.attempt(url) or {}), **result, "finished_at": datetime.now(UTC).isoformat()})

    def extract_saved(self, url: str) -> dict[str, Any]:
        directory = self.page_dir(url)
        response = json.loads((directory / "response.json").read_text())
        body = (directory / "body.bin").read_bytes()
        if _sha(body) != response["body_sha256"]:
            raise ValueError("Cached response hash mismatch")
        page_html = body.decode(response["encoding"] or "utf-8", errors="replace")
        private_bytes(directory / "page.html", page_html.encode())
        try:
            evidence = inspect_page(page_html, url, response["final_url"])
        except (ValueError, TypeError, AttributeError, LxmlError):
            evidence = {"quality": "unresolved", "issues": ["invalid_html"], "text": "",
                        "date_evidence": extract_date_evidence("", response["final_url"]),
                        "admission": "not_evaluated", "version": EXTRACTION_VERSION}
        if response["status_code"] != 200:
            evidence["quality"] = "unresolved"
            evidence["issues"].append(f"http_{response['status_code']}")
        if response.get("truncated"):
            evidence["quality"] = "unresolved"
            evidence["issues"].append("response_too_large")
        if "html" not in response.get("content_type", "").lower():
            evidence["quality"] = "unresolved"
            evidence["issues"].append("non_html_response")
        content = evidence.pop("text")
        private_bytes(directory / "text.txt", content.encode())
        evidence.update(text_sha256=_sha(content.encode()), html_sha256=_sha(page_html.encode()),
                        text_chars=len(content), response_sha256=fingerprint(response))
        private_write(directory / "evidence.json", evidence)
        result = {"state": "completed", "quality": evidence["quality"],
                  "issues": evidence["issues"], "text_chars": len(content),
                  "evidence_sha256": fingerprint(evidence),
                  "published_status": evidence["date_evidence"]["published"]["status"],
                  "modified_status": evidence["date_evidence"]["modified"]["status"]}
        self.finish(url, result)
        return result

    def status(self, urls: list[str]) -> dict[str, Any]:
        states: Counter[str] = Counter()
        quality: Counter[str] = Counter()
        dates: Counter[str] = Counter()
        issues: Counter[str] = Counter()
        for url in urls:
            attempt = self.attempt(url)
            states[attempt["state"] if attempt else "pending"] += 1
            if attempt:
                if attempt.get("quality"):
                    quality[attempt["quality"]] += 1
                if attempt.get("published_status"):
                    dates[attempt["published_status"]] += 1
                issues.update(attempt.get("issues", []))
        return {"urls": len(urls), "states": dict(states), "quality": dict(quality),
                "publication_dates": dict(dates), "issues": dict(issues), "model_calls": 0}


OUTAGE_HOSTS = 10  # distinct hosts failing to connect, no success between


class SourcePageDownloader:  # pylint: disable=too-many-instance-attributes
    """Bounded downloads with per-host pacing, manual redirects and no retry loop."""

    def __init__(self, cache: PageCache, client: httpx.AsyncClient, *, concurrency: int = 8,
                 host_interval: float = 1.0, max_bytes: int = 10 * 1024 * 1024,
                 respect_robots: bool = True):
        self.cache = cache
        self.client = client
        self.slots = asyncio.Semaphore(concurrency)
        self.host_interval = host_interval
        self.max_bytes = max_bytes
        self.locks: dict[str, asyncio.Lock] = {}
        self.next_allowed: dict[str, float] = {}
        self.outage = False
        self.connection_failures: set[str] = set()
        self.blocked_hosts: set[str] = set()
        self.service_failures: Counter[str] = Counter()
        self.respect_robots = respect_robots
        self.robot_locks: dict[str, asyncio.Lock] = {}
        self.robots: dict[str, RobotFileParser] = {}

    async def _get(self, url: str, original_url: str | None) -> dict[str, Any]:
        validate_source_url(url)
        parts = urlsplit(url)
        host = (parts.hostname or "").removeprefix("www.")
        async with self.locks.setdefault(host, asyncio.Lock()):
            if host in self.blocked_hosts:
                raise HostUnavailableError("Host paused; preserve unresolved")
            delay = self.next_allowed.get(host, 0) - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            async with self.slots:
                if self.outage:
                    raise RuntimeError("Download outage; keep undispatched targets pending")
                if original_url and self.cache.attempt(original_url) is None:
                    self.cache.begin(original_url)
                self.next_allowed[host] = time.monotonic() + self.host_interval
                async with self.client.stream("GET", url, follow_redirects=False) as response:
                    body = bytearray()
                    truncated = False
                    async for chunk in response.aiter_bytes():
                        remaining = self.max_bytes - len(body)
                        body.extend(chunk[:remaining])
                        if len(chunk) > remaining:
                            truncated = True
                            break
                    return {"final_url": str(response.url), "status_code": response.status_code,
                            "content_type": response.headers.get("content-type", ""),
                            "encoding": response.encoding, "body": bytes(body),
                            "location": response.headers.get("location"), "truncated": truncated,
                            "retry_after": response.headers.get("retry-after"),
                            "fetched_at": datetime.now(UTC).isoformat()}

    async def _follow_robots_redirects(self, saved: dict[str, Any]) -> dict[str, Any]:
        history = list(saved.get("redirects", []))
        for _ in range(max(0, 5 - len(history))):
            if (saved["status_code"] not in {301, 302, 303, 307, 308}
                    or not saved.get("location") or saved.get("truncated")):
                break
            destination = urljoin(saved["final_url"], saved["location"])
            history.append({k: v for k, v in saved.items() if k not in {"body", "redirects"}})
            response = await self._get(destination, None)
            body = response.pop("body")
            saved = {**response, "body": body.decode("utf-8", errors="replace"),
                     "redirects": history}
        return saved

    async def _robots_allowed(self, url: str) -> bool:
        validate_source_url(url)
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        async with self.robot_locks.setdefault(origin, asyncio.Lock()):
            if origin not in self.robots:
                directory = self.cache.root / "robots"
                directory.mkdir(exist_ok=True, mode=0o700)
                path = directory / (url_key(origin) + ".json")
                if path.exists():
                    saved = json.loads(path.read_text())
                else:
                    response = await self._get(origin + "/robots.txt", None)
                    body = response.pop("body")
                    saved = {**response, "body": body.decode("utf-8", errors="replace")}
                saved = await self._follow_robots_redirects(saved)
                private_write(path, saved)
                parser = RobotFileParser()
                if saved["status_code"] == 200 and not saved["truncated"]:
                    parser.parse(saved["body"].splitlines())
                elif saved["status_code"] in {404, 410}:
                    parser.parse([])
                else:
                    parser.parse(["User-agent: *", "Disallow: /"])
                self.robots[origin] = parser
            parser = self.robots[origin]
            delay = parser.crawl_delay(BOT_TOKEN)
            if delay:
                host = (parts.hostname or "").removeprefix("www.")
                self.next_allowed[host] = max(self.next_allowed.get(host, 0),
                                              time.monotonic() + float(delay))
            return parser.can_fetch(BOT_TOKEN, url)

    async def fetch_one(self, url: str) -> None:  # pylint: disable=too-many-branches,too-many-statements
        attempt = self.cache.attempt(url)
        if attempt:
            directory = self.cache.page_dir(url)
            if attempt["state"] == "started" and (directory / "response.json").exists():
                await asyncio.to_thread(self.cache.extract_saved, url)
            return
        if self.outage:
            return
        current, history = url, []
        try:
            for _ in range(6):
                if not await self._robots_allowed(current):
                    self.cache.finish(url, {"state": "blocked", "quality": "unresolved",
                                            "issues": ["robots_disallowed_or_unavailable"]})
                    return
                response = await self._get(current, url)
                self.connection_failures.clear()
                status = response["status_code"]
                if status in {429, 503}:
                    host = (urlsplit(current).hostname or "").removeprefix("www.")
                    retry = response.get("retry_after") or "60"
                    seconds = max(60.0, min(float(retry) if retry.isdigit() else 60.0, 3600.0))
                    self.next_allowed[host] = time.monotonic() + seconds
                    self.service_failures[host] += 1
                    if status == 429 or self.service_failures[host] >= 3:
                        self.blocked_hosts.add(host)
                if status not in {301, 302, 303, 307, 308} or not response["location"]:
                    break
                destination = urljoin(current, response["location"])
                history.append({k: v for k, v in response.items() if k != "body"})
                if url_exclusion_reason(destination):
                    response["redirect_issue"] = "redirect_to_non_article"
                    break
                current = destination
            else:
                response["redirect_issue"] = "too_many_redirects"
            directory = self.cache.page_dir(url)
            body = response.pop("body")
            private_bytes(directory / "body.bin", body)
            response.update(body_sha256=_sha(body), redirects=history, original_url=url)
            private_write(directory / "response.json", response)
            result = await asyncio.to_thread(self.cache.extract_saved, url)
            if response.get("redirect_issue"):
                result["quality"] = "unresolved"
                result["issues"].append(response["redirect_issue"])
                evidence_path = directory / "evidence.json"
                evidence = json.loads(evidence_path.read_text())
                evidence.update(quality=result["quality"], issues=result["issues"])
                private_write(evidence_path, evidence)
                result["evidence_sha256"] = fingerprint(evidence)
                self.cache.finish(url, result)
        except HostUnavailableError:
            self.cache.finish(url, {"state": "blocked", "quality": "unresolved",
                                    "issues": ["host_rate_limit_or_unavailable"]})
        except RuntimeError:
            if self.cache.attempt(url):
                self.cache.finish(url, {"state": "failed", "quality": "unresolved",
                                        "issues": ["download_outage"]})
        except (httpx.HTTPError, ValueError, OSError, LookupError) as exc:
            if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
                self.connection_failures.add(urlsplit(current).hostname or "")
                if len(self.connection_failures) >= OUTAGE_HOSTS:
                    self.outage = True
            # Exception messages can contain URLs/content. Emit only the exception class.
            self.cache.finish(url, {"state": "failed", "quality": "unresolved",
                                    "issues": [type(exc).__name__]})


def make_http_client(concurrency: int = 8) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0),
                             headers={"User-Agent": DEFAULT_USER_AGENT},
                             limits=httpx.Limits(max_connections=concurrency,
                                                max_keepalive_connections=concurrency),
                             follow_redirects=False)
