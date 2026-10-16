"""Testable reminder scheduling and drink tracking, independent of Qt."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from typing import Callable

from .storage import JsonStore

DATA_VERSION = 1


def local_now() -> datetime:
    return datetime.now().astimezone()


def _parse_clock(value: str) -> time:
    if not isinstance(value, str):
        raise ValueError("active hours must use HH:MM text")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("active hours must use HH:MM text") from exc
    if parsed.tzinfo is not None or parsed.strftime("%H:%M") != value:
        raise ValueError("active hours must use HH:MM text")
    return parsed


@dataclass(frozen=True)
class Settings:
    cup_ml: int = 200
    daily_goal_ml: int = 1600
    interval_minutes: int = 90
    active_start: str = "08:00"
    active_end: str = "22:00"
    snooze_minutes: int = 10

    def __post_init__(self) -> None:
        for name in ("cup_ml", "daily_goal_ml", "interval_minutes", "snooze_minutes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.interval_minutes > 24 * 60:
            raise ValueError("interval_minutes cannot exceed one day")
        _parse_clock(self.active_start)
        _parse_clock(self.active_end)


@dataclass(frozen=True)
class WaterEntry:
    timestamp: datetime
    amount_ml: int


@dataclass(frozen=True)
class ReminderEvent:
    due_at: datetime
    emitted_at: datetime
    today_total_ml: int
    daily_goal_ml: int


class WaterReminderCore:
    """Manage local-day totals and a single, non-catching-up reminder timer."""

    def __init__(self, store: JsonStore, now_fn: Callable[[], datetime] = local_now) -> None:
        self.store = store
        self._now_fn = now_fn
        self.load_warnings: list[str] = []
        raw = store.load()
        if store.last_warning:
            self.load_warnings.append(store.last_warning)

        self.settings = self._load_settings(raw.get("settings"))
        self.entries = self._load_entries(raw.get("entries", []))
        self.paused = raw.get("paused", False) if isinstance(raw.get("paused", False), bool) else False
        if not isinstance(raw.get("paused", False), bool):
            self.load_warnings.append("The saved pause state was invalid and has been reset.")

        now = self._at()
        self._schedule_date = now.date()
        self._next_due_at: datetime | None = None if self.paused or self._goal_reached(now) else self._after_interval(now)

    @property
    def next_due_at(self) -> datetime | None:
        return self._next_due_at

    def today_total_ml(self, at: datetime | None = None) -> int:
        current = self._at(at)
        return sum(entry.amount_ml for entry in self.entries if entry.timestamp.date() == current.date())

    def record_water(self, amount_ml: int, at: datetime | None = None) -> int:
        if isinstance(amount_ml, bool) or not isinstance(amount_ml, int) or amount_ml < 1:
            raise ValueError("amount_ml must be a positive integer")
        current = self._at(at)
        self.entries.append(WaterEntry(timestamp=current, amount_ml=amount_ml))
        self._schedule_date = current.date()
        if self.paused or self._goal_reached(current):
            self._next_due_at = None
        else:
            self._next_due_at = self._after_interval(current)
        self._save()
        return self.today_total_ml(current)

    def update_settings(self, settings: Settings, at: datetime | None = None) -> None:
        if not isinstance(settings, Settings):
            raise TypeError("settings must be a Settings instance")
        current = self._at(at)
        self.settings = settings
        self._schedule_date = current.date()
        if self.paused or self._goal_reached(current):
            self._next_due_at = None
        else:
            self._next_due_at = self._after_interval(current)
        self._save()

    def set_paused(self, paused: bool, at: datetime | None = None) -> None:
        if not isinstance(paused, bool):
            raise TypeError("paused must be a bool")
        current = self._at(at)
        self.paused = paused
        self._schedule_date = current.date()
        if paused or self._goal_reached(current):
            self._next_due_at = None
        else:
            self._next_due_at = self._after_interval(current)
        self._save()

    def snooze(self, at: datetime | None = None) -> datetime | None:
        current = self._at(at)
        if self.paused or self._goal_reached(current):
            return None
        self._schedule_date = current.date()
        self._next_due_at = current + timedelta(minutes=self.settings.snooze_minutes)
        return self._next_due_at

    def tick(self, at: datetime | None = None) -> ReminderEvent | None:
        current = self._at(at)
        if self.paused:
            return None

        # A new local calendar day starts a fresh interval; missed time is never replayed.
        if current.date() != self._schedule_date:
            self._schedule_date = current.date()
            if self._goal_reached(current):
                self._next_due_at = None
            elif self._next_due_at is None:
                self._next_due_at = self._after_interval(current)

        if self._goal_reached(current):
            self._next_due_at = None
            return None
        if self._next_due_at is None:
            self._next_due_at = self._after_interval(current)
            return None
        if current < self._next_due_at:
            return None
        if not self._is_active(current):
            self._next_due_at = self._next_active_start(current)
            return None

        due_at = self._next_due_at
        total = self.today_total_ml(current)
        self._next_due_at = self._after_interval(current)
        return ReminderEvent(
            due_at=due_at,
            emitted_at=current,
            today_total_ml=total,
            daily_goal_ml=self.settings.daily_goal_ml,
        )

    def _load_settings(self, value: object) -> Settings:
        if value is None:
            return Settings()
        if not isinstance(value, dict):
            self.load_warnings.append("Saved settings were invalid and defaults were loaded.")
            return Settings()
        try:
            allowed = Settings.__dataclass_fields__.keys()
            return Settings(**{key: value[key] for key in allowed if key in value})
        except (TypeError, ValueError):
            self.load_warnings.append("Saved settings were invalid and defaults were loaded.")
            return Settings()

    def _load_entries(self, value: object) -> list[WaterEntry]:
        if not isinstance(value, list):
            self.load_warnings.append("Saved drink history was invalid and has been skipped.")
            return []
        entries: list[WaterEntry] = []
        skipped = False
        for item in value:
            try:
                if not isinstance(item, dict):
                    raise ValueError
                timestamp = datetime.fromisoformat(item["timestamp"])
                amount = item["amount_ml"]
                if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
                    raise ValueError
                entries.append(WaterEntry(timestamp=timestamp, amount_ml=amount))
            except (KeyError, TypeError, ValueError):
                skipped = True
        if skipped:
            self.load_warnings.append("Some invalid drink history rows were skipped.")
        return entries

    def _at(self, value: datetime | None = None) -> datetime:
        current = self._now_fn() if value is None else value
        if not isinstance(current, datetime):
            raise TypeError("current time must be a datetime")
        return current.astimezone() if current.tzinfo is None else current

    def _after_interval(self, at: datetime) -> datetime:
        return at + timedelta(minutes=self.settings.interval_minutes)

    def _goal_reached(self, at: datetime) -> bool:
        return self.today_total_ml(at) >= self.settings.daily_goal_ml

    def _is_active(self, at: datetime) -> bool:
        start = _parse_clock(self.settings.active_start)
        end = _parse_clock(self.settings.active_end)
        current = at.timetz().replace(tzinfo=None)
        if start == end:
            return True
        if start < end:
            return start <= current < end
        return current >= start or current < end

    def _next_active_start(self, at: datetime) -> datetime:
        start = _parse_clock(self.settings.active_start)
        end = _parse_clock(self.settings.active_end)
        current = at.timetz().replace(tzinfo=None)
        if start < end:
            target_day = at.date() if current < start else at.date() + timedelta(days=1)
        else:
            target_day = at.date() if end <= current < start else at.date() + timedelta(days=1)
        return datetime.combine(target_day, start).replace(tzinfo=at.tzinfo)

    def _save(self) -> None:
        self.store.save(
            {
                "version": DATA_VERSION,
                "settings": asdict(self.settings),
                "entries": [
                    {"timestamp": entry.timestamp.isoformat(), "amount_ml": entry.amount_ml}
                    for entry in self.entries
                ],
                "paused": self.paused,
            }
        )
