"""Local, append-only event log and snapshot paths.

Everything stays on the machine (under the configured data_dir). Nothing is
uploaded unless you explicitly configure a notification channel.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import Config


def timestamp_slug(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now()
    return dt.strftime("%Y%m%d-%H%M%S")


def snapshot_path(cfg: Config, kind: str, dt: Optional[datetime] = None) -> Path:
    """Return a unique snapshot path like snapshots/20260101-091500_login.jpg."""
    cfg.ensure_dirs()
    safe_kind = "".join(c for c in kind if c.isalnum() or c in "-_") or "event"
    return cfg.snapshot_dir / f"{timestamp_slug(dt)}_{safe_kind}.jpg"


def log_event(
    cfg: Config,
    kind: str,
    message: str,
    image_path: Optional[Path] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Append one JSON line to the event log and return the record."""
    cfg.ensure_dirs()
    record = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "message": message,
        "image": str(image_path) if image_path else None,
    }
    if extra:
        record["extra"] = extra

    with cfg.log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def read_events(cfg: Config, limit: int = 50) -> list[dict]:
    """Return the most recent events (newest last), up to `limit`."""
    if not cfg.log_path.exists():
        return []
    lines = cfg.log_path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
