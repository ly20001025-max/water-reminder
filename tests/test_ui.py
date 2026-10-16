from water_reminder.app import SettingsDialog, WaterReminderApp
from water_reminder.core import Settings, WaterReminderCore
from water_reminder.storage import JsonStore


def test_settings_dialog_returns_all_configurable_values(qtbot):
    dialog = SettingsDialog(Settings())
    qtbot.addWidget(dialog)
    dialog.cup.setValue(250)
    dialog.goal.setValue(1800)
    dialog.interval.setValue(75)
    dialog.active_start.setTime(dialog.active_start.time().fromString("07:30", "HH:mm"))
    dialog.active_end.setTime(dialog.active_end.time().fromString("21:30", "HH:mm"))
    dialog.snooze.setValue(15)

    assert dialog.settings() == Settings(
        cup_ml=250,
        daily_goal_ml=1800,
        interval_minutes=75,
        active_start="07:30",
        active_end="21:30",
        snooze_minutes=15,
    )


def test_desktop_app_records_confirmed_drink_and_close_hides_cup(qtbot, qapp, tmp_path):
    core = WaterReminderCore(JsonStore(tmp_path / "water.json"))
    desktop = WaterReminderApp(qapp, core)
    qtbot.addWidget(desktop.cup)
    desktop._refresh()

    desktop.record_cup()

    assert core.today_total_ml() == 200
    assert desktop.cup.amount.text() == "200 / 1600 ml"
    assert desktop.cup.cup_glyph.ratio == 0.125

    desktop.cup.show()
    desktop.cup.close()
    assert not desktop.cup.isVisible()
