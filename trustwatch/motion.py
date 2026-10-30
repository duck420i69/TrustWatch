"""Frame-to-frame motion detection for the security-camera mode.

Classic approach: convert to grayscale, blur to remove sensor noise, diff the
current frame against a slowly-updated reference frame, threshold the delta, and
report motion when a large enough region has changed.
"""

from __future__ import annotations

from typing import Optional

from .config import MotionConfig


class MotionDetector:
    def __init__(self, cfg: MotionConfig):
        self.cfg = cfg
        self._cv2 = None
        self._ref = None  # reference (background) frame, grayscale/blurred

    def _ensure_cv2(self):
        if self._cv2 is None:
            import cv2  # type: ignore

            self._cv2 = cv2
        return self._cv2

    def _prep(self, frame):
        cv2 = self._ensure_cv2()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (21, 21), 0)

    def update(self, frame) -> int:
        """Feed a frame; return the area (px) of the largest changed region.

        Returns 0 while the detector is still establishing its reference frame.
        """
        cv2 = self._ensure_cv2()
        prepped = self._prep(frame)

        if self._ref is None:
            self._ref = prepped.astype("float")
            return 0

        # Blend the reference slowly so lighting drift doesn't cause false
        # positives, while a person moving still stands out sharply.
        cv2.accumulateWeighted(prepped, self._ref, 0.5)
        ref_uint8 = cv2.convertScaleAbs(self._ref)

        delta = cv2.absdiff(prepped, ref_uint8)
        thresh = cv2.threshold(
            delta, self.cfg.sensitivity, 255, cv2.THRESH_BINARY
        )[1]
        thresh = cv2.dilate(thresh, None, iterations=2)

        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return 0
        return int(max(cv2.contourArea(c) for c in contours))

    def is_motion(self, area: int) -> bool:
        return area >= self.cfg.min_area
