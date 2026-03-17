"""
Abstract base class for notification senders.

A Notifier takes a NotificationContext (filtered results + files) and a
NotificationConfig (recipients, subject, template path) and delivers the
notification.  The orchestrator calls .notify() without knowing whether
it's email, Slack, or anything else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from report_runner.config.models import NotificationConfig
from report_runner.models import NotificationContext


class Notifier(ABC):
    """Delivers a notification for a single notification block."""

    @abstractmethod
    def notify(
        self,
        context: NotificationContext,
        notification_config: NotificationConfig,
    ) -> None:
        """
        Send the notification.

        Must not raise on failure — log the error and return instead,
        so subsequent notification blocks are still attempted.
        """
        ...
