from __future__ import annotations

from datetime import datetime
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QBrush, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QSystemTrayIcon,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from water_reminder.core import Settings, WaterReminderCore
from water_reminder.storage import JsonStore


class TrayIconPainter:
    @staticmethod
    def create() -> QIcon:
        from PySide6.QtGui import QPixmap

        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#177E78"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QBrush(QColor("#D9F1EC")))
        cup = QPolygonF([QPointF(18, 12), QPointF(46, 12), QPointF(42, 52), QPointF(22, 52)])
        painter.drawPolygon(cup)
        painter.setPen(QPen(QColor("#299E91"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(23, 34, 41, 34)
        painter.end()
        return QIcon(pixmap)


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("喝水提醒设置")
        self.setModal(True)
        self.setMinimumWidth(310)

        self.cup = QSpinBox()
        self.cup.setRange(50, 1000)
        self.cup.setSingleStep(50)
        self.cup.setSuffix(" ml")
        self.cup.setValue(settings.cup_ml)

        self.goal = QSpinBox()
        self.goal.setRange(200, 10000)
        self.goal.setSingleStep(200)
        self.goal.setSuffix(" ml")
        self.goal.setValue(settings.daily_goal_ml)

        self.interval = QSpinBox()
        self.interval.setRange(15, 240)
        self.interval.setSingleStep(15)
        self.interval.setSuffix(" 分钟")
        self.interval.setValue(settings.interval_minutes)

        self.active_start = QTimeEdit()
        self.active_start.setDisplayFormat("HH:mm")
        self.active_start.setTime(self._time(settings.active_start))

        self.active_end = QTimeEdit()
        self.active_end.setDisplayFormat("HH:mm")
        self.active_end.setTime(self._time(settings.active_end))
        self.snooze = QSpinBox()
        self.snooze.setRange(5, 60)
        self.snooze.setSingleStep(5)
        self.snooze.setSuffix(" 分钟")
        self.snooze.setValue(settings.snooze_minutes)

        form = QFormLayout()
        form.addRow("一杯容量", self.cup)
        form.addRow("每日目标", self.goal)
        form.addRow("提醒间隔", self.interval)
        form.addRow("提醒开始", self.active_start)
        form.addRow("提醒结束", self.active_end)
        form.addRow("稍后提醒", self.snooze)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @staticmethod
    def _time(value: str):
        from PySide6.QtCore import QTime

        parsed = QTime.fromString(value, "HH:mm")
        return parsed if parsed.isValid() else QTime(8, 0)

    def settings(self) -> Settings:
        return Settings(
            cup_ml=self.cup.value(),
            daily_goal_ml=self.goal.value(),
            interval_minutes=self.interval.value(),
            active_start=self.active_start.time().toString("HH:mm"),
            active_end=self.active_end.time().toString("HH:mm"),
            snooze_minutes=self.snooze.value(),
        )


class CupIndicator(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(42, 48)
        self.ratio = 0.0

    def set_ratio(self, ratio: float) -> None:
        self.ratio = min(1.0, max(0.0, ratio))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cup = QPainterPath()
        cup.moveTo(9, 5)
        cup.lineTo(33, 5)
        cup.lineTo(30, 42)
        cup.lineTo(12, 42)
        cup.closeSubpath()
        painter.save()
        painter.setClipPath(cup)
        fill_height = 31 * self.ratio
        if fill_height:
            painter.fillRect(QRectF(8, 42 - fill_height, 26, fill_height), QColor("#6DC7B7"))
        painter.restore()
        painter.setPen(QPen(QColor("#177E78"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(cup)


class FloatingCup(QWidget):
    def __init__(self, app: "WaterReminderApp"):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.app = app
        self.setFixedSize(286, 254)
        self.setWindowTitle("喝水提醒")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget#surface { background: #FCFEFD; border: 1px solid #D7E6E1; border-radius: 8px; }
            QLabel { color: #183B3A; }
            QLabel#title { font-size: 14px; font-weight: 700; }
            QLabel#status { color: #56716D; font-size: 12px; }
            QLabel#amount { font-size: 22px; font-weight: 700; }
            QPushButton { min-height: 34px; border: 1px solid #D7E6E1; border-radius: 8px; background: #F5FAF8; color: #244A46; font-weight: 600; padding: 0 10px; }
            QPushButton:hover { background: #E7F5F1; }
            QPushButton#primary { background: #177E78; color: white; border-color: #177E78; }
            QPushButton#primary:hover { background: #116C67; }
            QPushButton#quiet { border: none; background: transparent; min-width: 28px; padding: 0; color: #718783; }
            QProgressBar { height: 9px; border: none; border-radius: 4px; background: #E8F0ED; }
            QProgressBar::chunk { border-radius: 4px; background: #35A994; }
        """)

        surface = QWidget()
        surface.setObjectName("surface")
        header = QHBoxLayout()
        title = QLabel("今日饮水")
        title.setObjectName("title")
        self.reminder = QLabel("")
        self.reminder.setObjectName("status")
        self.reminder.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        close = QPushButton("×")
        close.setObjectName("quiet")
        close.setToolTip("隐藏小杯")
        close.clicked.connect(self.hide)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.reminder)
        header.addWidget(close)

        self.amount = QLabel("0 / 1600 ml")
        self.amount.setObjectName("amount")
        self.cup_glyph = CupIndicator()
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        summary = QVBoxLayout()
        summary.setSpacing(7)
        summary.addWidget(self.amount)
        summary.addWidget(self.progress)
        amount_row = QHBoxLayout()
        amount_row.setSpacing(12)
        amount_row.addWidget(self.cup_glyph)
        amount_row.addLayout(summary, 1)

        self.next_due = QLabel("下次提醒 --:--")
        self.next_due.setObjectName("status")

        primary_row = QHBoxLayout()
        add_cup = QPushButton("喝了一杯 200ml")
        add_cup.setObjectName("primary")
        add_cup.clicked.connect(self.app.record_cup)
        custom = QPushButton("自定义")
        custom.clicked.connect(self.app.record_custom)
        primary_row.addWidget(add_cup, 2)
        primary_row.addWidget(custom, 1)

        footer = QHBoxLayout()
        snooze = QPushButton("稍后提醒")
        snooze.clicked.connect(self.app.snooze)
        pause = QPushButton("暂停")
        pause.clicked.connect(self.app.toggle_pause)
        footer.addWidget(snooze)
        footer.addWidget(pause)
        self.pause_button = pause

        inner = QVBoxLayout(surface)
        inner.setContentsMargins(16, 13, 16, 15)
        inner.setSpacing(12)
        inner.addLayout(header)
        inner.addLayout(amount_row)
        inner.addWidget(self.next_due)
        inner.addLayout(primary_row)
        inner.addLayout(footer)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(surface)

    def refresh(self, total: int, goal: int, due_at: datetime | None, paused: bool, reminder: bool = False) -> None:
        self.amount.setText(f"{total} / {goal} ml")
        ratio = min(1.0, total / max(goal, 1))
        self.progress.setValue(round(ratio * 100))
        self.cup_glyph.set_ratio(ratio)
        self.pause_button.setText("恢复" if paused else "暂停")
        if due_at is None:
            next_text = "今日目标已完成" if total >= goal else "非提醒时段"
        else:
            next_text = f"下次提醒 {due_at.astimezone().strftime('%H:%M')}"
        if paused:
            next_text = "提醒已暂停"
        self.next_due.setText(next_text)
        self.reminder.setText("该喝水了" if reminder else "")
        if reminder:
            self.show()
            self.raise_()

    def place_at_corner(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 22, area.bottom() - self.height() - 22)

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


class WaterReminderApp:
    def __init__(self, qapp: QApplication, core: WaterReminderCore, storage_warning: str | None = None):
        self.qapp = qapp
        self.core = core
        self.storage_warning = storage_warning
        self.icon = TrayIconPainter.create()
        self.cup = FloatingCup(self)
        self.tray = QSystemTrayIcon(self.icon, qapp)
        self.tray.setToolTip("喝水提醒")
        self._build_menu()

        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.snooze_action: QAction

    def _build_menu(self) -> None:
        menu = QMenu()
        show = QAction("显示小杯", menu)
        show.triggered.connect(self.show_cup)
        hide = QAction("隐藏小杯", menu)
        hide.triggered.connect(self.cup.hide)
        menu.addAction(show)
        menu.addAction(hide)
        menu.addSeparator()

        add = QAction(f"记录一杯（{self.core.settings.cup_ml}ml）", menu)
        add.triggered.connect(self.record_cup)
        menu.addAction(add)
        self.add_action = add

        self.pause_action = QAction("暂停提醒", menu)
        self.pause_action.triggered.connect(self.toggle_pause)
        menu.addAction(self.pause_action)
        self.snooze_action = QAction(f"稍后提醒（{self.core.settings.snooze_minutes}分钟）", menu)
        self.snooze_action.triggered.connect(self.snooze)
        menu.addAction(self.snooze_action)
        menu.addSeparator()

        settings = QAction("设置...", menu)
        settings.triggered.connect(self.open_settings)
        menu.addAction(settings)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)

    def start(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.cup.place_at_corner()
        self.cup.show()
        self.tick()
        self.timer.start()
        if self.storage_warning:
            QTimer.singleShot(800, lambda: self.tray.showMessage("饮水记录", self.storage_warning, QSystemTrayIcon.MessageIcon.Warning, 5000))

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.cup.setVisible(not self.cup.isVisible())

    def _refresh(self, reminder: bool = False) -> None:
        total = self.core.today_total_ml()
        settings = self.core.settings
        self.cup.refresh(total, settings.daily_goal_ml, self.core.next_due_at, self.core.paused, reminder)
        self.add_action.setText(f"记录一杯（{settings.cup_ml}ml）")
        self.pause_action.setText("恢复提醒" if self.core.paused else "暂停提醒")
        self.tray.setToolTip(f"喝水提醒 · 今日 {total}/{settings.daily_goal_ml}ml")

    def tick(self) -> None:
        event = self.core.tick()
        self._refresh(reminder=event is not None)
        if event is not None:
            self.tray.showMessage("喝水提醒", "起来喝几口水吧。记录只会在你手动确认后增加。", self.tray.MessageIcon.Information, 5000)

    def show_cup(self) -> None:
        self.cup.place_at_corner()
        self.cup.show()
        self.cup.raise_()
        self._refresh()

    def record_cup(self) -> None:
        try:
            self.core.record_water(self.core.settings.cup_ml)
        except Exception as exc:
            QMessageBox.warning(self.cup, "未能保存", str(exc))
        self._refresh()

    def record_custom(self) -> None:
        amount, accepted = QInputDialog.getInt(self.cup, "记录饮水", "本次饮水量（ml）", self.core.settings.cup_ml, 1, 3000, 50)
        if accepted:
            try:
                self.core.record_water(amount)
            except Exception as exc:
                QMessageBox.warning(self.cup, "未能保存", str(exc))
            self._refresh()

    def snooze(self) -> None:
        self.core.snooze()
        self._refresh()

    def toggle_pause(self) -> None:
        self.core.set_paused(not self.core.paused)
        self._refresh()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.core.settings, self.cup)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.core.update_settings(dialog.settings())
            self.snooze_action.setText(f"稍后提醒（{self.core.settings.snooze_minutes}分钟）")
            self._refresh()

    def quit(self) -> None:
        self.timer.stop()
        self.tray.hide()
        self.qapp.quit()
