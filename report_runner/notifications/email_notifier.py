"""
EmailNotifier — sends one email per notification block.

Responsibilities:
  - Render the Jinja2 HTML body template.
  - Compose a MIME email with the rendered body and .xlsx attachments.
  - Send via SMTP with STARTTLS.
  - Never raise — log the error and return so remaining blocks are attempted.

SMTP credentials are resolved from environment variables:
  SMTP_{ALIAS_UPPER}_HOST
  SMTP_{ALIAS_UPPER}_PORT
  SMTP_{ALIAS_UPPER}_USER
  SMTP_{ALIAS_UPPER}_PASSWORD
  SMTP_{ALIAS_UPPER}_USE_TLS   (true/false, default: true)
"""

from __future__ import annotations

import os
import smtplib
from datetime import date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from loguru import logger

from report_runner.config.models import ConfigurationError, EmailNotificationConfig
from report_runner.models import NotificationContext
from report_runner.notifications.base import Notifier


class EmailNotifier(Notifier):
    """Sends HTML emails with .xlsx attachments via SMTP."""

    def notify(
        self,
        context: NotificationContext,
        notification_config: EmailNotificationConfig,  # type: ignore[override]
    ) -> None:
        try:
            self._send(context, notification_config)
        except Exception as exc:
            # Email failure must never crash the application.
            logger.exception(
                "Email notification failed for recipients {}: {}",
                notification_config.to,
                exc,
            )

    # ── Private implementation ────────────────────────────────────────────────

    def _send(
        self,
        context: NotificationContext,
        cfg: EmailNotificationConfig,
    ) -> None:
        smtp_cfg = _SmtpConfig.from_alias(cfg.smtp_alias)
        subject = cfg.subject.replace("{date}", context.run_date.strftime("%Y-%m-%d"))

        body_html = self._render_body(cfg.body_template, context)
        message = self._build_message(cfg, subject, body_html, context)

        with smtplib.SMTP(smtp_cfg.host, smtp_cfg.port) as server:
            if smtp_cfg.use_tls:
                server.starttls()
            if smtp_cfg.user and smtp_cfg.password:
                server.login(smtp_cfg.user, smtp_cfg.password)

            all_recipients = cfg.to + cfg.cc + cfg.bcc
            server.sendmail(smtp_cfg.user or "", all_recipients, message.as_string())

        logger.info(
            "Email sent to {} (cc: {}) for workflow '{}' with {} attachment(s).",
            cfg.to,
            cfg.cc,
            context.workflow_name,
            len(context.attached_files),
        )

    @staticmethod
    def _render_body(template_path: str, context: NotificationContext) -> str:
        """Render the Jinja2 HTML template with the notification context."""
        path = Path(template_path)
        env = Environment(
            loader=FileSystemLoader(str(path.parent)),
            autoescape=True,
        )
        try:
            template = env.get_template(path.name)
        except TemplateNotFound:
            raise FileNotFoundError(
                f"Email body template not found: '{template_path}'"
            )

        return template.render(
            workflow_name=context.workflow_name,
            run_date=context.run_date.strftime("%Y-%m-%d"),
            run_started_at=context.run_started_at.strftime("%Y-%m-%d %H:%M:%S"),
            results=context.results,
            attached_files=context.attached_files,
        )

    @staticmethod
    def _build_message(
        cfg: EmailNotificationConfig,
        subject: str,
        body_html: str,
        context: NotificationContext,
    ) -> MIMEMultipart:
        """Assemble the MIME message with body and attachments."""
        message = MIMEMultipart("mixed")
        message["Subject"] = subject
        message["From"] = os.environ.get(
            f"SMTP_{cfg.smtp_alias.upper().replace('-', '_')}_USER", ""
        )
        message["To"] = ", ".join(cfg.to)
        if cfg.cc:
            message["Cc"] = ", ".join(cfg.cc)

        # Attach the HTML body.
        message.attach(MIMEText(body_html, "html", "utf-8"))

        # Attach each .xlsx file.
        for exported_file in context.attached_files:
            file_path = exported_file.path
            if not file_path.exists():
                logger.warning(
                    "Attachment file not found, skipping: {}", file_path
                )
                continue

            attachment = MIMEBase("application", "octet-stream")
            attachment.set_payload(file_path.read_bytes())
            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=file_path.name,
            )
            message.attach(attachment)

        return message


class _SmtpConfig:
    """SMTP connection parameters resolved from environment variables."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        use_tls: bool,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls

    @classmethod
    def from_alias(cls, alias: str) -> _SmtpConfig:
        prefix = f"SMTP_{alias.upper().replace('-', '_')}"

        host = os.environ.get(f"{prefix}_HOST")
        if not host:
            raise ConfigurationError(
                f"Missing environment variable '{prefix}_HOST' for SMTP alias '{alias}'."
            )

        port_str = os.environ.get(f"{prefix}_PORT", "587")
        try:
            port = int(port_str)
        except ValueError:
            raise ConfigurationError(
                f"Invalid value for '{prefix}_PORT': '{port_str}' is not an integer."
            )

        user = os.environ.get(f"{prefix}_USER", "")
        password = os.environ.get(f"{prefix}_PASSWORD", "")
        use_tls_str = os.environ.get(f"{prefix}_USE_TLS", "true").lower()
        use_tls = use_tls_str not in ("false", "0", "no")

        return cls(host=host, port=port, user=user, password=password, use_tls=use_tls)
