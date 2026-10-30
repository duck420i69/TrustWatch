"""The two monitoring modes: a one-shot access snapshot, and the camera loop."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from .camera import Camera, CameraError, capture_single
from .config import Config
from .motion import MotionDetector
from .notifier import Notifier
from .storage import log_event, snapshot_path

log = logging.getLogger("trustwatch.monitor")


def snap(cfg: Config, kind: str = "access", notify: bool = True) -> dict:
    """Capture one frame, log it, and alert. Meant to be fired on login/unlock.

    Returns the logged event record.
    """
    cfg.ensure_dirs()
    path = snapshot_path(cfg, kind)
    when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        capture_single(cfg.camera, path)
        image = path
        message = f"Device accessed at {when}. Snapshot saved."
    except CameraError as exc:
        # Still record the access even if the camera is blocked/unavailable —
        # a covered or disabled camera is itself worth knowing about.
        image = None
        message = f"Device accessed at {when}, but camera capture failed: {exc}"
        log.warning(message)

    record = log_event(cfg, kind, message, image_path=image)

    if notify:
        Notifier(cfg.notifier).notify(
            title="TrustWatch: device accessed",
            body=message,
            image_path=image,
        )
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
        with Camera(cfg.camera) as cam:
            while True:
                try:
                    frame = cam.read()
                except CameraError as exc:
                    log.warning("Frame read failed: %s", exc)
                    time.sleep(1.0)
                    continue

                area = detector.update(frame)
                if detector.is_motion(area):
                    streak += 1
                else:
                    streak = 0

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
    except KeyboardInterrupt:
        log.info("Stopping security camera.")
        log_event(cfg, "camera_stop", "Security camera mode stopped.")
