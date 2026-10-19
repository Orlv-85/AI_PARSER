"""Server-side HTML for the Daily AI Signals block on `/` (plan "UI").

The client re-renders the same structure in digest.html (`renderSignals`) on date change.
"""
import re
from html import escape

from app.web.models import (
    DailySignalEntityItem,
    DailySignalLink,
    DailySignalsResponse,
    DailySignalStory,
    DailySignalTrendItem,
)

UNAVAILABLE = "Daily signals are not available for this date yet."
READ_ERROR = "Daily signals are temporarily unavailable."
_HTTP = re.compile(r"^https?://", re.IGNORECASE)
# Singular forms of the plural event labels (EVENT_LABELS in daily_signals_compute).
SINGULAR = {"model releases": "model release", "product launches": "product launch",
            "funding rounds": "funding round", "acquisitions": "acquisition",
            "partnerships": "partnership", "infrastructure deals": "infrastructure deal",
            "security incidents": "security incident", "people moves": "people move",
            "benchmark results": "benchmark result"}


def event_label(count: int, label: str) -> str:
    """'1 model release', '3 model releases', '1 product launch', '2 analysis'."""
    return f"{count} {SINGULAR.get(label, label) if count == 1 else label}"


def _status(text: str) -> str:
    return f'<p class="signals-status">{escape(text)}</p>'


def _links(links: list[DailySignalLink], quote: str | None = None) -> str:
    items = "".join(
        f'<li><a href="{escape(link.url, quote=True)}" target="_blank" rel="noreferrer">'
        f"{escape(link.title)}</a> <span>{escape(link.publisher)}</span></li>"
        for link in links if _HTTP.match(link.url))
    said = f'<p class="signal-quote">Source says: "{escape(quote)}"</p>' if quote else ""
    if not items and not said:
        return ""
    return (f'<details class="signal-sources"><summary>sources</summary>'
            f'<ul class="signal-links">{items}</ul>{said}</details>')


def _meta(*parts: str | None) -> str:
    return '<p class="signal-meta">' + " &middot; ".join(
        escape(p) for p in parts if p) + "</p>"


def _sources(count: int) -> str:
    return f"{count} source" + ("" if count == 1 else "s")


def _new_item(item: DailySignalEntityItem) -> str:
    badge = ' <span class="signal-badge">early signal</span>' if item.level == "early" else ""
    extra = []
    if item.variant_of:
        extra.append(f'<p class="signal-meta">variant of {escape(item.variant_of)}</p>')
    if item.variants:
        extra.append(f'<p class="signal-meta">also: {escape(", ".join(item.variants))}</p>')
    return (f'<li><strong>{escape(item.name)}</strong>{badge}'
            f"{_meta(item.type, item.vendor, _sources(item.publishers))}{''.join(extra)}"
            f"{_links(item.links, item.novelty_quote)}</li>")


def _story(story: DailySignalStory, labels: dict[str, str]) -> str:
    return (f"<li><strong>{escape(story.label)}</strong>"
            f"{_meta(_sources(story.publishers), labels.get(story.event_type))}"
            f"{_links(story.links)}</li>")


def _n(value: float | None) -> str:
    """A count or rate for display; a missing value renders as "-" (F5)."""
    return "-" if value is None else f"{value:g}"


def _trend(item: DailySignalTrendItem) -> str:
    if item.current_7d is not None:
        counts = (f"7d: {_n(item.previous_7d)} &rarr; {item.current_7d}"
                  f" (expected {_n(item.expected_7d)})")
    else:
        counts = f"today {item.today} vs {_n(item.trailing_mean or 0)}/day"
    badge = ' <span class="signal-badge">spike</span>' if item.spike else ""
    return (f"<li><strong>{escape(item.name)}</strong>{badge}"
            f'<p class="signal-meta">{counts}</p>{_links(item.links)}</li>')


def _card(title: str, body: str, note: str | None, card_id: str, empty: str) -> str:
    note_html = f'<p class="signal-note">{escape(note)}</p>' if note else ""
    if not body and not note:
        note_html = f'<p class="signal-note">{escape(empty)}</p>'
    return (f'<section class="signal-card" id="{card_id}"><h3>{escape(title)}</h3>{note_html}'
            f'<ul class="signal-list">{body}</ul></section>')


def render_signals(signals: DailySignalsResponse | None, *, read_error: bool = False) -> str:
    """Inner HTML of `#daily-signals-body`."""
    if read_error:
        return _status(READ_ERROR)
    if signals is None or signals.status == "unavailable":
        note = signals.notes[0] if signals is not None and signals.notes else UNAVAILABLE
        return _status(note)
    labels = {c.event_type: event_label(1, c.label).split(" ", 1)[1]
              for c in signals.event_counts}
    chips = "".join(f'<li class="signal-chip">{escape(event_label(c.stories, c.label))}</li>'
                    for c in signals.event_counts if c.stories)
    lines = []
    if signals.status == "partial":
        cov = signals.coverage
        lines.append(_status(f"Extracted {cov.extracted}/{cov.items} digest items; "
                             "signals may be incomplete."))
    else:
        lines.extend(_status(n) for n in signals.notes)
    sections = signals.sections
    new_state = sections.get("new")
    top_state = sections.get("top_stories")
    rising_state = sections.get("rising")
    cooling_state = sections.get("cooling")
    cards = [
        _card("New", "".join(_new_item(i) for i in signals.new),
              new_state.note if new_state else None, "signals-new",
              "Nothing was first seen in our corpus on this date."),
        _card("Top stories", "".join(_story(s, labels) for s in signals.top_stories),
              top_state.note if top_state else None, "signals-top",
              "No story was covered by more than one publisher."),
        _card("Spikes" if rising_state and rising_state.state == "spikes_only" else "Rising",
              "".join(_trend(i) for i in signals.rising),
              rising_state.note if rising_state else None, "signals-rising",
              "Nothing is rising or spiking on this date."),
    ]
    cooling = ""
    if cooling_state and cooling_state.state == "ready":
        cooling = (f'<details class="signal-cooling"><summary>Cooling ({len(signals.cooling)})'
                   f'</summary><ul class="signal-list">'
                   f"{''.join(_trend(i) for i in signals.cooling)}</ul></details>")
    return (f'<ul class="signal-chips">{chips}</ul>{"".join(lines)}'
            f'<div class="signal-grid">{"".join(cards)}</div>{cooling}')
