"""Stored bulletin preview HTML; behavior and decisions: src/app/web/pages.md."""
import json
import re
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

from app.core.bulletin.phrases import load_phrases
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


def _story_heading(story: dict[str, Any]) -> str:
    return _text(story.get("headline") or story["title"])


def _paragraph(value: Any, class_name: str) -> str:
    return f'<p class="{class_name}">{_text(value)}</p>' if value else ""


def _story(story: dict[str, Any]) -> str:
    paragraphs = "".join(f"<p>{_text(note)}</p>" for note in story.get("site_note", []))
    gloss = _paragraph(story.get("gloss"), "gloss")
    reaction = _paragraph(story.get("reaction"), "reaction")
    links = ", ".join(_outlet(link) for link in story["links"])
    return (f'<article class="story"><p class="area">{_text(story["area"])}</p>'
            f'<h3>{_story_heading(story)}</h3>{paragraphs}{gloss}{reaction}'
            f'<div class="sources">Sources: {links}</div></article>')


def _section(title: str, stories: list[dict[str, Any] | None]) -> str:
    content = "".join(_story(story) for story in stories if story is not None)
    if not content:
        return ""
    return (f'<section class="issue-section"><h2>{_text(title)}</h2>'
            f'<div class="stories">{content}</div></section>')


def _incidents(payload: dict[str, Any]) -> str:
    if not payload["incidents"]:
        return ""
    story = payload.get("incident_story")
    content = f'<p class="among">Among them</p>{_story(story)}' if story else ""
    return (f'<section class="issue-section incidents">'
            f'<h2>Isolated incidents: {_text(payload["incidents"])}</h2>{content}</section>')


def _checking(row: BulletinRow) -> str:
    payload = row.payload
    stories = [*payload["key_results"], payload.get("rubric_story"),
               *payload["cooperation"], payload.get("incident_story")]
    notes = "".join(
        f'<li><strong>{_story_heading(story)}</strong>: '
        f'text_origin: {_text(story.get("text_origin", "title"))} | '
        f'origin: {_text(story["origin"])}</li>' for story in stories if story is not None)
    numbers = _text(json.dumps(row.numbers, indent=2))
    return (f'<details class="checking"><summary>For checking</summary><ul>{notes}</ul>'
            f'<h2>Stored numbers</h2><pre id="bulletin-numbers">{numbers}</pre></details>')


def _ready(row: BulletinRow) -> str:
    payload = row.payload
    day = row.day.isoformat()
    headline = payload["headline"] or f"Bulletin for {day}"
    sections = (_section("Key results", payload["key_results"])
                + _section(payload["rubric_name"], [payload.get("rubric_story")])
                + _section("Cooperation with humanity", payload["cooperation"])
                + _incidents(payload))
    footnote = (_paragraph(load_phrases()["cut"]["footnote"], "footnote")
                if payload["headline_cut"] else "")
    return (f'<header class="issue-header"><p class="byline">{_text(payload["byline"])}</p>'
            f'<time datetime="{day}">{day}</time><h1>{_text(headline)}</h1>'
            f'{_paragraph(payload["opening"], "opening")}'
            f'{_paragraph(payload["numbers"], "numbers-line")}</header>{sections}'
            f'<div class="issue-close">{_paragraph(payload["closing"], "closing")}'
            f'<a class="full-report" href="/?date={day}">'
            f'Full report ({_text(payload["items"])}) &#8594;</a>{footnote}</div>')


def _navigation(day: date, yesterday: date) -> str:
    links = []
    if day > date.min:
        previous = (day - timedelta(days=1)).isoformat()
        links.append(f'<a rel="prev" href="/bulletin?date={previous}">Previous day</a>')
    if day < yesterday:
        following = (day + timedelta(days=1)).isoformat()
        links.append(f'<a rel="next" href="/bulletin?date={following}">Next day</a>')
    return f'<nav aria-label="Bulletin dates">{"".join(links)}</nav>'


def _status(row: BulletinRow | None, day: date | None, message: str | None) -> str:
    title = f"Bulletin for {day.isoformat()}" if day else "Bulletin preview"
    note = message or ("No bulletin for this day." if day else "No bulletin is stored yet.")
    reason = f"<p>{_text(row.reason)}</p>" if row is not None and row.reason else ""
    content = f'<section class="status"><h1>{title}</h1><p>{_text(note)}</p>{reason}</section>'
    if day is not None:
        content += (f'<p><a class="full-report" href="/?date={day.isoformat()}">'
                    'Daily digest for this day</a></p>')
    return content


def render_bulletin_page(row: BulletinRow | None, day: date | None, *,
                         message: str | None = None) -> str:
    """Render a ready row, a skipped/missing day or a storage error in the same shell."""
    if row is not None and row.status == "ready":
        content = _ready(row)
        checking = _checking(row)
    else:
        content = _status(row, day, message)
        checking = ""
    if day is not None:
        content += _navigation(day, datetime.now(UTC).date() - timedelta(days=1))
    return _TEMPLATE.read_text(encoding="utf-8").replace("__BULLETIN_CONTENT__", content + checking)
