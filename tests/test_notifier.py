"""Tests for trustwatch.notifier.

No network is touched: we monkeypatch the private per-channel methods so we can
observe the fan-out and the fault isolation provided by ``Notifier._safe``.
"""

from __future__ import annotations

import pytest

from trustwatch.config import NotifierConfig
from trustwatch.notifier import Notifier


def _all_channels_config():
    return NotifierConfig(
        desktop=True,
        telegram_token="tok",
        telegram_chat_id="chat",
        email_enabled=True,
        smtp_host="smtp.example",
        webhook_url="https://example/hook",
    )


def test_notify_fans_out_to_every_enabled_channel(monkeypatch):
    n = Notifier(_all_channels_config())
    called = []

    monkeypatch.setattr(n, "_desktop", lambda *a: called.append("desktop"))
    monkeypatch.setattr(n, "_telegram", lambda *a: called.append("telegram"))
    monkeypatch.setattr(n, "_email", lambda *a: called.append("email"))
    monkeypatch.setattr(n, "_webhook", lambda *a: called.append("webhook"))

    n.notify("title", "body")
    assert set(called) == {"desktop", "telegram", "email", "webhook"}


def test_one_failing_channel_does_not_stop_the_others(monkeypatch):
    n = Notifier(_all_channels_config())
    called = []

    def boom(*a):
        raise RuntimeError("telegram is down")

    monkeypatch.setattr(n, "_desktop", lambda *a: called.append("desktop"))
    monkeypatch.setattr(n, "_telegram", boom)
    monkeypatch.setattr(n, "_email", lambda *a: called.append("email"))
    monkeypatch.setattr(n, "_webhook", lambda *a: called.append("webhook"))

    # Must not raise even though a channel blows up.
    n.notify("title", "body")
    assert set(called) == {"desktop", "email", "webhook"}


def test_disabled_channels_are_not_invoked(monkeypatch):
    cfg = NotifierConfig(
        desktop=False,
        telegram_token="",  # telegram disabled (no token)
        telegram_chat_id="",
        email_enabled=False,
        webhook_url="",
    )
    n = Notifier(cfg)
    called = []
    monkeypatch.setattr(n, "_desktop", lambda *a: called.append("desktop"))
    monkeypatch.setattr(n, "_telegram", lambda *a: called.append("telegram"))
    monkeypatch.setattr(n, "_email", lambda *a: called.append("email"))
    monkeypatch.setattr(n, "_webhook", lambda *a: called.append("webhook"))

    n.notify("title", "body")
    assert called == []


def test_safe_wrapper_swallows_exceptions():
    def raiser():
        raise ValueError("nope")

    # Should not raise.
    Notifier._safe(raiser)


def test_telegram_requires_both_token_and_chat_id(monkeypatch):
    cfg = NotifierConfig(
        desktop=False, telegram_token="tok", telegram_chat_id=""
    )
    n = Notifier(cfg)
    called = []
    monkeypatch.setattr(n, "_telegram", lambda *a: called.append("telegram"))
    n.notify("t", "b")
    assert called == []


def test_email_channel_does_not_hit_network(monkeypatch):
    """With smtplib stubbed out, _email must still run without a real server."""
    import smtplib

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, *a, **k):
            pass

        def login(self, *a, **k):
            pass

        def send_message(self, *a, **k):
            pass

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    cfg = NotifierConfig(
        desktop=False,
        email_enabled=True,
        smtp_host="smtp.example",
        smtp_user="me@example.com",
        smtp_password="pw",
        email_to="me@example.com",
    )
    n = Notifier(cfg)
    # Should complete without raising and without a real connection.
    n.notify("title", "body")
