"""Notification channels.

Each channel fails softly: a broken Telegram token or an offline SMTP server
logs a warning but never crashes the monitor, so one misconfigured channel can't
silence the others or stop capturing.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from .config import NotifierConfig

log = logging.getLogger("trustwatch.notifier")


def _scrub(text: str, *secrets: str) -> str:
    """Replace any non-empty secret substrings in `text` with a placeholder.

    Telegram embeds the bot token in the request URL and a webhook URL may hold
    a secret path, so the URL inside a requests exception would otherwise land
    the credential in the logs.
    """
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text


class Notifier:
    def __init__(self, cfg: NotifierConfig):
        self.cfg = cfg

    def notify(self, title: str, body: str, image_path: Optional[Path] = None) -> None:
        """Fan the alert out to every configured channel."""
        if self.cfg.desktop:
            self._safe(self._desktop, title, body)
        if self.cfg.telegram_token and self.cfg.telegram_chat_id:
            self._safe(self._telegram, title, body, image_path)
        if self.cfg.email_enabled:
            self._safe(self._email, title, body, image_path)
        if self.cfg.webhook_url:
            self._safe(self._webhook, title, body, image_path)

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _safe(fn, *args) -> None:
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001 - channels must not crash monitor
            log.warning("Notification channel %s failed: %s", fn.__name__, exc)

    def _desktop(self, title: str, body: str) -> None:
        try:
            from plyer import notification  # type: ignore

            notification.notify(title=title, message=body, app_name="TrustWatch")
            return
        except Exception:
            pass
        # Fall back to platform-native tools if plyer is unavailable.
        import platform
        import shutil
        import subprocess

        system = platform.system()
        if system == "Darwin":
            script = f'display notification {body!r} with title {title!r}'
            subprocess.run(["osascript", "-e", script], check=False)
        elif system == "Linux" and shutil.which("notify-send"):
            subprocess.run(["notify-send", title, body], check=False)
        # Windows without plyer: silently skip (log already covers failures).

    def _telegram(self, title: str, body: str, image_path: Optional[Path]) -> None:
        import requests  # type: ignore

        token = self.cfg.telegram_token
        chat_id = self.cfg.telegram_chat_id
        caption = f"{title}\n{body}"

        try:
            if image_path and Path(image_path).exists():
                url = f"https://api.telegram.org/bot{token}/sendPhoto"
                with open(image_path, "rb") as fh:
                    resp = requests.post(
                        url,
                        data={"chat_id": chat_id, "caption": caption},
                        files={"photo": fh},
                        timeout=20,
                    )
            else:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                resp = requests.post(
                    url, data={"chat_id": chat_id, "text": caption}, timeout=20
                )
            resp.raise_for_status()
        except Exception as exc:
            # The token lives in the URL, which requests puts in the error text.
            raise RuntimeError(_scrub(str(exc), token)) from None

    def _email(self, title: str, body: str, image_path: Optional[Path]) -> None:
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = self.cfg.smtp_user
        msg["To"] = self.cfg.email_to
        msg.set_content(body)

        if image_path and Path(image_path).exists():
            data = Path(image_path).read_bytes()
            msg.add_attachment(
                data, maintype="image", subtype="jpeg", filename=Path(image_path).name
            )

        context = ssl.create_default_context()
        with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port, timeout=20) as server:
            server.starttls(context=context)
            if self.cfg.smtp_user:
                server.login(self.cfg.smtp_user, self.cfg.smtp_password)
            server.send_message(msg)

    def _webhook(self, title: str, body: str, image_path: Optional[Path]) -> None:
        import requests  # type: ignore

        payload = {"title": title, "body": body, "text": f"{title}: {body}"}
        try:
            if image_path and Path(image_path).exists():
                with open(image_path, "rb") as fh:
                    resp = requests.post(
                        self.cfg.webhook_url,
                        data=payload,
                        files={"image": (Path(image_path).name, fh, "image/jpeg")},
                        timeout=20,
                    )
            else:
                resp = requests.post(self.cfg.webhook_url, json=payload, timeout=20)
            resp.raise_for_status()
        except Exception as exc:
            # A webhook URL can carry a secret path/token; keep it out of logs.
            raise RuntimeError(_scrub(str(exc), self.cfg.webhook_url)) from None
