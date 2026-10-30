"""Tests for trustwatch.activity (written against the agreed API).

The module may not exist yet while it is being developed in parallel; in that
case these tests skip rather than fail.

On this headless Linux container the underlying tools (idle-time probes, window
managers, usb listing utilities) are typically absent, so the functions must
degrade gracefully: return None / None / an (possibly empty) set, never raise.
"""

from __future__ import annotations

import pytest

activity = pytest.importorskip(
    "trustwatch.activity",
    reason="trustwatch.activity not implemented yet",
)


def test_public_api_is_callable():
    assert callable(activity.seconds_since_last_input)
    assert callable(activity.active_window)
    assert callable(activity.list_usb_devices)


def test_seconds_since_last_input_returns_optional_float():
    result = activity.seconds_since_last_input()
    assert result is None or isinstance(result, (int, float))


def test_active_window_returns_optional_dict():
    result = activity.active_window()
    assert result is None or isinstance(result, dict)


def test_list_usb_devices_returns_a_set():
    result = activity.list_usb_devices()
    assert isinstance(result, set)
    # Every member (if any) should be a string identifier.
    assert all(isinstance(x, str) for x in result)


def test_functions_never_raise():
    # Call each one; the contract is "degrade gracefully", not "crash".
    activity.seconds_since_last_input()
    activity.active_window()
    activity.list_usb_devices()
