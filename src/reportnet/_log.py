"""Logging setup for the library.

The library logs to the ``reportnet`` logger hierarchy and attaches a
:class:`~logging.NullHandler`, so it stays silent unless the application opts
in. To see what it is doing::

    import logging
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("reportnet").setLevel(logging.DEBUG)

Levels used:

* ``DEBUG`` — every HTTP request, every job poll. Verbose by design.
* ``INFO``  — job status transitions, multi-step orchestration progress.
* ``WARNING`` — retries, and any silent-degradation fallback (an unresolved
  codelist, a guessed reference dataset). Anything that makes the result
  *weaker than requested* must be at least a warning.

API keys are never logged: they live in a header that is not included in any
log record.
"""

from __future__ import annotations

import logging

logging.getLogger("reportnet").addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """Return the module logger for *name* (pass ``__name__``)."""
    return logging.getLogger(name)
