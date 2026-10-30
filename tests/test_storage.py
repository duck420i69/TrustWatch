"""Tests for trustwatch.storage."""

from __future__ import annotations

from datetime import datetime

from trustwatch.storage import log_event, read_events, snapshot_path


def test_log_event_and_read_round_trip(config):
    rec = log_event(config, "login", "Someone logged in", image_path=None)
    assert rec["kind"] == "login"
    assert rec["message"] == "Someone logged in"
    assert rec["image"] is None
    assert "time" in rec

    events = read_events(config)
    assert len(events) == 1
    assert events[0]["kind"] == "login"
    assert events[0]["message"] == "Someone logged in"


def test_log_event_records_image_path_and_extra(config):
    img = config.snapshot_dir / "shot.jpg"
    rec = log_event(
        config, "motion", "Motion!", image_path=img, extra={"area": 4242}
    )
    assert rec["image"] == str(img)
    assert rec["extra"] == {"area": 4242}

    events = read_events(config)
    assert events[-1]["image"] == str(img)
    assert events[-1]["extra"] == {"area": 4242}


def test_read_events_respects_limit_and_order(config):
    for i in range(5):
        log_event(config, "e", f"msg-{i}")
    events = read_events(config, limit=3)
    assert [e["message"] for e in events] == ["msg-2", "msg-3", "msg-4"]


def test_read_events_empty_when_no_log(config):
    # Fresh config: no events.log written yet.
    assert read_events(config) == []


def test_snapshot_path_under_snapshots_dir(config):
    p = snapshot_path(config, "login")
    assert p.parent == config.snapshot_dir
    assert config.snapshot_dir.is_dir()
    assert p.suffix == ".jpg"
    assert p.name.endswith("_login.jpg")


def test_snapshot_path_is_unique_across_time_and_kind(config):
    a = snapshot_path(config, "login", dt=datetime(2026, 1, 1, 9, 15, 0))
    b = snapshot_path(config, "login", dt=datetime(2026, 1, 1, 9, 15, 1))
    c = snapshot_path(config, "unlock", dt=datetime(2026, 1, 1, 9, 15, 0))
    assert a != b
    assert a != c
    assert b != c


def test_snapshot_path_sanitizes_kind(config):
    p = snapshot_path(config, "../weird/kind name!")
    # No path traversal and no spaces/special chars leak into the filename.
    assert p.parent == config.snapshot_dir
    assert "/" not in p.name.replace(".jpg", "")
    assert " " not in p.name


def test_corrupt_lines_are_skipped(config):
    log_event(config, "good", "first")
    # Append a corrupt (non-JSON) line and a blank line directly.
    with config.log_path.open("a", encoding="utf-8") as fh:
        fh.write("this is not json\n")
        fh.write("\n")
        fh.write('{"partial": \n')
    log_event(config, "good", "second")

    events = read_events(config)
    messages = [e["message"] for e in events]
    assert messages == ["first", "second"]
