"""Stop errors of the provider payment journal (src/app/storage/provider_journal.md).

They live in core so provider clients in core can catch them without importing storage.
"""


class PilotStopped(RuntimeError):
    """No further paid requests may be dispatched."""


class TransportAttemptsExhausted(ValueError):
    """Every reviewed transport attempt failed; `dispatched` tells if this call sent one."""

    def __init__(self, message, dispatched=False):
        super().__init__(message)
        self.dispatched = dispatched
