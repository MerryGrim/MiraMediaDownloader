"""Small native date-range dialog; state belongs only to its caller."""

from __future__ import annotations

from datetime import date, datetime, timezone

from PySide6.QtCore import QDate, QEvent, QLocale, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget, QCheckBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QRadioButton, QStyle, QStyleOptionButton, QVBoxLayout, QWidget,
)

from .localization import calendar_locale_name, tr, translate_widget_tree
from .window_chrome import install_chrome


def _bound(value: str) -> date | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        raise ValueError("Дата периода должна иметь формат ГГГГ-ММ-ДД.") from None


def _display(value: date) -> str:
    return f"{value.day:02d}.{value.month:02d}.{value.year:04d}"


def range_label(date_from: str, date_to: str) -> str:
    """Return a short Russian label for the engine's inclusive ISO bounds."""
    first, last = _bound(date_from), _bound(date_to)
    if first is not None and last is not None:
        return f"{_display(first)} — {_display(last)}"
    if first is not None:
        return tr("С {date}", date=_display(first))
    if last is not None:
        return tr("По {date}", date=_display(last))
    return tr("Все даты")


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


class _BoundCheckBox(QCheckBox):
    """Keep the native control while restoring a tick over themed indicators."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.isChecked():
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        indicator = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = (self.palette().color(QPalette.ColorRole.HighlightedText) if self.isEnabled() else
               self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))
        painter.setPen(QPen(ink, 1.8))
        x, y = indicator.left(), indicator.top()
        painter.drawLine(x + 4, y + 8, x + 7, y + 11)
        painter.drawLine(x + 7, y + 11, x + 12, y + 5)
        painter.end()


class _CalendarPopup(QFrame):
    """A native day grid with comfortable month/year buttons and no spinners."""

    def __init__(self, picker):
        super().__init__(picker, Qt.WindowType.Popup)
        self.setObjectName("dateCalendarPopup")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.previous_month = QPushButton("‹")
        self.previous_month.setAccessibleName("Предыдущий месяц")
        self.previous_month.setToolTip("Предыдущий месяц")
        self.next_month = QPushButton("›")
        self.next_month.setAccessibleName("Следующий месяц")
        self.next_month.setToolTip("Следующий месяц")
        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setObjectName("calendarMonthLabel")
        for button in (self.previous_month, self.next_month):
            button.setMinimumSize(36, 34)
        header.addWidget(self.previous_month)
        header.addWidget(self.month_label, 1)
        header.addWidget(self.next_month)
        layout.addLayout(header)

        self.calendar = QCalendarWidget()
        self.calendar.setObjectName("dateCalendar")
        self.calendar.setLocale(QLocale(calendar_locale_name()))
        self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.calendar.setDateRange(QDate(1, 1, 1), QDate(9999, 12, 31))
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        # Replace the built-in tiny navigation/tool buttons and inline date
        # editor; the ordinary native day grid and keyboard selection remain.
        self.calendar.setNavigationBarVisible(False)
        self.calendar.setDateEditEnabled(False)
        self.calendar.setMinimumSize(336, 244)
        layout.addWidget(self.calendar)

        footer = QHBoxLayout()
        self.previous_year = QPushButton("На год назад")
        self.previous_year.setAccessibleName("Предыдущий год")
        self.today_button = QPushButton("Сегодня")
        self.today_button.setToolTip("Сегодняшняя дата по UTC")
        self.next_year = QPushButton("На год вперёд")
        self.next_year.setAccessibleName("Следующий год")
        for button in (self.previous_year, self.today_button, self.next_year):
            button.setMinimumHeight(34)
            footer.addWidget(button)
        layout.addLayout(footer)
        for button in (self.previous_month, self.next_month, self.previous_year, self.today_button, self.next_year):
            button.setAutoDefault(False)
            button.setObjectName("calendarToday" if button is self.today_button else "calendarNavigation")
        self.previous_month.clicked.connect(lambda: self._move_month(-1))
        self.next_month.clicked.connect(lambda: self._move_month(1))
        self.previous_year.clicked.connect(lambda: self._move_year(-1))
        self.next_year.clicked.connect(lambda: self._move_year(1))
        self.today_button.clicked.connect(lambda: picker._choose_date(_qdate(datetime.now(timezone.utc).date())))
        self.calendar.clicked.connect(picker._choose_date)
        self.calendar.activated.connect(picker._choose_date)
        self.calendar.currentPageChanged.connect(self._update_header)
        self._refresh_weekend_colors()
        self._update_header(self.calendar.yearShown(), self.calendar.monthShown())
        translate_widget_tree(self)

    def _move_month(self, delta: int) -> None:
        shown = QDate(self.calendar.yearShown(), self.calendar.monthShown(), 1).addMonths(delta)
        if shown.isValid() and 1 <= shown.year() <= 9999:
            self.calendar.setCurrentPage(shown.year(), shown.month())

    def _move_year(self, delta: int) -> None:
        year = self.calendar.yearShown() + delta
        if 1 <= year <= 9999:
            self.calendar.setCurrentPage(year, self.calendar.monthShown())

    def _update_header(self, year: int, month: int) -> None:
        self.month_label.setText(f"{self.calendar.locale().standaloneMonthName(month)} {year}")
        self.previous_month.setEnabled((year, month) > (1, 1))
        self.next_month.setEnabled((year, month) < (9999, 12))
        self.previous_year.setEnabled(year > 1)
        self.next_year.setEnabled(year < 9999)

    def _refresh_weekend_colors(self) -> None:
        if not hasattr(self, "calendar"):
            return
        text = QTextCharFormat()
        text.setForeground(self.palette().color(QPalette.ColorRole.Text))
        self.calendar.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, text)
        self.calendar.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, text)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            self._refresh_weekend_colors()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)


class DatePickerButton(QPushButton):
    """A whole-button calendar picker with the small QDate API the dialog uses."""

    dateChanged = Signal(QDate)

    def __init__(self, value: QDate, parent=None):
        super().__init__(parent)
        self.setObjectName("datePickerButton")
        self._refresh_icon()
        self.setAutoDefault(False)
        self.setMinimumHeight(36)
        self._date = QDate()
        self.popup = None
        self.setDate(value)
        self.clicked.connect(self.open_calendar)

    def _refresh_icon(self) -> None:
        from .icons import action_icon
        self.setIcon(action_icon("calendar", color=self.palette().color(QPalette.ColorRole.ButtonText).name()))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            self._refresh_icon()

    def date(self) -> QDate:
        return QDate(self._date)

    def setDate(self, value: QDate) -> None:
        if not isinstance(value, QDate) or not value.isValid() or not 1 <= value.year() <= 9999:
            raise ValueError("Выберите действующую дату от 1 до 9999 года.")
        if value == self._date:
            return
        self._date = QDate(value)
        self.setText(value.toString("dd.MM.yyyy"))
        self.dateChanged.emit(QDate(value))

    def calendarPopup(self) -> bool:
        return True

    def calendarWidget(self) -> QCalendarWidget:
        if self.popup is None:
            self.popup = _CalendarPopup(self)
        return self.popup.calendar

    def open_calendar(self) -> None:
        if not self.isEnabled():
            return
        calendar = self.calendarWidget()
        calendar.setSelectedDate(self._date)
        calendar.setCurrentPage(self._date.year(), self._date.month())
        self.popup.adjustSize()
        position = self.mapToGlobal(QPoint(0, self.height() + 4))
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            x = max(available.left(), min(position.x(), available.right() - self.popup.width() + 1))
            y = position.y()
            if y + self.popup.height() > available.bottom() + 1:
                y = self.mapToGlobal(QPoint(0, 0)).y() - self.popup.height() - 4
            y = max(available.top(), min(y, available.bottom() - self.popup.height() + 1))
            position = QPoint(x, y)
        self.popup.move(position)
        self.popup.show()
        self.popup.raise_()
        calendar.setFocus()

    def _choose_date(self, value: QDate) -> None:
        if self.isEnabled():
            self.setDate(value)
        if self.popup is not None:
            self.popup.close()

    def hideEvent(self, event) -> None:
        if self.popup is not None:
            self.popup.close()
        super().hideEvent(event)


class DateFilterDialog(QDialog):
    """Edit a range locally; the caller commits it only after Accepted.

    No preferences, files, network or parent widgets are read or modified.
    Each bound is independent; the all-dates choice ignores retained edits.
    """

    def __init__(self, parent=None, *, date_from: str = "", date_to: str = ""):
        first, last = _bound(date_from), _bound(date_to)
        super().__init__(parent)
        self.setWindowTitle("Период загрузки")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        title = QLabel("Период загрузки")
        title.setObjectName("title")
        self.chrome = install_chrome(self, resizable=False, maximizable=False, minimizable=False)
        self.header_widget = QWidget(self)
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(title, 1)
        header.addWidget(self.chrome.controls)
        self.chrome.set_drag_area(self.header_widget)
        layout.addWidget(self.header_widget)
        description = QLabel("Выберите даты публикаций, которые нужно найти и скачать.")
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.all_dates = QRadioButton("Все даты")
        self.all_dates.setToolTip("Не ограничивать дату публикации.")
        self.custom_dates = QRadioButton("Выбрать период")
        self.custom_dates.setToolTip("Можно указать обе границы или только одну.")
        layout.addWidget(self.all_dates)
        layout.addWidget(self.custom_dates)

        self.bounds = QWidget()
        grid = QGridLayout(self.bounds)
        grid.setContentsMargins(22, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.from_enabled = _BoundCheckBox("С")
        self.from_enabled.setAccessibleName("Указать начало периода")
        self.to_enabled = _BoundCheckBox("По")
        self.to_enabled.setAccessibleName("Указать конец периода")
        today = _qdate(datetime.now(timezone.utc).date())
        self.date_from = DatePickerButton(_qdate(first) if first else today.addMonths(-1))
        self.date_to = DatePickerButton(_qdate(last) if last else today)
        for edit, accessible_name in ((self.date_from, "Начало периода, UTC"),
                                      (self.date_to, "Конец периода, UTC")):
            edit.setAccessibleName(accessible_name)
            edit.setToolTip("Открыть календарь. Дата публикации по UTC, включительно.")
        grid.addWidget(self.from_enabled, 0, 0)
        grid.addWidget(self.date_from, 0, 1)
        grid.addWidget(self.to_enabled, 1, 0)
        grid.addWidget(self.date_to, 1, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(self.bounds)

        self.utc_hint = QLabel("Обе границы включаются целиком. Даты публикаций считаются по UTC.")
        self.utc_hint.setObjectName("muted")
        self.utc_hint.setWordWrap(True)
        layout.addWidget(self.utc_hint)
        self.error_label = QLabel()
        self.error_label.setObjectName("error")
        self.error_label.setAccessibleName("Ошибка периода")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.apply_button.setText("Применить")
        self.apply_button.setObjectName("primary")
        self.apply_button.setDefault(True)
        self.cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancel_button.setText("Отмена")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.from_enabled.setChecked(first is not None)
        self.to_enabled.setChecked(last is not None)
        self.custom_dates.setChecked(first is not None or last is not None)
        self.all_dates.setChecked(first is None and last is None)
        self.all_dates.toggled.connect(self._update_controls)
        self.custom_dates.toggled.connect(self._update_controls)
        self.from_enabled.toggled.connect(self._update_controls)
        self.to_enabled.toggled.connect(self._update_controls)
        self.date_from.dateChanged.connect(self._clear_error)
        self.date_to.dateChanged.connect(self._clear_error)
        self._update_controls()
        translate_widget_tree(self)

    def _clear_error(self, *_args) -> None:
        self.error_label.clear()
        self.error_label.hide()

    def _update_controls(self, *_args) -> None:
        custom = self.custom_dates.isChecked()
        self.from_enabled.setEnabled(custom)
        self.to_enabled.setEnabled(custom)
        self.date_from.setEnabled(custom and self.from_enabled.isChecked())
        self.date_to.setEnabled(custom and self.to_enabled.isChecked())
        self._clear_error()

    def selected_range(self) -> tuple[str, str]:
        if self.all_dates.isChecked():
            return "", ""
        first = self.date_from.date().toString("yyyy-MM-dd") if self.from_enabled.isChecked() else ""
        last = self.date_to.date().toString("yyyy-MM-dd") if self.to_enabled.isChecked() else ""
        return first, last

    def accept(self) -> None:
        first, last = self.selected_range()
        if self.custom_dates.isChecked() and not (first or last):
            self.error_label.setText(tr("Выберите хотя бы одну границу периода или «Все даты»."))
            self.error_label.show()
            self.from_enabled.setFocus()
            return
        if first and last and first > last:
            self.error_label.setText(tr("Начало периода должно быть раньше окончания или совпадать с ним."))
            self.error_label.show()
            self.date_from.setFocus()
            return
        self._clear_error()
        super().accept()
