"""Configuration loading for TrustWatch.

Config is plain JSON so there are no required third-party dependencies to read
it. A YAML file is also accepted if PyYAML happens to be installed. Unknown keys
are ignored, and every field has a sensible default, so a missing or partial
config file still works.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_DATA_DIR = Path.home() / ".trustwatch"


@dataclass
class NotifierConfig:
    # Desktop pop-up on the machine itself (useful while you are nearby).
    desktop: bool = True

    # Telegram bot: reaches your phone. Create a bot via @BotFather, then send it
    # a message and read your chat id from https://api.telegram.org/bot<token>/getUpdates
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # Email over SMTP (e.g. a Gmail app password).
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_to: str = ""

    # Generic webhook: TrustWatch POSTs a JSON body (and the image as multipart
    # when possible) to this URL. Works with Slack/Discord incoming webhooks,
    # IFTTT, ntfy.sh, Home Assistant, your own server, etc.
    webhook_url: str = ""


@dataclass
class CameraConfig:
    device_index: int = 0          # which webcam (0 is the default built-in cam)
    warmup_frames: int = 5         # frames to discard so exposure can settle
    width: int = 0                 # 0 = leave at the camera default
    height: int = 0


@dataclass
class MotionConfig:
    min_area: int = 1500           # contour pixels before it counts as motion
    sensitivity: int = 25          # pixel delta threshold (lower = more sensitive)
    cooldown_seconds: float = 20.0 # minimum gap between motion alerts
    consecutive_frames: int = 2    # frames of motion in a row before alerting
    poll_interval: float = 0.1     # seconds between frames in camera mode


@dataclass
class ScreenConfig:
    enabled: bool = True           # also grab a screenshot ("what they're doing")
    monitor: int = 0               # 0 = whole virtual desktop; >=1 a single display
    max_width: int = 1280          # downscale wide screenshots to keep files small


@dataclass
class GuardConfig:
    poll_interval: float = 2.0            # seconds between checks while guarding
    capture_on_start: bool = True         # snapshot when guard starts (i.e. turn-on)
    capture_on_wake: bool = True          # snapshot when the machine resumes from sleep
    wake_gap_seconds: float = 30.0        # a poll gap larger than this => it slept
    capture_on_interaction: bool = True   # snapshot when someone is actively using it
    interaction_idle_threshold: float = 3.0  # idle under this => a person is present
    interaction_cooldown: float = 90.0    # min seconds between interaction snapshots
    capture_on_usb_change: bool = True    # snapshot when USB devices are plugged/removed
    log_activity: bool = True             # log foreground app/window changes


@dataclass
class Config:
    data_dir: str = str(DEFAULT_DATA_DIR)
    notifier: NotifierConfig = field(default_factory=NotifierConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    guard: GuardConfig = field(default_factory=GuardConfig)

    @property
    def snapshot_dir(self) -> Path:
        return Path(self.data_dir).expanduser() / "snapshots"

    @property
    def log_path(self) -> Path:
        return Path(self.data_dir).expanduser() / "events.log"

    def ensure_dirs(self) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    # Fields that hold credentials and must never be printed verbatim.
    _SECRET_FIELDS = ("telegram_token", "smtp_password", "webhook_url")

    def to_redacted_dict(self) -> Dict[str, Any]:
        """Like :meth:`to_dict`, but with secret values masked.

        Used by ``show-config`` so pasting its output can't leak a bot token,
        SMTP password, or webhook URL.
        """
        data = self.to_dict()
        notifier = data.get("notifier", {})
        for key in self._SECRET_FIELDS:
            if notifier.get(key):
                notifier[key] = "***set (hidden)***"
        return data


def _load_raw(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "YAML config requires PyYAML (pip install pyyaml), or use JSON."
            ) from exc
        return yaml.safe_load(text) or {}
    return json.loads(text)


def _merge(section_cls, raw: Optional[Dict[str, Any]]):
    """Build a dataclass instance from raw dict, keeping only known fields."""
    known = {f.name for f in section_cls.__dataclass_fields__.values()}
    data = {k: v for k, v in (raw or {}).items() if k in known}
    return section_cls(**data)


def load_config(path: Optional[str]) -> Config:
    """Load config from the given path, or return defaults if path is None/missing."""
    if not path:
        return Config()

    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    raw = _load_raw(p)
    cfg = Config(
        data_dir=raw.get("data_dir", str(DEFAULT_DATA_DIR)),
        notifier=_merge(NotifierConfig, raw.get("notifier")),
        camera=_merge(CameraConfig, raw.get("camera")),
        motion=_merge(MotionConfig, raw.get("motion")),
        screen=_merge(ScreenConfig, raw.get("screen")),
        guard=_merge(GuardConfig, raw.get("guard")),
    )

    # Environment variables override secrets so you need not keep them in a file.
    cfg.notifier.telegram_token = os.environ.get(
        "TRUSTWATCH_TELEGRAM_TOKEN", cfg.notifier.telegram_token
    )
    cfg.notifier.telegram_chat_id = os.environ.get(
        "TRUSTWATCH_TELEGRAM_CHAT_ID", cfg.notifier.telegram_chat_id
    )
    cfg.notifier.smtp_password = os.environ.get(
        "TRUSTWATCH_SMTP_PASSWORD", cfg.notifier.smtp_password
    )
    cfg.notifier.webhook_url = os.environ.get(
        "TRUSTWATCH_WEBHOOK_URL", cfg.notifier.webhook_url
    )
    return cfg
