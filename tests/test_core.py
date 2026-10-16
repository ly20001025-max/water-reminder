from datetime import datetime, timedelta, timezone
import json

import pytest

from water_reminder import JsonStore, Settings, WaterReminderCore


TZ = timezone(timedelta(hours=8))


def dt(day: int, hour: int, minute: int = 0, month: int = 1) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


def make_core(tmp_path, at: datetime, settings: Settings | None = None) -> WaterReminderCore:
    store = JsonStore(tmp_path / "water.json")
    core = WaterReminderCore(store, now_fn=lambda: at)
    if settings is not None:
        core.update_settings(settings, at)
    return core


def test_defaults_and_persisted_drink_history(tmp_path):
    now = dt(16, 9)
    core = make_core(tmp_path, now)

    assert core.settings == Settings()
    assert core.record_water(200, now) == 200
    assert core.record_water(100, now + timedelta(minutes=2)) == 300

    restored = WaterReminderCore(JsonStore(tmp_path / "water.json"), now_fn=lambda: now)
    assert restored.today_total_ml(now) == 300
    assert len(restored.entries) == 2


def test_totals_are_scoped_to_local_calendar_day(tmp_path):
    before_midnight = dt(16, 23, 58)
    core = make_core(tmp_path, before_midnight)
    core.record_water(200, before_midnight)

    after_midnight = dt(17, 0, 2)
    assert core.today_total_ml(after_midnight) == 0
    assert core.record_water(100, after_midnight) == 100
    assert core.today_total_ml(before_midnight) == 200


def test_pause_invalidates_due_callback_and_resume_starts_fresh_interval(tmp_path):
    start = dt(16, 9)
    core = make_core(tmp_path, start, Settings(active_start="08:00", active_end="22:00"))
    first_due = start + timedelta(minutes=90)

    core.set_paused(True, start + timedelta(minutes=30))
    assert core.tick(first_due) is None
    assert core.next_due_at is None

    resumed = start + timedelta(hours=2)
    core.set_paused(False, resumed)
    assert core.tick(resumed + timedelta(minutes=30)) is None
    assert core.next_due_at == resumed + timedelta(minutes=90)
    assert core.tick(resumed + timedelta(minutes=90)) is not None


def test_snooze_replaces_the_old_due_time(tmp_path):
    start = dt(16, 9)
    core = make_core(tmp_path, start)
    old_due = core.next_due_at
    snooze_until = core.snooze(old_due)

    assert snooze_until == old_due + timedelta(minutes=10)
    assert core.tick(old_due) is None
    event = core.tick(snooze_until)
    assert event is not None
    assert event.due_at == snooze_until


def test_reminder_window_can_cross_midnight(tmp_path):
    start = dt(16, 23)
    settings = Settings(interval_minutes=90, active_start="22:00", active_end="06:00")
    core = make_core(tmp_path, start, settings)

    event = core.tick(dt(17, 0, 30))
    assert event is not None
    assert event.emitted_at == dt(17, 0, 30)


def test_inactive_due_moves_to_next_window_across_midnight(tmp_path):
    start = dt(16, 21)
    settings = Settings(interval_minutes=90, active_start="08:00", active_end="22:00")
    core = make_core(tmp_path, start, settings)

    assert core.tick(dt(16, 22, 30)) is None
    assert core.next_due_at == dt(17, 8)
    assert core.tick(dt(17, 8)) is not None


def test_goal_stops_reminders_until_a_new_local_day(tmp_path):
    start = dt(16, 9)
    settings = Settings(daily_goal_ml=300)
    core = make_core(tmp_path, start, settings)
    core.record_water(200, start)
    core.record_water(100, start + timedelta(minutes=1))

    assert core.tick(start + timedelta(hours=4)) is None
    assert core.next_due_at is None
    next_day = dt(17, 8)
    assert core.tick(next_day) is None
    assert core.next_due_at == next_day + timedelta(minutes=90)
    assert core.today_total_ml(next_day) == 0


def test_overdue_scheduler_emits_one_event_then_resets_from_now(tmp_path):
    start = dt(16, 9)
    core = make_core(tmp_path, start)
    resumed = start + timedelta(hours=5)

    event = core.tick(resumed)
    assert event is not None
    assert event.due_at == start + timedelta(minutes=90)
    assert event.emitted_at == resumed
    assert core.tick(resumed) is None
    assert core.next_due_at == resumed + timedelta(minutes=90)


def test_missing_and_corrupt_json_start_with_defaults_and_preserve_corrupt_file(tmp_path):
    path = tmp_path / "water.json"
    store = JsonStore(path)
    assert store.load() == {}
    path.write_text("{ broken", encoding="utf-8")

    core = WaterReminderCore(store, now_fn=lambda: dt(16, 9))
    assert core.settings == Settings()
    assert core.load_warnings
    assert not path.exists()
    assert list(tmp_path.glob("water.corrupt-*.json"))


def test_atomic_store_round_trip_and_invalid_rows_are_reported(tmp_path):
    path = tmp_path / "nested" / "water.json"
    store = JsonStore(path)
    store.save({"version": 1, "settings": {}, "entries": [{"timestamp": "bad", "amount_ml": 0}]})
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1

    core = WaterReminderCore(store, now_fn=lambda: dt(16, 9))
    assert core.entries == []
    assert core.load_warnings
    assert not list(path.parent.glob("*.tmp"))


def test_settings_reject_non_positive_or_malformed_values():
    with pytest.raises(ValueError):
        Settings(cup_ml=0)
    with pytest.raises(ValueError):
        Settings(active_start="8am")
