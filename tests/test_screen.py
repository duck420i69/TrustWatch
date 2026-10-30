"""Tests for trustwatch.screen (written against the agreed API).

The module may not exist yet while it is being developed in parallel; in that
case these tests skip rather than fail.
"""

from __future__ import annotations

import sys

import pytest

screen = pytest.importorskip(
    "trustwatch.screen",
    reason="trustwatch.screen not implemented yet",
)


def test_public_api_is_present():
    assert hasattr(screen, "capture_screen")
    assert callable(screen.capture_screen)
    assert hasattr(screen, "ScreenCaptureError")
    assert issubclass(screen.ScreenCaptureError, Exception)


def test_capture_screen_raises_when_no_backend(tmp_path, monkeypatch):
    """With both mss and Pillow unavailable, capture must raise cleanly."""
    # Make `import mss` and anything under PIL fail with ImportError.
    monkeypatch.setitem(sys.modules, "mss", None)
    monkeypatch.setitem(sys.modules, "mss.tools", None)
    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setitem(sys.modules, "PIL.Image", None)
    monkeypatch.setitem(sys.modules, "PIL.ImageGrab", None)

    dest = tmp_path / "shot.png"
    with pytest.raises(screen.ScreenCaptureError):
        screen.capture_screen(dest)


def test_capture_screen_accepts_monitor_and_max_width_kwargs(tmp_path, monkeypatch):
    """Signature contract: monitor and max_width are accepted keyword args.

    We force the no-backend path so the call fails deterministically with the
    documented error rather than trying to touch a real display.
    """
    monkeypatch.setitem(sys.modules, "mss", None)
    monkeypatch.setitem(sys.modules, "mss.tools", None)
    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setitem(sys.modules, "PIL.Image", None)
    monkeypatch.setitem(sys.modules, "PIL.ImageGrab", None)

    dest = tmp_path / "shot.jpg"
    with pytest.raises(screen.ScreenCaptureError):
        screen.capture_screen(dest, monitor=1, max_width=800)
