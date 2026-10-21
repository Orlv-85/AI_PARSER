"""Paid provider prices, dollar caps in microdollars and unbilled overload answers."""
from decimal import Decimal

PRICES = {"jev": {"input": 0.042, "output": 0},
          "deepseek": {"input": 0.30, "output": 1.20}}

# Overload/rate-limit answers without usage are not billed; retry them in place.
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def microdollars(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or amount <= 0 or amount * 1000000 != int(amount * 1000000):
        raise ValueError("Invalid dollar cap")
    return int(amount * 1000000)


def is_overload(status_code, data):
    """An explicit error-only overload answer; anything else keeps unknown billing."""
    return status_code in TRANSIENT_STATUS and isinstance(data, dict) and set(data) == {"error"}
