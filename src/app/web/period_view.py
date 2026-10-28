"""Server HTML for one stored week on `/weekly` (017 R3).

Reads nothing itself: the route passes the stored row (as the API reads it). Behavior of the
page states: `src/app/core/periodic/signals_period.md`; page and assets: `src/app/web/pages.md`.
"""
import re
from collections.abc import Sequence
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.web.models import DailySignalTrendItem, PeriodSignalsResponse
from app.web.signals_view import AI_NOTE, _trend, event_label

_TEMPLATE = Path(__file__).resolve().parent / "period.html"
_PLACEHOLDER = re.compile(r"__[A-Z_]+__")
_HTTP = re.compile(r"^https?://", re.IGNORECASE)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

NOT_YET = "Weekly signals are not available yet."
NOT_FOR_WEEK = "Weekly signals are not available for this week."
UNREADABLE = "Weekly signals for this week could not be read."
FIRST_WEEK = "First week, no comparison with a previous week."
LOW_COVERAGE = ("Comparison with the previous week is hidden: too few publishers were covered "
                "(low publisher coverage).")
PARTIAL = "Partial week: some days or items are missing, so numbers may be incomplete."


def _short(day: date) -> str:
    return f"{_MONTHS[day.month - 1]} {day.day}"


def week_label(start: date, end: date) -> str:
    """'Oct 19-25' within a month, 'Oct 26 - Nov 1' across months."""
    if start.month == end.month:
        return f"{_short(start)}-{end.day}"
    return f"{_short(start)} - {_short(end)}"


def _t(value: Any) -> str:
    return "" if value is None else escape(str(value))


def _i(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _status(text: str) -> str:
    return f'<p class="signals-status">{escape(text)}</p>'


def _meta(parts: Sequence[str | None]) -> str:
    """`parts` are already HTML-escaped."""
    return '<p class="signal-meta">' + " &middot; ".join(p for p in parts if p) + "</p>"


def _outlets(count: int) -> str:
    return f"{count} outlet" + ("" if count == 1 else "s")


def _day(value: Any) -> str:
    """A day as a link to the daily page; anything that is not a date stays escaped text."""
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        return _t(value)
    return f'<a href="/?date={day.isoformat()}">{_short(day)}</a>'


def _days(values: Any, prefix: str = "days") -> str | None:
    days = [_day(v) for v in _list(values)]
    return f"{prefix}: {', '.join(days)}" if days else None


def _links(links: Any) -> str:
    items = []
    for link in _list(links):
        link = _dict(link)
        url = str(link.get("url") or "")
        if not _HTTP.match(url):
            continue
        title = link.get("title") or url
        items.append(f'<li><a href="{escape(url, quote=True)}" target="_blank" rel="noreferrer">'
                     f'{_t(title)}</a> <span>{_t(link.get("publisher"))}</span></li>')
    if not items:
        return ""
    return ('<details class="signal-sources"><summary>sources</summary>'
            f'<ul class="signal-links">{"".join(items)}</ul></details>')


def _card(title: str, card_id: str, body: str, note: str | None = None, empty: str = "") -> str:
    """A section: items, or one plain reason line (never an empty list)."""
    lines = f'<p class="signal-note">{escape(note)}</p>' if note else ""
    if not body and not note:
        lines = f'<p class="signal-note">{escape(empty)}</p>'
    items = f'<ul class="signal-list">{body}</ul>' if body else ""
    return (f'<section class="signal-card" id="{card_id}"><h3>{escape(title)}</h3>'
            f"{lines}{items}</section>")


def _story(story: dict[str, Any], labels: dict[str, str]) -> str:
    event = _t(labels.get(str(story.get("event_type"))))
    meta = _meta([_outlets(_i(story.get("publishers"))), event, _days(story.get("days"))])
    return (f"<li><strong>{_t(story.get('label'))}</strong>{meta}"
            f"{_links(story.get('links'))}</li>")


def _entity(item: dict[str, Any]) -> str:
    articles = _i(item.get("articles"))
    meta = _meta([_t(item.get("vendor")) or None,
                  f"{articles} article" + ("" if articles == 1 else "s"),
                  _outlets(_i(item.get("publishers"))), _days(item.get("days"))])
    return f"<li><strong>{_t(item.get('name'))}</strong>{meta}{_links(item.get('links'))}</li>"


def _new(item: dict[str, Any]) -> str:
    confirmed = item.get("level") == "confirmed"
    links = _list(item.get("links"))
    first = _dict(links[0]) if links else {}
    source = _outlets(_i(item.get("publishers"))) if confirmed or not first else \
        f"via {_t(first.get('publisher'))}"
    seen = f"first seen {_day(item['first_seen_day'])}" if item.get("first_seen_day") else None
    what = f'<p class="signal-what">{_t(item["one_liner"])}</p>' if item.get("one_liner") else ""
    css = "signal-confirmed" if confirmed else "signal-muted"
    return (f'<li class="{css}"><strong>{_t(item.get("name"))}</strong>'
            f"{_meta([_t(item.get('type')) or None, _t(item.get('vendor')) or None, source, seen])}"
            f"{what}{_links(links)}</li>")


def _trend_html(item: Any) -> str:
    try:
        return str(_trend(DailySignalTrendItem.model_validate(item)))
    except ValidationError:
        return f"<li><strong>{_t(_dict(item).get('name'))}</strong></li>"


def _why_hidden(comparison: dict[str, Any]) -> str:
    return LOW_COVERAGE if comparison.get("state") == "suppressed" else FIRST_WEEK


def _coverage(signals: PeriodSignalsResponse) -> str:
    cov = signals.coverage
    share = cov.get("extracted_share")
    parts = [f"{_i(cov.get('complete_days'))} of {_i(cov.get('days'))} days complete",
             f"{_i(cov.get('items'))} items", f"{_i(cov.get('publishers'))} publishers"]
    if isinstance(share, int | float):
        parts.append(f"{round(share * 100)}% extracted")
    lines = [_status(", ".join(parts))]
    missing = [_day(d) for d in _list(cov.get("missing_days"))]
    if missing:
        lines.append(f'<p class="signals-status">No data for: {", ".join(missing)}</p>')
    if signals.status == "partial":
        lines.append(_status(PARTIAL))
    if signals.quiet:
        lines.append(f'<p class="signal-quiet">Quiet week: only {_i(cov.get("items"))} items. '
                     "Sections show what there is.</p>")
    comparison = signals.comparison
    if comparison.get("state") in ("none", "suppressed"):
        lines.append(_status(_why_hidden(comparison)))
    return "".join(lines)


def _entities(signals: PeriodSignalsResponse) -> str:
    cards = []
    for group, items in signals.top_entities.items():
        if items:
            cards.append(_card(group.capitalize(), f"period-entities-{re.sub('[^a-z]', '', group)}",
                               "".join(_entity(_dict(i)) for i in items)))
    if not cards:
        return _card("Top entities", "period-entities", "",
                     empty="No entity was covered by enough articles and publishers.")
    return f'<div class="signal-grid cols-2" id="period-entities">{"".join(cards)}</div>'


def _event_mix(signals: PeriodSignalsResponse) -> str:
    mix = signals.event_mix
    rows = []
    for row in _list(mix.get("types")):
        row = _dict(row)
        delta = row.get("delta")
        change = ""
        if isinstance(delta, int):
            change = " (no change)" if delta == 0 else f" ({delta:+d} vs previous week)"
        name = _t(event_label(_i(row.get("stories")), str(row.get("label"))))
        arts = f"{_i(row.get('articles'))} articles{change}"
        rows.append(f"<li><strong>{name}</strong>{_meta([escape(arts)])}</li>")
    more = _dict(mix.get("more"))
    if _i(more.get("stories")):
        rows.append(f"<li>+{_i(more.get('stories'))} stories in {_i(more.get('types'))} "
                    "other types</li>")
    note = None
    if rows and signals.comparison.get("state") != "ready":
        note = _why_hidden(signals.comparison)
    return _card("Event types", "period-events", "".join(rows), note,
                 "No hard event type was covered this week.")


def _risers(signals: PeriodSignalsResponse) -> str:
    state = signals.sections.get("rising")
    if state == "ready":
        rising = "".join(_trend_html(i) for i in signals.rising)
        cooling = "".join(_trend_html(i) for i in signals.cooling)
        return ('<div class="signal-grid cols-2" id="period-trends">'
                + _card("Rising", "period-rising", rising, None, "Nothing is rising this week.")
                + _card("Cooling", "period-cooling", cooling, None,
                        "Nothing is cooling this week.") + "</div>")
    note = _why_hidden(signals.comparison) if state == "hidden" else \
        "Rising and Cooling are not available for this week."
    return _card("Rising and Cooling", "period-trends", "", note)


def _brief(signals: PeriodSignalsResponse) -> str:
    """"In brief": the stored sentences with numbered http(s) source links and the AI note."""
    items = []
    for sentence in signals.brief.sentences if signals.brief else []:
        refs = "".join(
            f' <a class="signal-ref" href="{escape(link.url, quote=True)}" '
            f'title="{escape(link.title, quote=True)}" target="_blank" rel="noreferrer">'
            f"[{n}]</a>"
            for n, link in enumerate((x for x in sentence.links if _HTTP.match(x.url)), start=1))
        items.append(f"<li>{escape(sentence.text)}{refs}</li>")
    if not items:
        return ""
    return ('<div class="signal-brief-block"><h3>In brief</h3>'
            f'<ul class="signal-brief">{"".join(items)}</ul>'
            f'<p class="signal-ai-note">{escape(AI_NOTE)}</p></div>')


def render_week(signals: PeriodSignalsResponse) -> str:
    """Inner HTML of the week: the brief, the coverage line and the sections in plan order."""
    types = [_dict(t) for t in _list(signals.event_mix.get("types"))]
    labels = {str(t.get("event_type")): event_label(1, str(t.get("label"))).split(" ", 1)[1]
              for t in types}
    stories = _card("Top stories", "period-stories",
                    "".join(_story(_dict(s), labels) for s in signals.top_stories),
                    None, "No story was covered by more than one publisher.")
    new = _card("New this week", "period-new", "".join(_new(_dict(i)) for i in signals.new),
                None, "Nothing was first seen in our corpus this week.")
    return (f'<div class="period-stack">{_brief(signals)}{_coverage(signals)}{stories}'
            f"{_entities(signals)}{new}{_risers(signals)}{_event_mix(signals)}</div>")


def render_picker(weeks: Sequence[tuple[date, date, str]], current: date | None) -> str:
    """Plain links between stored weeks (`weeks` newest first): previous, next and the list."""
    if not weeks:
        return ""
    starts = [w[0] for w in weeks]
    nav = []
    if current in starts:
        at = starts.index(current)
        if at + 1 < len(weeks):
            older = weeks[at + 1]
            nav.append(f'<a rel="prev" href="/weekly?week={older[0].isoformat()}">'
                       f"&larr; {week_label(older[0], older[1])}</a>")
        if at > 0:
            newer = weeks[at - 1]
            nav.append(f'<a rel="next" href="/weekly?week={newer[0].isoformat()}">'
                       f"{week_label(newer[0], newer[1])} &rarr;</a>")
    items = []
    for start, end, status in weeks:
        name = week_label(start, end) + (" (partial)" if status == "partial" else "")
        if start == current:
            items.append(f'<li aria-current="page"><strong>{name}</strong></li>')
        else:
            items.append(f'<li><a href="/weekly?week={start.isoformat()}">{name}</a></li>')
    return (f'<nav class="period-picker" aria-label="Weeks"><p class="period-prevnext">'
            f'{" ".join(nav)}</p><ul class="period-weeks">{"".join(items)}</ul></nav>')


def render_content(signals: PeriodSignalsResponse | None, *, note: str = NOT_FOR_WEEK) -> str:
    """The week, or one plain reason line. Never raises on stored data of an odd shape."""
    heading = ""
    if signals is not None and signals.period_start and signals.period_end:
        heading = (f'<h2 class="period-heading">Week of '
                   f'{week_label(signals.period_start, signals.period_end)}, '
                   f'{signals.period_start.year}</h2>')
    if signals is None or signals.status == "unavailable":
        text = signals.notes[0] if signals is not None and signals.notes else note
        return f"{heading}{_status(text)}"
    try:
        return heading + render_week(signals)
    except (TypeError, ValueError, KeyError, AttributeError, IndexError):
        return f"{heading}{_status(UNREADABLE)}"


def render_page(content: str, picker: str) -> str:
    values = {"__PERIOD_CONTENT__": content, "__PERIOD_PICKER__": picker}
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(0), m.group(0)),
                            _TEMPLATE.read_text(encoding="utf-8"))


def nav_link() -> str:
    return '<a class="hero-link" href="/weekly">Weekly</a>'


def home_line(start: date, end: date) -> str:
    return (f'<p class="period-line"><a href="/weekly">Week of {week_label(start, end)}: '
            "weekly signals</a></p>")
