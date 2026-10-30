"""Command-line interface for TrustWatch."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import __version__
from .config import Config, load_config
from .monitor import camera_loop, guard_loop, snap
from .notifier import Notifier
from .storage import read_events


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="trustwatch",
        description=(
            "Local intrusion/tamper monitor for your own laptop. Capture who "
            "accesses the machine, run a motion-detecting camera, and get alerts."
        ),
    )
    p.add_argument("--version", action="version", version=f"TrustWatch {__version__}")
    p.add_argument("-c", "--config", help="Path to a JSON (or YAML) config file.")
    p.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging to stderr."
    )

    sub = p.add_subparsers(dest="command", required=True)

    s_snap = sub.add_parser(
        "snap",
        help="Capture one access snapshot now (wire this to your OS login/unlock).",
    )
    s_snap.add_argument(
        "--kind", default="access", help="Label for this event (e.g. login, unlock)."
    )
    s_snap.add_argument(
        "--no-notify", action="store_true", help="Log only, do not send alerts."
    )

    s_cam = sub.add_parser(
        "camera", help="Run as a motion-detecting security camera until Ctrl-C."
    )
    s_cam.add_argument(
        "--no-notify", action="store_true", help="Log/save only, do not send alerts."
    )

    s_guard = sub.add_parser(
        "guard",
        help=(
            "Persistent watcher: capture on turn-on, on wake from sleep, while "
            "someone is interacting, and on USB plug/unplug. Runs until Ctrl-C."
        ),
    )
    s_guard.add_argument(
        "--no-notify", action="store_true", help="Log/save only, do not send alerts."
    )

    sub.add_parser("log", help="Show recent events.").add_argument(
        "-n", "--limit", type=int, default=20, help="How many recent events to show."
    )

    sub.add_parser(
        "test-notify", help="Send a test alert through every configured channel."
    )

    sub.add_parser(
        "show-config", help="Print the effective configuration and exit."
    )

    return p


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))

    try:
        cfg: Config = load_config(args.config)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    cfg.ensure_dirs()

    if args.command == "snap":
        record = snap(cfg, kind=args.kind, notify=not args.no_notify)
        print(record["message"])
        return 0

    if args.command == "camera":
        camera_loop(cfg, notify=not args.no_notify)
        return 0

    if args.command == "guard":
        guard_loop(cfg, notify=not args.no_notify)
        return 0

    if args.command == "log":
        events = read_events(cfg, limit=args.limit)
        if not events:
            print("No events recorded yet.")
            return 0
        for ev in events:
            img = f"  [{ev['image']}]" if ev.get("image") else ""
            when = ev.get("time", "?")
            kind = ev.get("kind", "?")
            msg = ev.get("message", "")
            print(f"{when}  {kind:<12} {msg}{img}")
        return 0

    if args.command == "test-notify":
        Notifier(cfg.notifier).notify(
            title="TrustWatch: test alert",
            body="If you can read this, notifications are working.",
        )
        print("Test alert dispatched to all configured channels.")
        return 0

    if args.command == "show-config":
        # Redacted so secrets (token, SMTP password, webhook URL) aren't leaked
        # when the output is pasted into a bug report.
        print(json.dumps(cfg.to_redacted_dict(), indent=2))
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
