"""The monitoring modes.

- ``snap``        — one access capture (webcam + screenshot + activity), meant to
                    be fired on login/unlock.
- ``camera_loop`` — a motion-detecting security camera.
- ``guard_loop``  — a persistent watcher that captures on start (turn-on), on
                    resume from sleep, while someone is actively interacting, and
                    when USB devices are plugged in or removed.

"What the person is doing" is recorded as a screenshot plus the foreground
app/window name. TrustWatch never records keystrokes or typed content — see
``trustwatch/activity.py``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import activity, screen
from .camera import CameraError, capture_single
from .config import Config
from .motion import MotionDetector
from .notifier import Notifier
from .storage import log_event, snapshot_path

log = logging.getLogger("trustwatch.monitor")


def _capture_screenshot(cfg: Config, kind: str) -> Optional[Path]:
    """Grab a screenshot if enabled; return its path, or None on any failure."""
    if not cfg.screen.enabled:
        return None
    path = snapshot_path(cfg, f"{kind}-screen").with_suffix(".jpg")
    try:
        screen.capture_screen(
            path, monitor=cfg.screen.monitor, max_width=cfg.screen.max_width
        )
        return path
    except screen.ScreenCaptureError as exc:
        log.debug("Screenshot skipped: %s", exc)
        return None


def _capture(
    cfg: Config,
    kind: str,
    note: Optional[str] = None,
    extra_fields: Optional[dict] = None,
) -> dict:
    """Capture one event: webcam photo + screenshot + foreground activity.

    Always returns a record describing what was captured. A failure of any single
    source (camera covered, no display, headless) is recorded but never raises —
    a blocked camera or screen is itself worth knowing about.

    Args:
        note: Extra text appended to the persisted event message (e.g. which USB
            devices changed), so the detail survives in ``events.log``.
        extra_fields: Additional structured fields merged into the event's
            ``extra`` dict.
    """
    when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Webcam photo of who is at the machine.
    photo: Optional[Path] = snapshot_path(cfg, kind)
    camera_ok = True
    try:
        capture_single(cfg.camera, photo)
    except CameraError as exc:
        camera_ok = False
        photo = None
        log.warning("Camera capture failed for %s: %s", kind, exc)

    # Screenshot of what is on screen.
    shot = _capture_screenshot(cfg, kind)

    # Which application is in focus (never what is typed into it).
    win = None
    try:
        win = activity.active_window()
    except Exception as exc:  # noqa: BLE001 - activity must never crash a capture
        log.debug("active_window failed: %s", exc)

    extra = {
        "camera_ok": camera_ok,
        "screenshot": str(shot) if shot else None,
        "app": (win or {}).get("app"),
        "window_title": (win or {}).get("title"),
    }
    if extra_fields:
        extra.update(extra_fields)

    parts = [f"Event '{kind}' at {when}."]
    parts.append("Webcam photo saved." if camera_ok else "Webcam capture FAILED.")
    if shot:
        parts.append("Screenshot saved.")
    if win and (win.get("app") or win.get("title")):
        parts.append(f"Foreground: {win.get('app') or '?'} — {win.get('title') or ''}".strip())
    if note:
        parts.append(note)
    message = " ".join(parts)

    record = log_event(cfg, kind, message, image_path=photo, extra=extra)
    record["_photo"] = photo
    record["_screenshot"] = shot
    return record


def _notify_capture(cfg: Config, title: str, record: dict) -> None:
    """Send a capture record out through the notifier (webcam photo attached)."""
    body = record["message"]
    shot = record.get("_screenshot")
    if shot:
        body += f"\nScreenshot: {shot}"
    Notifier(cfg.notifier).notify(
        title=title, body=body, image_path=record.get("_photo")
    )


def snap(cfg: Config, kind: str = "access", notify: bool = True) -> dict:
    """Capture one access event (webcam + screenshot + activity), log it, alert.

    Meant to be fired on login/unlock. Returns the logged event record.
    """
    cfg.ensure_dirs()
    record = _capture(cfg, kind)
    if notify:
        _notify_capture(cfg, "TrustWatch: device accessed", record)
    return record


def camera_loop(cfg: Config, kind: str = "motion", notify: bool = True) -> None:
    """Run the motion-detecting security camera until interrupted (Ctrl-C)."""
    cfg.ensure_dirs()
    detector = MotionDetector(cfg.motion)
    mcfg = cfg.motion
    notifier = Notifier(cfg.notifier)

    last_alert = 0.0
    streak = 0

    log.info(
        "Security camera running (min_area=%d, cooldown=%ss). Press Ctrl-C to stop.",
        mcfg.min_area,
        mcfg.cooldown_seconds,
    )
    log_event(cfg, "camera_start", "Security camera mode started.")

    try:
        from .camera import Camera

        with Camera(cfg.camera) as cam:
            while True:
                try:
                    frame = cam.read()
                except CameraError as exc:
                    log.warning("Frame read failed: %s", exc)
                    time.sleep(1.0)
                    continue

                area = detector.update(frame)
                streak = streak + 1 if detector.is_motion(area) else 0

                now = time.monotonic()
                ready = (now - last_alert) >= mcfg.cooldown_seconds
                if streak >= mcfg.consecutive_frames and ready:
                    last_alert = now
                    streak = 0
                    path = snapshot_path(cfg, kind)
                    try:
                        cam.capture_to_file(path)
                        image = path
                    except CameraError:
                        image = None
                    when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    message = f"Motion detected at {when} (area={area}px)."
                    log.info(message)
                    log_event(cfg, kind, message, image_path=image,
                              extra={"area": area})
                    if notify:
                        notifier.notify(
                            title="TrustWatch: motion detected",
                            body=message,
                            image_path=image,
                        )

                time.sleep(mcfg.poll_interval)
    except CameraError as exc:
        # Raised when the camera can't be opened at all (bad index, in use, no
        # permission). Report cleanly instead of dying with a traceback.
        msg = f"Cannot start security camera: {exc}"
        log.error(msg)
        log_event(cfg, "camera_error", msg)
        if notify:
            Notifier(cfg.notifier).notify(
                title="TrustWatch: camera unavailable", body=msg
            )
    except KeyboardInterrupt:
        log.info("Stopping security camera.")
        log_event(cfg, "camera_stop", "Security camera mode stopped.")


class _GuardState:
    """Mutable state carried across guard iterations (see :func:`_guard_tick`)."""

    def __init__(self, cfg: Config):
        self.known_usb = (
            activity.list_usb_devices() if cfg.guard.capture_on_usb_change else set()
        )
        self.last_interaction_capture = 0.0
        self.last_app_title: Optional[str] = None
        # Set last, so the first tick's gap is ~poll_interval (no false wake).
        self.last_wall = time.time()


def _guard_tick(
    cfg: Config,
    state: _GuardState,
    notify: bool = True,
    now_wall: Optional[float] = None,
    now_mono: Optional[float] = None,
) -> list:
    """Run one guard iteration against `state`; return the kinds captured.

    Clocks are injectable for testing: ``now_wall`` (wall clock, for suspend
    detection — a frozen monotonic clock can't see a suspend) and ``now_mono``
    (monotonic, for the interaction cooldown).
    """
    g = cfg.guard
    now_wall = time.time() if now_wall is None else now_wall
    now_mono = time.monotonic() if now_mono is None else now_mono
    captured: list = []

    # --- resume-from-sleep detection -------------------------------------
    gap = now_wall - state.last_wall
    state.last_wall = now_wall
    if g.capture_on_wake and gap > (g.poll_interval + g.wake_gap_seconds):
        log.info("Resume from sleep detected (gap %.0fs).", gap)
        rec = _capture(cfg, "wake")
        captured.append("wake")
        if notify:
            _notify_capture(cfg, "TrustWatch: woke from sleep", rec)

    # --- USB plug/unplug detection ---------------------------------------
    if g.capture_on_usb_change:
        current = activity.list_usb_devices()
        added = current - state.known_usb
        removed = state.known_usb - current
        if added or removed:
            state.known_usb = current
            detail = []
            if added:
                detail.append(f"added: {', '.join(sorted(added))}")
            if removed:
                detail.append(f"removed: {', '.join(sorted(removed))}")
            detail_str = "; ".join(detail)
            log.info("USB change (%s).", detail_str)
            rec = _capture(
                cfg, "usb",
                note=f"USB change — {detail_str}",
                extra_fields={
                    "usb_added": sorted(added),
                    "usb_removed": sorted(removed),
                },
            )
            captured.append("usb")
            if notify:
                _notify_capture(cfg, "TrustWatch: USB device change", rec)

    # --- active-interaction detection ------------------------------------
    idle = activity.seconds_since_last_input()
    interacting = idle is not None and idle <= g.interaction_idle_threshold
    if (
        g.capture_on_interaction
        and interacting
        and (now_mono - state.last_interaction_capture) >= g.interaction_cooldown
    ):
        state.last_interaction_capture = now_mono
        rec = _capture(cfg, "interaction")
        captured.append("interaction")
        if notify:
            _notify_capture(cfg, "TrustWatch: someone is using the laptop", rec)

    # --- lightweight activity timeline -----------------------------------
    if g.log_activity:
        win = activity.active_window()
        if win:
            sig = f"{win.get('app')}|{win.get('title')}"
            if sig != state.last_app_title:
                state.last_app_title = sig
                log_event(
                    cfg, "activity",
                    f"Foreground: {win.get('app') or '?'} — {win.get('title') or ''}".strip(),
                    extra={"app": win.get("app"), "window_title": win.get("title")},
                )
    return captured


def guard_loop(cfg: Config, notify: bool = True) -> None:
    """Persistent watcher: capture on turn-on, on wake, on interaction, on USB change.

    Runs until interrupted (Ctrl-C). Because userspace code cannot execute while
    the laptop is physically suspended, "running during sleep" means this loop
    detects the resume (a poll gap far larger than the interval) and captures the
    instant the machine wakes. Pair it with the OS autostart in ``install/`` so it
    restarts on boot/login and keeps watching across sleep cycles.
    """
    cfg.ensure_dirs()
    g = cfg.guard

    log.info("Guard mode started (poll=%ss). Press Ctrl-C to stop.", g.poll_interval)
    log_event(cfg, "guard_start", "Guard mode started.")

    if g.capture_on_start:
        rec = _capture(cfg, "startup")
        if notify:
            _notify_capture(cfg, "TrustWatch: device turned on / guard started", rec)

    state = _GuardState(cfg)
    try:
        while True:
            time.sleep(g.poll_interval)
            try:
                _guard_tick(cfg, state, notify=notify)
            except Exception as exc:  # noqa: BLE001 - one bad tick must not stop guard
                log.warning("Guard iteration failed (continuing): %s", exc)
    except KeyboardInterrupt:
        log.info("Stopping guard mode.")
        log_event(cfg, "guard_stop", "Guard mode stopped.")
