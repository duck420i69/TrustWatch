"""Tests for the guard iteration logic (monitor._guard_tick / _GuardState).

The real guard_loop is an infinite loop, so the per-iteration decision logic —
wake-from-sleep detection, USB add/remove diffing, and the interaction cooldown —
is extracted into _guard_tick and unit-tested here with injected clocks and
stubbed hardware/activity sources.
"""

from __future__ import annotations

import trustwatch.monitor as monitor
from trustwatch.screen import ScreenCaptureError
from trustwatch.storage import read_events


def _stub_capture(monkeypatch):
    """Replace _capture with a hardware-free stub returning a minimal record."""
    monkeypatch.setattr(
        monitor, "_capture",
        lambda cfg, kind, **kw: {
            "kind": kind, "message": kind, "_photo": None, "_screenshot": None,
        },
    )


def _no_signals(monkeypatch):
    """Default: nothing plugged, no interaction, no foreground window."""
    monkeypatch.setattr(monitor.activity, "list_usb_devices", lambda: set())
    monkeypatch.setattr(monitor.activity, "seconds_since_last_input", lambda: 999.0)
    monkeypatch.setattr(monitor.activity, "active_window", lambda: None)


def test_tick_quiet_captures_nothing(config, monkeypatch):
    _stub_capture(monkeypatch)
    _no_signals(monkeypatch)
    state = monitor._GuardState(config)
    captured = monitor._guard_tick(
        config, state, notify=False, now_wall=state.last_wall, now_mono=1000.0
    )
    assert captured == []


def test_tick_detects_wake_from_sleep(config, monkeypatch):
    _stub_capture(monkeypatch)
    _no_signals(monkeypatch)
    state = monitor._GuardState(config)
    g = config.guard
    # A wall-clock jump far bigger than one poll interval == we were suspended.
    jump = state.last_wall + g.poll_interval + g.wake_gap_seconds + 60
    captured = monitor._guard_tick(
        config, state, notify=False, now_wall=jump, now_mono=1000.0
    )
    assert "wake" in captured


def test_tick_no_false_wake_on_normal_interval(config, monkeypatch):
    _stub_capture(monkeypatch)
    _no_signals(monkeypatch)
    state = monitor._GuardState(config)
    normal = state.last_wall + config.guard.poll_interval  # ordinary tick
    captured = monitor._guard_tick(
        config, state, notify=False, now_wall=normal, now_mono=1000.0
    )
    assert "wake" not in captured


def test_tick_usb_change_captures_and_persists_detail(config, monkeypatch):
    # Let _capture run for real (so persistence is exercised), but no hardware.
    monkeypatch.setattr(monitor, "capture_single",
                        lambda c, p: (p.write_bytes(b"x"), p)[1])
    monkeypatch.setattr(
        monitor.screen, "capture_screen",
        lambda *a, **k: (_ for _ in ()).throw(ScreenCaptureError("no display")),
    )
    monkeypatch.setattr(monitor.activity, "active_window", lambda: None)
    monkeypatch.setattr(monitor.activity, "seconds_since_last_input", lambda: 999.0)

    # Baseline (empty) at state construction, then one device appears.
    seq = iter([set(), {"1d6b:0002"}])
    monkeypatch.setattr(monitor.activity, "list_usb_devices",
                        lambda: next(seq, {"1d6b:0002"}))

    state = monitor._GuardState(config)  # consumes the empty baseline
    captured = monitor._guard_tick(
        config, state, notify=False, now_wall=state.last_wall, now_mono=1000.0
    )
    assert "usb" in captured

    usb_events = [e for e in read_events(config) if e["kind"] == "usb"]
    assert len(usb_events) == 1
    # The forensic detail is persisted in the log, not just the notification.
    assert "1d6b:0002" in usb_events[0]["message"]
    assert usb_events[0]["extra"]["usb_added"] == ["1d6b:0002"]


def test_tick_interaction_respects_cooldown(config, monkeypatch):
    _stub_capture(monkeypatch)
    monkeypatch.setattr(monitor.activity, "list_usb_devices", lambda: set())
    monkeypatch.setattr(monitor.activity, "active_window", lambda: None)
    monkeypatch.setattr(monitor.activity, "seconds_since_last_input", lambda: 0.0)

    state = monitor._GuardState(config)
    base = state.last_wall
    cooldown = config.guard.interaction_cooldown

    first = monitor._guard_tick(config, state, notify=False, now_wall=base, now_mono=1000.0)
    assert "interaction" in first

    # Still within cooldown -> no repeat capture even though input continues.
    soon = monitor._guard_tick(config, state, notify=False, now_wall=base, now_mono=1001.0)
    assert "interaction" not in soon

    # Past the cooldown -> captures again.
    later = monitor._guard_tick(
        config, state, notify=False, now_wall=base, now_mono=1000.0 + cooldown + 1
    )
    assert "interaction" in later
