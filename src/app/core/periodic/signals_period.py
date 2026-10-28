"""Period AI Signals: weekly and monthly sums and comparisons of the daily signals.

Feature doc: signals_period.md. This module is the public entry; the rules live in
period_model.py (bounds, thresholds, input records, status) and period_compute.py (pure compute).
"""
from app.core.periodic.period_compute import (
           PERIOD_METHODOLOGY_VERSION,
           compute_period,
           payload_hash,
)
from app.core.periodic.period_model import PeriodInput, PeriodThresholds

__all__ = ["PERIOD_METHODOLOGY_VERSION", "PeriodInput", "PeriodThresholds", "compute_period",
           "payload_hash"]
