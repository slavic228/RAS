"""
Abstract base class for precondition checkers.

A PreconditionChecker evaluates a single precondition and returns True if
it passed, or exits the process if the deadline was exceeded.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from report_runner.config.models import PreconditionConfig


class PreconditionChecker(ABC):
    """Evaluates a single precondition, blocking until it passes or the deadline is reached."""

    @abstractmethod
    def check(self, config: PreconditionConfig) -> bool:
        """
        Block until the precondition passes or the deadline is exceeded.

        Returns True if the precondition passed.
        Calls sys.exit(1) if the deadline is exceeded.
        """
        ...
