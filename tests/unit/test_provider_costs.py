import pytest

from app.core.provider_costs import PRICES, is_overload, microdollars


def test_prices_are_pinned():
    # Prices decide paid budgets and frozen weekly identities.
    assert PRICES == {"jev": {"input": 0.042, "output": 0},
                      "deepseek": {"input": 0.30, "output": 1.20}}


def test_microdollars_accepts_exact_caps_only():
    assert microdollars("0.30") == 300000
    assert microdollars(2) == 2000000
    assert microdollars("0.000001") == 1
    for bad in ("0", "-1", "0.0000001", "nan", "inf"):
        with pytest.raises(ValueError):
            microdollars(bad)


def test_is_overload_requires_error_only_body():
    assert is_overload(429, {"error": "busy"})
    assert not is_overload(429, {"error": "busy", "usage": {}})
    assert not is_overload(400, {"error": "bad"})
    assert not is_overload(503, None)
