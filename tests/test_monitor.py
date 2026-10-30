"""Tests for trustwatch.monitor.snap.

``capture_single`` and ``Notifier`` are monkeypatched so no camera or network is
needed. We verify both the success path (image logged) and the camera-failure
path (access still logged, image=None, no crash).
"""

from __future__ import annotations

import trustwatch.monitor as monitor
from trustwatch.camera import CameraError
from trustwatch.storage import read_events


class _FakeNotifier:
    """Stand-in for Notifier that records calls instead of alerting."""

    instances = []

    def __init__(self, cfg):
        self.cfg = cfg
        self.calls = []
        _FakeNotifier.instances.append(self)

    def notify(self, title, body, image_path=None):
        self.calls.append((title, body, image_path))


def test_snap_success_logs_event_with_image(config, monkeypatch):
    _FakeNotifier.instances = []

    def fake_capture_single(cam_cfg, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xd8\xff\xd9")  # dummy JPEG bytes
        return path

    monkeypatch.setattr(monitor, "capture_single", fake_capture_single)
    monkeypatch.setattr(monitor, "Notifier", _FakeNotifier)

    record = monitor.snap(config, kind="login", notify=True)

    assert record["kind"] == "login"
    assert record["image"] is not None
    assert record["image"].endswith("_login.jpg")

    events = read_events(config)
    assert len(events) == 1
    assert events[0]["image"] is not None

    # Notification fired with the image path.
    assert len(_FakeNotifier.instances) == 1
    assert _FakeNotifier.instances[0].calls
    assert _FakeNotifier.instances[0].calls[0][2] is not None


def test_snap_camera_failure_still_logs_without_image(config, monkeypatch):
    _FakeNotifier.instances = []

    def boom_capture(cam_cfg, path):
        raise CameraError("camera is covered")

    monkeypatch.setattr(monitor, "capture_single", boom_capture)
    monkeypatch.setattr(monitor, "Notifier", _FakeNotifier)

    # Must not raise.
    record = monitor.snap(config, kind="access", notify=True)

    assert record["kind"] == "access"
    assert record["image"] is None
    # The event message must make the webcam failure visible (wording-agnostic).
    assert "fail" in record["message"].lower()
    assert record["extra"]["camera_ok"] is False

    events = read_events(config)
    assert len(events) == 1
    assert events[0]["image"] is None

    # Still notified (with image_path None).
    assert _FakeNotifier.instances[0].calls[0][2] is None


def test_capture_bundles_webcam_screenshot_and_activity(config, monkeypatch):
    """_capture records webcam photo + screenshot + foreground app in one event."""

    def fake_capture_single(cam_cfg, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xd8\xff\xd9")
        return path

    def fake_capture_screen(path, monitor=0, max_width=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG")
        return path

    monkeypatch.setattr(monitor, "capture_single", fake_capture_single)
    monkeypatch.setattr(monitor.screen, "capture_screen", fake_capture_screen)
    monkeypatch.setattr(
        monitor.activity, "active_window",
        lambda: {"app": "Terminal", "title": "secret-plans.txt"},
    )

    record = monitor._capture(config, "startup")

    assert record["image"] is not None            # webcam photo
    assert record["extra"]["camera_ok"] is True
    assert record["extra"]["screenshot"] is not None
    assert record["extra"]["app"] == "Terminal"
    assert record["extra"]["window_title"] == "secret-plans.txt"
    assert len(read_events(config)) == 1


def test_capture_survives_screenshot_and_activity_failure(config, monkeypatch):
    """A screenshot or activity failure must not sink the whole capture."""
    from trustwatch.screen import ScreenCaptureError

    monkeypatch.setattr(
        monitor, "capture_single",
        lambda c, p: (p.write_bytes(b"x"), p)[1],
    )

    def boom_screen(path, monitor=0, max_width=0):
        raise ScreenCaptureError("no display")

    monkeypatch.setattr(monitor.screen, "capture_screen", boom_screen)
    monkeypatch.setattr(
        monitor.activity, "active_window",
        lambda: (_ for _ in ()).throw(RuntimeError("x11 gone")),
    )

    record = monitor._capture(config, "wake")  # must not raise
    assert record["extra"]["camera_ok"] is True
    assert record["extra"]["screenshot"] is None
    assert record["extra"]["app"] is None


def test_snap_no_notify_does_not_build_notifier(config, monkeypatch):
    _FakeNotifier.instances = []

    def fake_capture_single(cam_cfg, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path

    monkeypatch.setattr(monitor, "capture_single", fake_capture_single)
    monkeypatch.setattr(monitor, "Notifier", _FakeNotifier)

    monitor.snap(config, kind="login", notify=False)
    assert _FakeNotifier.instances == []
    assert len(read_events(config)) == 1
