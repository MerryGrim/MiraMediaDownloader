"""Native date choices and validation; no modal exec, settings or network."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDateEdit, QDialog, QDialogButtonBox, QStyle, QStyleOptionButton, QTableView

from mira_media.date_filter import DateFilterDialog, DatePickerButton, range_label


@pytest.fixture(scope="module")
def app():
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    application = QApplication.instance() or QApplication([])
    return application


@pytest.fixture
def dialogs(app):
    created = []
    def create(**kwargs):
        dialog = DateFilterDialog(**kwargs)
        created.append(dialog)
        return dialog
    yield create
    for dialog in created:
        dialog.close()
        dialog.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("first,last,label", [
    ("", "", "Все даты"),
    ("2026-10-01", "", "С 01.10.2026"),
    ("", "2026-10-14", "По 14.10.2026"),
    ("2026-10-01", "2026-10-14", "01.10.2026 — 14.10.2026"),
    ("2026-10-14", "2026-10-14", "14.10.2026 — 14.10.2026"),
])
def test_range_labels_are_readable_and_preserve_independent_bounds(first, last, label):
    assert range_label(first, last) == label


def test_default_all_dates_has_no_bounds_and_native_calendar_popups(dialogs):
    dialog = dialogs()
    assert dialog.windowTitle() == "Период загрузки" and dialog.isModal()
    assert dialog.all_dates.isChecked() and not dialog.custom_dates.isChecked()
    assert dialog.selected_range() == ("", "")
    assert not dialog.date_from.isEnabled() and not dialog.date_to.isEnabled()
    assert dialog.date_from.calendarPopup() and dialog.date_to.calendarPopup()
    assert "UTC" in dialog.utc_hint.text()


def test_date_dialog_has_close_only_body_header_and_rejects_on_close(dialogs, app):
    dialog = dialogs(date_from="2026-10-01")
    dialog.show()
    app.processEvents()
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert dialog.header_widget.isAncestorOf(dialog.chrome.controls)
    assert dialog.chrome.maximize_button is None and dialog.chrome.minimize_button is None
    dialog.chrome.close_button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not dialog.isVisible()
    assert dialog.apply_button.text() == "Применить" and dialog.cancel_button.text() == "Отмена"
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


@pytest.mark.parametrize("first,last", [("2026-10-01", "2026-10-14"), ("2026-10-01", ""),
                                       ("", "2026-10-14"), ("2026-10-14", "2026-10-14")])
def test_restores_custom_both_or_one_bound_and_accepts_inclusive_same_day(dialogs, first, last):
    dialog = dialogs(date_from=first, date_to=last)
    assert dialog.custom_dates.isChecked()
    assert dialog.from_enabled.isChecked() == bool(first)
    assert dialog.to_enabled.isChecked() == bool(last)
    assert dialog.date_from.isEnabled() == bool(first)
    assert dialog.date_to.isEnabled() == bool(last)
    assert dialog.selected_range() == (first, last)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_all_dates_ignores_retained_custom_edits_then_restores_them(dialogs):
    dialog = dialogs(date_from="2026-10-01", date_to="2026-10-14")
    dialog.all_dates.setChecked(True)
    assert dialog.selected_range() == ("", "")
    assert not dialog.date_from.isEnabled() and not dialog.from_enabled.isEnabled()
    dialog.custom_dates.setChecked(True)
    assert dialog.selected_range() == ("2026-10-01", "2026-10-14")
    dialog.from_enabled.setChecked(False)
    assert dialog.selected_range() == ("", "2026-10-14")
    assert not dialog.date_from.isEnabled() and dialog.date_to.isEnabled()


def test_custom_mode_without_bounds_requires_an_explicit_choice_inline(dialogs, app):
    dialog = dialogs()
    dialog.show()
    dialog.custom_dates.setChecked(True)
    dialog.apply_button.click()
    app.processEvents()
    assert dialog.result() != QDialog.DialogCode.Accepted and dialog.isVisible()
    assert dialog.error_label.isVisible() and "хотя бы одну" in dialog.error_label.text()
    dialog.from_enabled.setChecked(True)
    assert not dialog.error_label.text()
    dialog.apply_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_inverted_range_keeps_dialog_open_and_correction_clears_inline_error(dialogs, app):
    dialog = dialogs(date_from="2026-10-15", date_to="2026-10-14")
    dialog.show()
    dialog.apply_button.click()
    app.processEvents()
    assert dialog.isVisible() and dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.isVisible() and "Начало периода" in dialog.error_label.text()
    dialog.date_to.setDate(QDate(2026, 10, 15))
    assert not dialog.error_label.text()
    dialog.apply_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_range() == ("2026-10-15", "2026-10-15")


def test_cancel_and_separate_dialogs_do_not_commit_or_share_state(dialogs):
    initial = {"date_from": "2026-10-01", "date_to": "2026-10-14"}
    dialog = dialogs(**initial)
    dialog.date_from.setDate(QDate(2026, 10, 4))
    dialog.cancel_button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected
    reopened = dialogs(**initial)
    assert reopened.selected_range() == ("2026-10-01", "2026-10-14")
    assert initial == {"date_from": "2026-10-01", "date_to": "2026-10-14"}
    reopened.all_dates.setChecked(True)
    assert dialog.selected_range() == ("2026-10-04", "2026-10-14")


def test_iso_range_not_silently_clamped_to_qdateedit_default_minimum(dialogs):
    dialog = dialogs(date_from="1700-01-02", date_to="1700-01-03")
    assert dialog.selected_range() == ("1700-01-02", "1700-01-03")


def test_date_button_opens_calendar_and_real_day_click_picks_without_accepting_parent(dialogs, app):
    dialog = dialogs(date_from="2026-10-14", date_to="2026-10-31")
    dialog.show()
    app.processEvents()
    picker = dialog.date_from
    assert isinstance(picker, DatePickerButton) and picker.text() == "14.10.2026"
    assert not picker.icon().isNull() and not dialog.findChildren(QDateEdit)
    changed = QSignalSpy(picker.dateChanged)
    picker.click()
    app.processEvents()
    popup, calendar = picker.popup, picker.popup.calendar
    assert popup.isVisible() and not calendar.isNavigationBarVisible()
    assert not calendar.isDateEditEnabled()
    assert all(button.height() >= 32 for button in (popup.previous_month, popup.next_month,
               popup.previous_year, popup.next_year, popup.today_button))
    view = calendar.findChild(QTableView, "qt_calendar_calendarview")
    assert view is not None
    candidates = [view.model().index(row, column) for row in range(view.model().rowCount())
                  for column in range(view.model().columnCount())
                  if str(view.model().index(row, column).data(Qt.ItemDataRole.DisplayRole)) == "21"]
    assert len(candidates) == 1
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                     pos=view.visualRect(candidates[0]).center())
    app.processEvents()
    assert picker.date() == QDate(2026, 10, 21) and picker.text() == "21.10.2026"
    assert changed.count() == 1
    assert dialog.selected_range() == ("2026-10-21", "2026-10-31")
    assert not popup.isVisible() and dialog.isVisible()
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_calendar_navigation_and_escape_do_not_change_selected_date(dialogs, app):
    dialog = dialogs(date_from="2026-10-14")
    dialog.show()
    picker = dialog.date_from
    picker.click()
    app.processEvents()
    popup, calendar = picker.popup, picker.popup.calendar
    popup.next_month.click()
    assert (calendar.yearShown(), calendar.monthShown()) == (2026, 11)
    popup.previous_year.click()
    assert (calendar.yearShown(), calendar.monthShown()) == (2025, 11)
    # Moving the native grid's keyboard selection is provisional too; only
    # clicking/activating a date or Today commits it to the picker.
    calendar.setSelectedDate(QDate(2025, 11, 22))
    QTest.keyClick(calendar, Qt.Key.Key_Escape)
    app.processEvents()
    assert not popup.isVisible() and picker.date() == QDate(2026, 10, 14)
    assert dialog.selected_range() == ("2026-10-14", "") and dialog.isVisible()
    picker.click()
    app.processEvents()
    assert (calendar.yearShown(), calendar.monthShown()) == (2026, 10)
    dialog.reject()
    app.processEvents()
    assert not popup.isVisible()


def test_calendar_respects_iso_endpoints_and_disabled_picker_never_opens(dialogs, app):
    dialog = dialogs(date_from="0001-01-01")
    dialog.show()
    picker = dialog.date_from
    picker.click()
    app.processEvents()
    popup = picker.popup
    assert not popup.previous_month.isEnabled() and not popup.previous_year.isEnabled()
    popup.close()
    picker.setDate(QDate(9999, 12, 31))
    picker.click()
    app.processEvents()
    assert not popup.next_month.isEnabled() and not popup.next_year.isEnabled()
    assert dialog.selected_range() == ("9999-12-31", "")
    popup.close()
    dialog.from_enabled.setChecked(False)
    picker.open_calendar()
    assert not popup.isVisible()
    with pytest.raises(ValueError):
        picker.setDate(QDate(10000, 1, 1))
    with pytest.raises(ValueError):
        picker.setDate(QDate())


def test_checked_bound_has_visible_tick_under_filled_application_theme(dialogs, app):
    dialog = dialogs(date_from="2026-10-01")
    dialog.setStyleSheet("QCheckBox::indicator { width:15px; height:15px; border:1px solid #b6bdc6; "
                        "border-radius:3px; background:white; } "
                        "QCheckBox::indicator:checked { background:#30353c; border-color:#30353c; }")
    dialog.show()
    app.processEvents()
    checkbox = dialog.from_enabled
    option = QStyleOptionButton()
    checkbox.initStyleOption(option)
    indicator = checkbox.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, checkbox)
    interior = indicator.adjusted(3, 3, -3, -3)
    image = checkbox.grab().toImage()
    colors = [image.pixelColor(x, y) for x in range(interior.left(), interior.right() + 1)
              for y in range(interior.top(), interior.bottom() + 1)]
    assert sum(min(color.red(), color.green(), color.blue()) > 225 for color in colors) >= 5
    assert sum(max(color.red(), color.green(), color.blue()) < 100 for color in colors) >= 5
    checkbox.setChecked(False)
    app.processEvents()
    unchecked = checkbox.grab().toImage()
    assert all(min(unchecked.pixelColor(x, y).red(), unchecked.pixelColor(x, y).green(),
                   unchecked.pixelColor(x, y).blue()) > 225
               for x in range(interior.left(), interior.right() + 1)
               for y in range(interior.top(), interior.bottom() + 1))


@pytest.mark.parametrize("value", ["2026-02-30", "2026-1-2", "20261014", "not-a-date"])
def test_invalid_initial_date_fails_safely_without_dialog_or_settings(app, value):
    with pytest.raises(ValueError, match="ГГГГ-ММ-ДД"):
        DateFilterDialog(date_from=value)
    with pytest.raises(ValueError, match="ГГГГ-ММ-ДД"):
        range_label(value, "")
