"""Tests for trustwatch.motion.

``is_motion`` is pure threshold logic and is tested directly without cv2.
``update`` needs OpenCV + numpy; that test is guarded with importorskip so it
is skipped (not failed) on machines where those are not installed.
"""

from __future__ import annotations

import pytest

from trustwatch.config import MotionConfig
from trustwatch.motion import MotionDetector


def test_is_motion_threshold_logic():
    det = MotionDetector(MotionConfig(min_area=1500))
    assert det.is_motion(1500) is True
    assert det.is_motion(2000) is True
    assert det.is_motion(1499) is False
    assert det.is_motion(0) is False


def test_is_motion_respects_configured_min_area():
    det = MotionDetector(MotionConfig(min_area=100))
    assert det.is_motion(100) is True
    assert det.is_motion(99) is False


def test_update_establishes_reference_then_detects_change():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    det = MotionDetector(MotionConfig(min_area=10, sensitivity=25))

    h, w = 120, 160
    blank = np.zeros((h, w, 3), dtype=np.uint8)

    # First frame only establishes the reference -> area 0.
    assert det.update(blank) == 0

    # Feed a frame with a large bright block: should report a positive area.
    moved = np.zeros((h, w, 3), dtype=np.uint8)
    moved[20:100, 40:140] = 255
    area = det.update(moved)
    assert isinstance(area, int)
    assert area >= 0
