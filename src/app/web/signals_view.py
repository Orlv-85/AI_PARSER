"""Server-side HTML for the Daily AI Signals block on `/` (plan "UI").

The client re-renders the same structure in digest.html (`renderSignals`) on date change.
"""
import re
from html import escape

from app.core.daily_signals_brief import HARD_EVENTS
from app.web.models import (
    DailySignalBrief,
    DailySignalEntityItem,
    DailySignalLink,
    DailySignalsResponse,
    DailySignalStory,
    DailySignalTrendItem,
)

UNAVAILABLE = "Daily signals are not available for this date yet."
READ_ERROR = "Daily signals are temporarily unavailable."
AI_NOTE = "Written by AI from the linked articles; check the sources."
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


def _outlets(count: int) -> str:
    return f"{count} outlet" + ("" if count == 1 else "s")


def _new_item(item: DailySignalEntityItem) -> str:
    """D3: confirmed items with "N outlets"; single-source items muted, "via <publisher>"."""
    confirmed = item.level == "confirmed"
    source = _outlets(item.publishers) if confirmed or not item.links else \
        f"via {item.links[0].publisher}"
    extra = []
    if item.one_liner:
        line = item.one_liner if item.one_liner_source != "quote" else f'"{item.one_liner}"'
        extra.append(f'<p class="signal-what">{escape(line)}</p>')
    if item.variant_of:
        extra.append(f'<p class="signal-meta">variant of {escape(item.variant_of)}</p>')
    if item.variants:
        extra.append(f'<p class="signal-meta">also: {escape(", ".join(item.variants))}</p>')
    # The quote is shown once: as the line itself when the line came from it.
    quote = None if item.one_liner_source == "quote" else item.novelty_quote
    css = "signal-confirmed" if confirmed else "signal-muted"
    return (f'<li class="{css}"><strong>{escape(item.name)}</strong>'
            f"{_meta(item.type, item.vendor, source)}{''.join(extra)}"
            f"{_links(item.links, quote)}</li>")


def _story(story: DailySignalStory, labels: dict[str, str]) -> str:
    spikes = f"spike: {', '.join(story.spikes)}" if story.spikes else None
    return (f"<li><strong>{escape(story.label)}</strong>"
            f"{_meta(_outlets(story.publishers), labels.get(story.event_type), spikes)}"
            f"{_links(story.links)}</li>")


def _n(value: float | None) -> str:
    """A count or rate for display; a missing value renders as "-" (F5)."""
    return "-" if value is None else f"{value:g}"


def _trend(item: DailySignalTrendItem) -> str:
    if item.current_7d is not None:
        counts = (f"7d: {_n(item.previous_7d)} &rarr; {item.current_7d}"
                  f" (expected {_n(item.expected_7d)})")
    elif item.trailing_mean:
        counts = f"today {item.today} vs {_n(item.trailing_mean)}/day"
    else:
        counts = f"today {item.today} vs none before"
    if item.reason:
        counts += f" - {escape(item.reason)}"
    badge = ' <span class="signal-badge">spike</span>' if item.spike else ""
    return (f"<li><strong>{escape(item.name)}</strong>{badge}"
            f'<p class="signal-meta">{counts}</p>{_links(item.links)}</li>')


def _card(title: str, body: str, note: str | None, card_id: str, empty: str) -> str:
    note_html = f'<p class="signal-note">{escape(note)}</p>' if note else ""
    if not body and not note:
        note_html = f'<p class="signal-note">{escape(empty)}</p>'
    return (f'<section class="signal-card" id="{card_id}"><h3>{escape(title)}</h3>{note_html}'
            f'<ul class="signal-list">{body}</ul></section>')


def quiet_line(signals: DailySignalsResponse) -> str:
    """FR-006 template opening line (app text, not model output)."""
    multi = len(signals.top_stories)
    stories = "no story" if not multi else f"{multi} " + ("story" if multi == 1 else "stories")
    return (f"Quiet day: {signals.coverage.items} items, {stories} covered by more than one "
            "outlet.")


def _brief(signals: DailySignalsResponse) -> str:
    """"In brief": the quiet-day line, the generated sentences with [n] links, the AI note."""
    brief: DailySignalBrief | None = signals.brief
    quiet = f'<p class="signal-quiet">{escape(quiet_line(signals))}</p>' if signals.quiet else ""
    items = []
    for sentence in brief.sentences if brief else []:
        refs = "".join(
            f' <a class="signal-ref" href="{escape(link.url, quote=True)}" '
            f'title="{escape(link.title, quote=True)}" target="_blank" rel="noreferrer">'
            f"[{n}]</a>"
            for n, link in enumerate((x for x in sentence.links if _HTTP.match(x.url)), start=1))
        items.append(f"<li>{escape(sentence.text)}{refs}</li>")
    if not quiet and not items:
        return ""
    sentences = f'<ul class="signal-brief">{"".join(items)}</ul>' if items else ""
    note = f'<p class="signal-ai-note">{escape(AI_NOTE)}</p>' if items else ""
    return (f'<div class="signal-brief-block"><h3>In brief</h3>{quiet}{sentences}{note}'
            "</div>")


def _chips(signals: DailySignalsResponse) -> str:
    """Hard event types as chips; the rest folded into "+N more" (display only, OD4)."""
    hard = [c for c in signals.event_counts if c.stories and c.event_type in HARD_EVENTS]
    soft = [c for c in signals.event_counts if c.stories and c.event_type not in HARD_EVENTS]
    chips = "".join(f'<li class="signal-chip">{escape(event_label(c.stories, c.label))}</li>'
                    for c in hard)
    if soft:
        title = ", ".join(event_label(c.stories, c.label) for c in soft)
        chips += (f'<li class="signal-chip signal-chip-more" title="{escape(title, quote=True)}">'
                  f"+{sum(c.stories for c in soft)} more</li>")
    return f'<ul class="signal-chips">{chips}</ul>'


def render_signals(signals: DailySignalsResponse | None, *, read_error: bool = False) -> str:
    """Inner HTML of `#daily-signals-body`."""
    if read_error:
        return _status(READ_ERROR)
    if signals is None or signals.status == "unavailable":
        note = signals.notes[0] if signals is not None and signals.notes else UNAVAILABLE
        return _status(note)
    labels = {c.event_type: event_label(1, c.label).split(" ", 1)[1]
              for c in signals.event_counts}
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
    spikes_only = rising_state is not None and rising_state.state == "spikes_only"
    # A quiet day shows only cards that have items (no empty-state cards, FR-006).
    hide_spikes = not signals.rising and (signals.quiet or spikes_only)
    # The Rising/Spikes note moves to the status line when the card is hidden (not on quiet days).
    if hide_spikes and not signals.quiet and rising_state is not None and rising_state.note:
        lines.append(_status(rising_state.note))
    cards = []
    if signals.new or not signals.quiet:
        cards.append(_card("New", "".join(_new_item(i) for i in signals.new),
                           new_state.note if new_state else None, "signals-new",
                           "Nothing was first seen in our corpus on this date."))
    if signals.top_stories or not signals.quiet:
        cards.append(_card("Top stories", "".join(_story(s, labels) for s in signals.top_stories),
                           top_state.note if top_state else None, "signals-top",
                           "No story was covered by more than one publisher."))
    if not hide_spikes:
        note = rising_state.note if rising_state and not signals.quiet else None
        cards.append(_card("Spikes" if spikes_only else "Rising",
                           "".join(_trend(i) for i in signals.rising), note, "signals-rising",
                           "Nothing is rising or spiking on this date."))
    cooling = ""
    if cooling_state and cooling_state.state == "ready":
        cooling = (f'<details class="signal-cooling"><summary>Cooling ({len(signals.cooling)})'
                   f'</summary><ul class="signal-list">'
                   f"{''.join(_trend(i) for i in signals.cooling)}</ul></details>")
    grid = f'<div class="signal-grid cols-{len(cards)}">{"".join(cards)}</div>' if cards else ""
    return f'{_brief(signals)}{_chips(signals)}{"".join(lines)}{grid}{cooling}'
