"""Screenshot capture, isolated so the rest of the code never touches a
screenshot backend directly.

This module grabs the screen *image* only ("what is on the display"). It never
reads keystrokes, clipboard contents, or any other input. The screenshot
backends (``mss`` and Pillow) are imported lazily so that ``trustwatch --help``
and config validation keep working on a machine where neither is installed.

The preferred backend is ``mss`` (fast, cross-platform, multi-monitor). If it
is not available we fall back to Pillow's ``PIL.ImageGrab``. If neither is
installed we raise :class:`ScreenCaptureError` with install hints.
"""

from __future__ import annotations

import pathlib


class ScreenCaptureError(RuntimeError):
    """Raised when no screenshot backend is available or a capture fails."""


_NO_BACKEND_MSG = (
    "Screenshot capture needs 'mss' (pip install mss) "
    "or Pillow (pip install Pillow)."
)


def capture_screen(
    path: pathlib.Path,
    monitor: int = 0,
    max_width: int = 0,
) -> pathlib.Path:
    """Capture the screen to ``path`` (JPEG/PNG by extension) and return it.

    Args:
        path: Destination file. The image format is chosen from ``path.suffix``
            (e.g. ``.png`` or ``.jpg``/``.jpeg``).
        monitor: ``0`` captures the full virtual desktop (all monitors merged).
            A value ``>= 1`` selects a single physical display.
        max_width: If greater than ``0`` and the captured image is wider, the
            image is scaled down proportionally so its width is ``<= max_width``
            (to keep files small). ``0`` disables scaling.

    Returns:
        The ``path`` that was written.

    Raises:
        ScreenCaptureError: If no screenshot backend is installed, or the
            capture otherwise fails (for example on a headless machine with no
            display available).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import mss  # type: ignore
    except ImportError:
        return _capture_with_pillow(path, monitor=monitor, max_width=max_width)

    return _capture_with_mss(mss, path, monitor=monitor, max_width=max_width)


def _capture_with_mss(
    mss,
    path: pathlib.Path,
    monitor: int,
    max_width: int,
) -> pathlib.Path:
    """Capture using the ``mss`` backend, preferring Pillow for save/scale."""
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            # sct.monitors[0] is the full virtual desktop; 1..N are displays.
            if monitor < 0 or monitor >= len(monitors):
                raise ScreenCaptureError(
                    f"Monitor {monitor} is not available; this machine has "
                    f"{len(monitors) - 1} display(s) "
                    "(use 0 for the full virtual desktop)."
                )
            shot = sct.grab(monitors[monitor])
    except ScreenCaptureError:
        raise
    except Exception as exc:  # noqa: BLE001 - backend raises many error types
        raise ScreenCaptureError(
            "Screen capture failed. Is a display available? On a headless "
            f"machine there is no screen to grab. (backend error: {exc})"
        ) from exc

    # Prefer Pillow so we can scale and honour the requested file format.
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        # No Pillow: skip scaling and let mss write a PNG itself.
        try:
            from mss import tools as mss_tools  # type: ignore

            mss_tools.to_png(shot.rgb, shot.size, output=str(path))
        except Exception as exc:  # noqa: BLE001
            raise ScreenCaptureError(
                f"Could not write screenshot to {path}: {exc}"
            ) from exc
        return path

    try:
        # mss returns raw BGRA pixels; convert to an RGB Pillow image.
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        image = _maybe_downscale(image, max_width)
        _save_image(image, path)
    except ScreenCaptureError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ScreenCaptureError(
            f"Could not write screenshot to {path}: {exc}"
        ) from exc
    return path


def _capture_with_pillow(
    path: pathlib.Path,
    monitor: int,
    max_width: int,
) -> pathlib.Path:
    """Fallback capture using Pillow's ``ImageGrab``."""
    try:
        from PIL import Image, ImageGrab  # type: ignore
    except ImportError as exc:
        raise ScreenCaptureError(_NO_BACKEND_MSG) from exc

    try:
        # all_screens grabs the whole virtual desktop when supported; it is
        # ignored on platforms that do not understand it.
        try:
            grab = ImageGrab.grab(all_screens=True)
        except TypeError:
            grab = ImageGrab.grab()

        image = grab.convert("RGB") if grab.mode != "RGB" else grab

        # Pillow has no per-monitor selection, so monitor >= 1 still returns the
        # full desktop here; monitor 0 (full desktop) is the natural match.
        image = _maybe_downscale(image, max_width)
        _save_image(image, path)
    except ScreenCaptureError:
        raise
    except Exception as exc:  # noqa: BLE001 - backend raises many error types
        raise ScreenCaptureError(
            "Screen capture failed. Is a display available? On a headless "
            f"machine there is no screen to grab. (backend error: {exc})"
        ) from exc
    return path


def _maybe_downscale(image, max_width: int):
    """Return ``image`` scaled so its width is ``<= max_width`` (if requested)."""
    if max_width and max_width > 0 and image.width > max_width:
        ratio = max_width / float(image.width)
        new_height = max(1, int(round(image.height * ratio)))
        from PIL import Image  # type: ignore

        resample = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((max_width, new_height), resample)
    return image


def _save_image(image, path: pathlib.Path) -> None:
    """Save a Pillow image, choosing the format from the file suffix."""
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        # JPEG cannot store alpha; the image is already RGB at this point.
        image.save(str(path), format="JPEG", quality=85)
    elif suffix == ".png":
        image.save(str(path), format="PNG")
    else:
        # Let Pillow infer from the extension for anything else.
        image.save(str(path))
