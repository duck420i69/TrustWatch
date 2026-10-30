"""Webcam access, isolated so the rest of the code never touches OpenCV directly.

OpenCV is imported lazily so that `trustwatch --help` and config validation work
on a machine where opencv-python is not installed yet.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .config import CameraConfig


class CameraError(RuntimeError):
    pass


class Camera:
    """A thin context-managed wrapper over a single OpenCV capture device."""

    def __init__(self, cfg: CameraConfig):
        self.cfg = cfg
        self._cap = None
        self._cv2 = None

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise CameraError(
                "opencv-python is required. Install it with:\n"
                "    pip install opencv-python"
            ) from exc

        self._cv2 = cv2
        cap = cv2.VideoCapture(self.cfg.device_index)
        if self.cfg.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        if self.cfg.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)

        if not cap.isOpened():
            cap.release()
            raise CameraError(
                f"Could not open camera index {self.cfg.device_index}. "
                "Is another app using it, or does this process lack camera "
                "permission? On macOS, grant Camera access to your terminal."
            )
        self._cap = cap

        # Discard a few frames so auto-exposure/white-balance can settle,
        # otherwise the first capture is often black.
        for _ in range(max(0, self.cfg.warmup_frames)):
            self._cap.read()
            time.sleep(0.02)

    def read(self):
        """Return a single BGR frame (numpy array), or raise on failure."""
        if self._cap is None:
            raise CameraError("Camera is not open.")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise CameraError("Failed to read a frame from the camera.")
        return frame

    def capture_to_file(self, path: Path) -> Path:
        """Grab one frame and write it to `path`. Returns the path."""
        frame = self.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self._cv2.imwrite(str(path), frame):
            raise CameraError(f"Could not write image to {path}")
        return path

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def capture_single(cfg: CameraConfig, path: Path) -> Path:
    """Open the camera, grab one frame to `path`, and close. Convenience helper."""
    with Camera(cfg) as cam:
        return cam.capture_to_file(path)
