"""Stored bulletin preview HTML; behavior and decisions: src/app/web/pages.md."""
import json
import re
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

from app.storage.models_sql import BulletinRow

_TEMPLATE = Path(__file__).with_name("bulletin.html")
_HTTP = re.compile(r"^https?://", re.IGNORECASE)


def _text(value: Any) -> str:
    return escape(str(value))


def _outlet(link: dict[str, str]) -> str:
    label = _text(link["outlet"])
    url = link["url"]
    if _HTTP.match(url):
        return f'<a href="{_text(url)}">{label}</a>'
    return label


def _story(story: dict[str, Any]) -> str:
    paragraphs = "".join(f"<p>{_text(note)}</p>" for note in story.get("site_note", []))
    gloss = f'<p>{_text(story["gloss"])}</p>' if story.get("gloss") else ""
    meta = (f'{_text(story["area"])} | text_origin: {_text(story.get("text_origin", "title"))}'
            f' | origin: {_text(story["origin"])}')
    links = " | ".join(_outlet(link) for link in story["links"])
    heading = _text(story.get("headline") or story["title"])
    return (f'<article class="signal-card"><h2>{heading}</h2>'
            f'{paragraphs}{gloss}<p class="signal-meta">{meta}</p>'
            f'<div class="signal-meta">{links}</div></article>')


def _ready(row: BulletinRow) -> str:
    payload = row.payload
    stories = [*payload["key_results"], payload.get("rubric_story"),
               *payload["cooperation"], payload.get("incident_story")]
    content = "".join(_story(story) for story in stories if story is not None)
    numbers = _text(json.dumps(row.numbers, indent=2))
    return (f'<h1>Bulletin for {row.day.isoformat()} | Day {_text(payload["day_number"])}</h1>'
            f'{content}<section id="bulletin-numbers"><h2>Stored numbers</h2>'
            f'<pre>{numbers}</pre></section>')


def _navigation(day: date, yesterday: date) -> str:
    links = []
    if day > date.min:
        previous = (day - timedelta(days=1)).isoformat()
        links.append(f'<a rel="prev" href="/bulletin?date={previous}">Previous day</a>')
    if day < yesterday:
        following = (day + timedelta(days=1)).isoformat()
        links.append(f'<a rel="next" href="/bulletin?date={following}">Next day</a>')
    return f'<nav aria-label="Bulletin dates">{" | ".join(links)}</nav>'


def render_bulletin_page(row: BulletinRow | None, day: date | None, *,
                         message: str | None = None) -> str:
    """Render a ready row, a skipped/missing day or a storage error in the same shell."""
    if row is not None and row.status == "ready":
        content = _ready(row)
    else:
        title = f"Bulletin for {day.isoformat()}" if day else "Bulletin preview"
        note = message or ("No bulletin for this day." if day else "No bulletin is stored yet.")
        reason = f"<p>{_text(row.reason)}</p>" if row is not None and row.reason else ""
        content = f"<h1>{title}</h1><p>{_text(note)}</p>{reason}"
    if day is not None:
        content += (f'<p><a href="/?date={day.isoformat()}">Daily digest for this day</a></p>'
                    + _navigation(day, datetime.now(UTC).date() - timedelta(days=1)))
    return _TEMPLATE.read_text(encoding="utf-8").replace("__BULLETIN_CONTENT__", content)
