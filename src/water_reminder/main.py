from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from water_reminder.app import WaterReminderApp
from water_reminder.storage import JsonStore
from water_reminder.core import WaterReminderCore


def data_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "WaterReminder" / "water.json"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Water Reminder")
    app.setOrganizationName("WaterReminder")
    app.setQuitOnLastWindowClosed(False)

    store = JsonStore(data_path())
    core = WaterReminderCore(store)
    warnings = [*core.load_warnings]
    window = WaterReminderApp(app, core, " ".join(warnings) if warnings else None)
    window.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
