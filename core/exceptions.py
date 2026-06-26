"""Shared exceptions for the AgenticOS core layer.

Kept in a separate module to avoid circular imports between
core.orchestrator and agents.*.
"""


class SkippedRun(Exception):
    """Raise from any agent action when there is nothing to process.

    The orchestrator catches this, records status='skipped' with the reason in
    the run_history detail field, and exits cleanly — the run is NOT marked
    as failed.

    Example::

        if not notes:
            raise SkippedRun("No raw notes to process")
    """
