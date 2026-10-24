"""Daily AI Signals: naming helpers for variants, vendors and counting units (see signals.md)."""
from app.core.daily.signals_entities import Entity, tokens, vendor_tokens

# `variant of X` only for a specific earlier entity, never a bare family word (007 noise rule 2).
FAMILY_STOPWORDS = frozenset({"gpt", "claude", "gemini", "llama", "muse", "grok", "qwen", "clef",
                              "nemotron"})


def specific_variant(older: Entity, newer: Entity) -> bool:
    """`variant of` names a specific earlier entity of the same type (007 noise rule 2)."""
    if older.entity_type != newer.entity_type:
        return False
    vendor = set(vendor_tokens(newer.vendor)) | set(tokens(newer.vendor or ""))
    rest = [t for t in tokens(older.display_name) if t not in vendor]
    if not rest or " ".join(rest) in FAMILY_STOPWORDS:
        return False
    return len(rest) > 1 or any(ch.isdigit() for ch in "".join(rest))


def same_vendor(vendor: str | None, org: str) -> bool:
    parts = vendor_tokens(vendor)
    return bool(parts) and parts == vendor_tokens(org)


def unit_key(entity_key: str) -> str:
    """Counting unit: vendor-split automatic entities count together (plan Decision 2)."""
    parts = entity_key.split(":")
    return ":".join(parts[:3]) if parts[0] == "auto" else entity_key


def proper_name(name: str) -> bool:
    """F22: a New item needs a name shape: an uppercase letter or digit, or one hyphen/dot-joined
    token ("agent-engineer"). "dynamic workflows" is a description, not a name."""
    value = name.strip()
    return any(ch.isupper() or ch.isdigit() for ch in value) or \
        (" " not in value and any(ch in value for ch in "-."))
