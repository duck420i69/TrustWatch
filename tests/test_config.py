"""Tests for trustwatch.config.load_config."""

from __future__ import annotations

import json

from trustwatch.config import (
    Config,
    DEFAULT_DATA_DIR,
    NotifierConfig,
    load_config,
)

from conftest import EXAMPLE_CONFIG


def test_load_config_none_returns_defaults():
    cfg = load_config(None)
    assert isinstance(cfg, Config)
    assert cfg.data_dir == str(DEFAULT_DATA_DIR)
    # Section defaults.
    assert cfg.notifier == NotifierConfig()
    assert cfg.notifier.desktop is True
    assert cfg.notifier.email_enabled is False
    assert cfg.camera.device_index == 0
    assert cfg.motion.min_area == 1500


def test_load_example_config():
    assert EXAMPLE_CONFIG.exists(), "config.example.json should ship with the repo"
    cfg = load_config(str(EXAMPLE_CONFIG))
    assert cfg.data_dir == "~/.trustwatch"
    assert cfg.camera.device_index == 0
    assert cfg.camera.warmup_frames == 5
    assert cfg.motion.min_area == 1500
    assert cfg.motion.cooldown_seconds == 20
    assert cfg.notifier.desktop is True
    assert cfg.notifier.smtp_host == "smtp.gmail.com"
    assert cfg.notifier.smtp_port == 587
    assert cfg.notifier.email_enabled is False


def test_unknown_keys_are_ignored(tmp_path):
    raw = {
        "data_dir": str(tmp_path / "dd"),
        "surprise_top_level": 123,
        "camera": {"device_index": 2, "nonsense": "ignored"},
        "motion": {"min_area": 9000, "also_bogus": True},
        "notifier": {"desktop": False, "unknown_channel": "x"},
    }
    p = tmp_path / "config.json"
    p.write_text(json.dumps(raw), encoding="utf-8")

    cfg = load_config(str(p))
    assert cfg.data_dir == str(tmp_path / "dd")
    assert cfg.camera.device_index == 2
    assert cfg.motion.min_area == 9000
    assert cfg.notifier.desktop is False
    # Unknown keys must not become attributes.
    assert not hasattr(cfg.camera, "nonsense")
    assert not hasattr(cfg.notifier, "unknown_channel")


def test_env_vars_override_secrets(tmp_path, monkeypatch):
    raw = {
        "notifier": {
            "telegram_token": "from-file-token",
            "telegram_chat_id": "from-file-chat",
            "smtp_password": "from-file-pw",
            "webhook_url": "https://file.example/hook",
        }
    }
    p = tmp_path / "config.json"
    p.write_text(json.dumps(raw), encoding="utf-8")

    monkeypatch.setenv("TRUSTWATCH_TELEGRAM_TOKEN", "env-token")
    monkeypatch.setenv("TRUSTWATCH_TELEGRAM_CHAT_ID", "env-chat")
    monkeypatch.setenv("TRUSTWATCH_SMTP_PASSWORD", "env-pw")
    monkeypatch.setenv("TRUSTWATCH_WEBHOOK_URL", "https://env.example/hook")

    cfg = load_config(str(p))
    assert cfg.notifier.telegram_token == "env-token"
    assert cfg.notifier.telegram_chat_id == "env-chat"
    assert cfg.notifier.smtp_password == "env-pw"
    assert cfg.notifier.webhook_url == "https://env.example/hook"


def test_env_vars_fall_back_to_file_value(tmp_path, monkeypatch):
    raw = {"notifier": {"telegram_token": "keep-me"}}
    p = tmp_path / "config.json"
    p.write_text(json.dumps(raw), encoding="utf-8")

    monkeypatch.delenv("TRUSTWATCH_TELEGRAM_TOKEN", raising=False)
    cfg = load_config(str(p))
    assert cfg.notifier.telegram_token == "keep-me"
