"""Detect that *someone is interacting* with this laptop and record *what app*
is in use plus session-level signals — never the content of what is typed.

This is the owner observing their own device: it answers "is a person at the
keyboard right now, and what are they doing?" without ever recording which keys
or buttons were pressed. Concretely this module only ever reports:

* how long since the last input event (a single number read from the OS idle
  timer — not which keys/buttons, not where the mouse went),
* the foreground application name and window title,
* the set of currently-connected USB devices.

It deliberately does **not** import or use any keyboard/mouse hooking or
listening library (no ``pynput``, no ``keyboard``, no low-level input hooks) and
never captures keystrokes, key identities, typed text, clipboard contents, or
mouse coordinates/click targets. That is out of scope by design.

All platform tooling is invoked lazily and defensively: anything unsupported on
the current OS/session, or any failure, yields ``None`` (or an empty set for the
USB listing) rather than raising out of the function.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

# Short, uniform timeout for every external command so a hung tool can never
# wedge the monitor loop.
_CMD_TIMEOUT = 5


def _run(args: list[str]) -> Optional[str]:
    """Run a command and return its stdout as text, or None on any problem.

    Args:
        args: The command and its arguments.

    Returns:
        The command's standard output, or None if the command is missing,
        times out, exits non-zero, or raises for any other reason.
    """
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT,
        )
    except Exception:
        # FileNotFoundError (tool absent), TimeoutExpired, permission errors,
        # decode errors — all degrade to "unavailable".
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


# --------------------------------------------------------------------------- #
# Idle time
# --------------------------------------------------------------------------- #

def _idle_windows() -> Optional[float]:
    """Seconds since last input on Windows via GetLastInputInfo/GetTickCount."""
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("dwTime", wintypes.DWORD),
            ]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        # GetTickCount wraps roughly every 49.7 days; mask to 32 bits so the
        # subtraction stays correct across a wrap.
        now = ctypes.windll.kernel32.GetTickCount()
        elapsed_ms = (now - info.dwTime) & 0xFFFFFFFF
        return elapsed_ms / 1000.0
    except Exception:
        return None


def _idle_macos() -> Optional[float]:
    """Seconds since last input on macOS.

    Prefers Quartz if importable, otherwise parses the HIDIdleTime property
    (nanoseconds) out of ``ioreg -c IOHIDSystem``.
    """
    # Preferred: Quartz, if PyObjC happens to be installed.
    try:
        import Quartz  # type: ignore

        seconds = Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateHIDSystemState,
            Quartz.kCGAnyInputEventType,
        )
        return float(seconds)
    except Exception:
        pass

    # Dependency-free fallback: ioreg reports HIDIdleTime in nanoseconds.
    out = _run(["ioreg", "-c", "IOHIDSystem"])
    if not out:
        return None
    for line in out.splitlines():
        if "HIDIdleTime" in line:
            # Line looks like:  "HIDIdleTime" = 12345678900
            try:
                raw = line.split("=", 1)[1].strip()
                nanos = int(raw)
            except (IndexError, ValueError):
                return None
            return nanos / 1_000_000_000.0
    return None


def _idle_linux() -> Optional[float]:
    """Seconds since last input on Linux (X11 only).

    Tries ``xprintidle`` (milliseconds) first, then the X screensaver
    extension via python-xlib. Wayland cannot generally report this, so it
    returns None.
    """
    # xprintidle prints idle time in milliseconds.
    out = _run(["xprintidle"])
    if out:
        try:
            return int(out.strip()) / 1000.0
        except ValueError:
            pass

    # Fallback: X11 screensaver extension through python-xlib, if present.
    try:
        from Xlib import display  # type: ignore

        dpy = display.Display()
        try:
            info = dpy.screen().root.screensaver_query_info()
            # idle is reported in milliseconds.
            return float(info.idle) / 1000.0
        finally:
            dpy.close()
    except Exception:
        return None


def seconds_since_last_input() -> Optional[float]:
    """Return seconds since the last keyboard/mouse input (system idle time),
    or None if this OS/session can't report it.

    Used to detect that a person just interacted (idle time near zero). This
    reads the OS idle timer only; it does NOT record which keys or buttons were
    pressed.

    Returns:
        The number of seconds since the last input event, or None when the
        current platform/session cannot provide it (e.g. Wayland, or a missing
        helper).
    """
    try:
        if sys.platform.startswith("win"):
            return _idle_windows()
        if sys.platform == "darwin":
            return _idle_macos()
        if sys.platform.startswith("linux"):
            return _idle_linux()
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------- #
# Active window
# --------------------------------------------------------------------------- #

def _active_window_windows() -> Optional[dict]:
    """Foreground window app/title on Windows via ctypes (psutil optional)."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""

        app = ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            # psutil is optional: use it for a clean process name if present,
            # otherwise just skip the app name.
            try:
                import psutil  # type: ignore

                app = psutil.Process(pid.value).name()
            except Exception:
                app = ""

        return {"app": app, "title": title}
    except Exception:
        return None


def _active_window_macos() -> Optional[dict]:
    """Foreground app name (and best-effort window title) on macOS via osascript."""
    app_script = (
        'tell application "System Events" to '
        "get name of first application process whose frontmost is true"
    )
    app_out = _run(["osascript", "-e", app_script])
    if app_out is None:
        return None
    app = app_out.strip()
    if not app:
        return None

    # Window title is best-effort: some apps don't expose it and the AppleEvent
    # may fail, which is fine — we just return an empty title then.
    title = ""
    title_script = (
        'tell application "System Events" to tell '
        "(first application process whose frontmost is true) to "
        "get name of front window"
    )
    title_out = _run(["osascript", "-e", title_script])
    if title_out is not None:
        title = title_out.strip()

    return {"app": app, "title": title}


def _active_window_linux() -> Optional[dict]:
    """Foreground window app/title on Linux (X11) via xdotool, else xprop."""
    # Preferred: xdotool gives both the window name and the owning class.
    title = _run(["xdotool", "getactivewindow", "getwindowname"])
    if title is not None:
        title = title.strip()
        app = ""
        cls = _run(["xdotool", "getactivewindow", "getwindowclassname"])
        if cls:
            app = cls.strip()
        return {"app": app, "title": title}

    # Fallback: xprop on the active window id.
    root = _run(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
    if not root:
        return None
    try:
        win_id = root.split()[-1].strip()
        int(win_id, 16)  # validate it parses as a hex window id
    except (IndexError, ValueError):
        return None

    props = _run(["xprop", "-id", win_id, "WM_NAME", "WM_CLASS"])
    if props is None:
        return None

    title = ""
    app = ""
    for line in props.splitlines():
        if line.startswith("WM_NAME") and '"' in line:
            title = line.split('"', 1)[1].rsplit('"', 1)[0]
        elif line.startswith("WM_CLASS") and '"' in line:
            # WM_CLASS is usually "instance", "class" — take the last entry.
            parts = [p for p in line.split('"') if p.strip() and "=" not in p]
            if parts:
                app = parts[-1]
    return {"app": app, "title": title}


def active_window() -> Optional[dict]:
    """Return {"app": <process/app name>, "title": <window title>} for the
    foreground window, or None if unavailable.

    This is what the person is doing (which application has focus), not what
    they type into it.

    Returns:
        A dict with "app" and "title" keys, or None when the foreground window
        cannot be determined on the current platform/session.
    """
    try:
        if sys.platform.startswith("win"):
            return _active_window_windows()
        if sys.platform == "darwin":
            return _active_window_macos()
        if sys.platform.startswith("linux"):
            return _active_window_linux()
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------- #
# USB devices
# --------------------------------------------------------------------------- #

def _usb_linux() -> set[str]:
    """Connected USB identifiers on Linux from sysfs, falling back to lsusb."""
    devices: set[str] = set()

    # Preferred: sysfs, which needs no external tool. Each device directory has
    # idVendor/idProduct files; a serial is included when exposed for stability.
    try:
        from pathlib import Path

        base = Path("/sys/bus/usb/devices")
        if base.is_dir():
            for entry in base.iterdir():
                vendor = entry / "idVendor"
                product = entry / "idProduct"
                if not (vendor.is_file() and product.is_file()):
                    continue
                try:
                    vid = vendor.read_text().strip()
                    pid = product.read_text().strip()
                except OSError:
                    continue
                ident = f"{vid}:{pid}"
                serial = entry / "serial"
                if serial.is_file():
                    try:
                        s = serial.read_text().strip()
                        if s:
                            ident = f"{ident}:{s}"
                    except OSError:
                        pass
                devices.add(ident)
    except Exception:
        devices = set()

    if devices:
        return devices

    # Fallback: parse lsusb lines like
    # "Bus 001 Device 002: ID 1d6b:0002 Linux Foundation 2.0 root hub".
    out = _run(["lsusb"])
    if out:
        for line in out.splitlines():
            line = line.strip()
            if " ID " in line:
                try:
                    ident = line.split(" ID ", 1)[1].split()[0]
                    if ident:
                        devices.add(ident)
                except IndexError:
                    continue
    return devices


def _usb_macos() -> set[str]:
    """Connected USB identifiers on macOS from system_profiler."""
    out = _run(["system_profiler", "SPUSBDataType"])
    if not out:
        return set()

    devices: set[str] = set()
    for line in out.splitlines():
        stripped = line.strip()
        # Device entries are header lines ending with ':' that aren't the known
        # property keys. Combine with any Serial Number we see to stay stable.
        if stripped.endswith(":") and not stripped.startswith(
            (
                "Product ID", "Vendor ID", "Version", "Serial Number",
                "Speed", "Manufacturer", "Location ID", "Current",
                "Capacity", "USB", "Media", "BSD Name", "Removable Media",
                "Detachable Drive", "Partition Map Type", "S.M.A.R.T.",
                "Extra Operating Current", "Built-In", "Sleep Current",
            )
        ):
            name = stripped[:-1].strip()
            if name:
                devices.add(name)
        elif stripped.startswith("Serial Number:"):
            serial = stripped.split(":", 1)[1].strip()
            if serial:
                devices.add(f"serial:{serial}")
    return devices


def _usb_windows() -> set[str]:
    """Connected USB identifiers on Windows via PowerShell, falling back to wmic."""
    devices: set[str] = set()

    # Preferred: PowerShell PnP query (wmic is deprecated on recent Windows).
    ps_out = _run([
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-PnpDevice -Class USB -PresentOnly | "
        "Select-Object -ExpandProperty DeviceID",
    ])
    if ps_out:
        for line in ps_out.splitlines():
            ident = line.strip()
            if ident:
                devices.add(ident)
        if devices:
            return devices

    # Fallback: wmic, where still present.
    wmic_out = _run(["wmic", "path", "Win32_USBHub", "get", "DeviceID"])
    if wmic_out:
        for line in wmic_out.splitlines():
            ident = line.strip()
            if not ident or ident.lower() == "deviceid":
                continue
            devices.add(ident)
    return devices


def list_usb_devices() -> set[str]:
    """Return a set of currently-connected USB device identifiers (stable
    strings). Empty set if it can't be determined.

    The caller diffs successive calls to detect a device being plugged in or
    removed (a tamper signal).

    Returns:
        A set of identifier strings for the connected USB devices, or an empty
        set when the listing is unavailable on the current platform/session.
    """
    try:
        if sys.platform.startswith("win"):
            return _usb_windows()
        if sys.platform == "darwin":
            return _usb_macos()
        if sys.platform.startswith("linux"):
            return _usb_linux()
    except Exception:
        return set()
    return set()
