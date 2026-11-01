"""Plain-text (Telegram style) rendering of a bulletin (spec 018, item 2).

Layout of specs/018-daily-inference/voice.md; behavior in src/app/core/bulletin/builder.md.
"""
from textwrap import fill
from typing import Any

from app.core.bulletin.builder import Bulletin, Story

TEXT_WIDTH = 60
OUTLETS_SHOWN = 3


def _outlets(story: Story) -> str:
    shown = story.outlets[:OUTLETS_SHOWN]
    extra = len(story.outlets) - len(shown)
    return ", ".join(shown) + (f" +{extra}" if extra else "")


def _bullet(story: Story, *, area: bool = False) -> str:
    text = f"{story.area}: " if area else ""
    text += f"{story.title} ({_outlets(story)})"
    if story.reaction:
        text += f". {story.reaction}"
    return fill(text, TEXT_WIDTH, initial_indent="• ", subsequent_indent="  ")


def _paragraph(text: str) -> str:
    return fill(text, TEXT_WIDTH)


def render_text(bulletin: Bulletin, lib: dict[str, Any]) -> str:
    """The bulletin as plain text; empty sections are left out."""
    labels = lib["labels"]
    blocks = [f"{bulletin.masthead}\n{bulletin.byline}"]
    if bulletin.headline:
        blocks.append(_paragraph(bulletin.headline))
    blocks.append(_paragraph(f"{bulletin.opening} {bulletin.numbers}"))
    if bulletin.key_results:
        blocks.append("\n".join([labels["key_results"]]
                                + [_bullet(s, area=True) for s in bulletin.key_results]))
    if bulletin.rubric_story and bulletin.rubric_name:
        blocks.append(f"{bulletin.rubric_name}\n{_bullet(bulletin.rubric_story)}")
    if bulletin.cooperation:
        blocks.append("\n".join([labels["cooperation"]]
                                + [_bullet(s) for s in bulletin.cooperation]))
    if bulletin.incidents:
        line = f"{labels['incidents']}: {bulletin.incidents}."
        if bulletin.incident_story:
            story = bulletin.incident_story
            line += f" {labels['among']}: {story.title} ({_outlets(story)})."
        blocks.append(_paragraph(line))
    blocks.append(f"{bulletin.closing}\n{labels['full_report']} ({bulletin.items}) →")
    if bulletin.headline_cut:
        blocks[-1] += f"\n{lib['cut']['footnote']}"
    return "\n\n".join(blocks) + "\n"
