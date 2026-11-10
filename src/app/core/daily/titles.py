"""Digest title: the article title without aggregator decorations."""
import re

# Aggregator decorations only; meaningful parentheticals such as "(Sponsor)" stay.
TITLE_JUNK = re.compile(
    r"\s*\((?:\d+ min(?:ute)? read|GitHub Repo|"
    r"Hugging Face (?:Repo|Model|Space|Dataset|Paper))\)\s*$", re.IGNORECASE)


def digest_title(title):
    cleaned = title
    while (stripped := TITLE_JUNK.sub("", cleaned)) != cleaned:
        cleaned = stripped
    return cleaned.strip() or title
