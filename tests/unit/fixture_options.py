"""Optional keywords of test data builders, kept out of their signatures (pylint max-args)."""

from typing import Any


def options(given: dict[str, Any], **defaults: Any) -> tuple[Any, ...]:
    """Values of `defaults` in their order, each replaced by `given`; an unknown name fails."""
    unknown = sorted(set(given) - set(defaults))
    if unknown:
        raise TypeError(f"unexpected options: {unknown}")
    return tuple(given.get(name, value) for name, value in defaults.items())
