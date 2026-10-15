"""Bounded, offline acceptance checks for the shipped native design.

Entry point configures isolated preferences, collection and an empty vault first.
Only local generated pictures are shown; no job or platform login is started.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def design_probe(output: str) -> int:
    from PySide6.QtCore import QAbstractProxyModel, QDate, QElapsedTimer, QEventLoop, QPoint, Qt, QTimer
    from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPalette, QPolygon
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QApplication, QDialog,
                                   QFileSystemModel, QLabel, QToolButton)
    from .date_filter import DateFilterDialog
    from .localization import calendar_locale_name, get_language, tr
    from .themes import colors as theme_colors, get_theme
    from .ui import MainWindow, STYLE
    from .window_chrome import install_dialog_chrome_hook

    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Browser discovery in the advanced panel must also remain inside the QA
    # fixture; never enumerate a person's real browser profile metadata here.
    os.environ['APPDATA'] = str(root / 'isolated-roaming')
    os.environ['LOCALAPPDATA'] = str(root / 'isolated-local')
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    from .app_identity import apply_app_icon
    apply_app_icon(app)
    install_dialog_chrome_hook(app)
    app.setStyle('Fusion')
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, '#ffffff'),
                        (QPalette.ColorRole.WindowText, '#24272c'),
                        (QPalette.ColorRole.Base, '#ffffff'),
                        (QPalette.ColorRole.AlternateBase, '#fafbfc'),
                        (QPalette.ColorRole.Text, '#24272c'),
                        (QPalette.ColorRole.Button, '#ffffff'),
                        (QPalette.ColorRole.ButtonText, '#24272c'),
                        (QPalette.ColorRole.Highlight, '#525c6b'),
                        (QPalette.ColorRole.HighlightedText, '#ffffff')):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window._change_language('ru')
    if get_theme() != 'light':
        window._toggle_theme()
    window.resize(1180, 850)
    window.show()
    result = {'passed': False, 'errors': [], 'checks': {}, 'screenshots': {},
              'network_requests': 0, 'real_user_cookies_accessed': False,
              'demonstration_images_only': True, 'appearance_preferences': {}, 'window_chrome': {}}

    def check(name, condition):
        result['checks'][name] = bool(condition)
        if not condition:
            raise AssertionError(name)

    def wait_for_picker_entry(dialog, expected: Path, name: str) -> None:
        """Wait for an actual fixture row, rather than guessing a render delay."""
        picker = dialog.file_picker
        model = picker.findChild(QFileSystemModel)
        check(name + '_filesystem_model_present', model is not None)
        views = [view for view in picker.findChildren(QAbstractItemView)
                 if view.objectName() in ('listView', 'treeView')]
        ready_view = []
        directory_notifications = []
        elapsed = QElapsedTimer()
        elapsed.start()
        loop = QEventLoop(dialog)
        poll = QTimer(loop)
        poll.setInterval(25)
        timeout = QTimer(loop)
        timeout.setSingleShot(True)

        def inspect_entry():
            parent_index = model.index(str(expected.parent))
            source_index = model.index(str(expected))
            if (not parent_index.isValid() or not source_index.isValid()
                    or source_index.parent() != parent_index
                    or model.fileName(source_index) != expected.name
                    or model.rowCount(parent_index) == 0):
                return
            for view in views:
                current_model = view.model()
                proxies = []
                while isinstance(current_model, QAbstractProxyModel):
                    proxies.append(current_model)
                    current_model = current_model.sourceModel()
                if current_model != model or not view.isVisible():
                    continue
                visible_index = source_index
                for proxy in reversed(proxies):
                    visible_index = proxy.mapFromSource(visible_index)
                if (visible_index.isValid() and view.rootIndex() == visible_index.parent()
                        and not view.visualRect(visible_index).isEmpty()):
                    ready_view.append(view.objectName())
                    loop.quit()
                    return

        def directory_loaded(path):
            if Path(path).resolve() == expected.parent.resolve():
                directory_notifications.append(path)
                inspect_entry()

        model.directoryLoaded.connect(directory_loaded)
        poll.timeout.connect(inspect_entry)
        timeout.timeout.connect(loop.quit)
        try:
            inspect_entry()
            if not ready_view:
                poll.start()
                timeout.start(5000)
                loop.exec()
            poll.stop()
            timeout.stop()
            parent_index = model.index(str(expected.parent))
            result.setdefault('file_picker_model_entries', {})[name] = {
                'fixture_name': expected.name,
                'fixture_parent': str(expected.parent),
                'entry_visible': bool(ready_view),
                'visible_view': ready_view[0] if ready_view else None,
                'model_rows': model.rowCount(parent_index),
                'directory_loaded_signal_observed': bool(directory_notifications),
                'wait_ms': elapsed.elapsed(),
                'timeout_ms': 5000,
            }
            check(name + '_fixture_entry_loaded_and_visible', bool(ready_view))
        finally:
            poll.stop()
            timeout.stop()
            model.directoryLoaded.disconnect(directory_loaded)
            loop.deleteLater()

    def shot(name, widget):
        app.processEvents()
        target = root / (name + '.png')
        check('screenshot_' + name, widget.grab().save(str(target)))
        result['screenshots'][name] = str(target)

    def modal_presentation(name, dialog):
        owner = getattr(dialog, '_mira_modal_owner', None)
        overlay = getattr(owner, '_mira_modal_backdrop', None) if owner is not None else None
        check(name + '_owner_has_blurred_backdrop', owner is not None and overlay is not None
              and overlay.isVisible() and overlay.capture_count >= 1 and overlay.geometry() == owner.rect())
        check(name + '_live_owner_has_no_graphics_effect', owner.graphicsEffect() is None)
        center = dialog.frameGeometry().center()
        expected = owner.frameGeometry().center()
        available = dialog.screen().availableGeometry()
        check(name + '_dialog_centered_or_screen_bounded',
              abs(center.x() - expected.x()) <= 2 and abs(center.y() - expected.y()) <= 2
              or dialog.frameGeometry().left() == available.left()
              or dialog.frameGeometry().top() == available.top()
              or dialog.frameGeometry().right() == available.right()
              or dialog.frameGeometry().bottom() == available.bottom())

    def modal_shot(name, dialog):
        modal_presentation(name, dialog)
        image = window.grab()
        painter = QPainter(image)
        position = dialog.mapToGlobal(QPoint(0, 0)) - window.mapToGlobal(QPoint(0, 0))
        painter.drawPixmap(position, dialog.grab())
        painter.end()
        target = root / (name + '.png')
        check('screenshot_' + name, image.save(str(target)))
        result['screenshots'][name] = str(target)

    def native_chrome(name, widget):
        # Flush zero-delay frame synchronisation before sampling native facts.
        app.processEvents()
        app.processEvents()
        controller = getattr(widget, 'chrome', None) or getattr(widget, '_mira_window_chrome')
        diagnostics = controller.native_diagnostics()
        result['window_chrome'][name] = diagnostics
        if diagnostics['enabled']:
            check(name + '_native_caption_absent', diagnostics['window_exists'] and not diagnostics['caption_present'])
            check(name + '_full_native_client_rect', diagnostics['client_rect'] == diagnostics['window_rect'])
            rounded = not (widget.isMaximized() or widget.isFullScreen())
            if diagnostics['corner_backend'] == 'dwm':
                check(name + '_native_corner_preference', diagnostics['corner_preference'] == (2 if rounded else 1))
            else:
                check(name + '_fallback_corner_region', bool(widget.mask().isEmpty()) != rounded)
            proofs = result.setdefault('composed_corners', {})
            if name not in proofs:
                from .corner_capture import composed_corner_proof
                directory = root / 'corners'
                directory.mkdir(exist_ok=True)
                proof = composed_corner_proof(int(widget.winId()), directory / (name + '.png'), rounded=rounded)
                proofs[name] = proof
                check(name + '_composed_corner_pixels', proof['passed'])
        return diagnostics

    def settle_window_state():
        # Allow Qt's queued native-frame fit and DWM's state transition to finish.
        loop = QEventLoop(window)
        QTimer.singleShot(160, loop.quit)
        loop.exec()
        app.processEvents()

    def safe(callback):
        def run():
            try:
                callback()
            except Exception as exc:
                result['errors'].append(type(exc).__name__ + ': ' + str(exc))
                modal = QApplication.activeModalWidget()
                if modal is not None:
                    modal.reject()
                window._set_active(False)
                app.quit()
        return run

    def date_visit(callback):
        dialog = QApplication.activeModalWidget()
        check('date_popup_is_native_modal', isinstance(dialog, DateFilterDialog))
        check('date_dialog_has_integrated_chrome', bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
              and dialog.header_widget.isAncestorOf(dialog.chrome.controls)
              and dialog.chrome.minimize_button is None and dialog.chrome.maximize_button is None)
        native_chrome('date-dialog', dialog)
        modal_presentation('date-dialog', dialog)
        callback(dialog)

    def open_dates(callback):
        QTimer.singleShot(100, safe(lambda: date_visit(callback)))
        window.date_button.click()
        check('date_modal_returned', QApplication.activeModalWidget() is None)

    def set_range(dialog, first, last):
        dialog.custom_dates.setChecked(True)
        dialog.from_enabled.setChecked(bool(first))
        dialog.to_enabled.setChecked(bool(last))
        if first:
            dialog.date_from.setDate(QDate.fromString(first, 'yyyy-MM-dd'))
        if last:
            dialog.date_to.setDate(QDate.fromString(last, 'yyyy-MM-dd'))

    def bounds():
        return (window.date_from.date().toString('yyyy-MM-dd') if window.from_enabled.isChecked() else '',
                window.date_to.date().toString('yyyy-MM-dd') if window.to_enabled.isChecked() else '')

    def interval_visible(prefix):
        editor = window.request_delay.lineEdit()
        editor.deselect()
        app.processEvents()
        check(prefix + '_editor_fits_value', editor.width() >= editor.fontMetrics().horizontalAdvance(editor.text()) + 4)
        image = editor.grab().toImage()
        foreground = QColor(theme_colors()['text'])
        pixels = sum(abs(image.pixelColor(x, y).red() - foreground.red())
                     + abs(image.pixelColor(x, y).green() - foreground.green())
                     + abs(image.pixelColor(x, y).blue() - foreground.blue()) < 90
                     for x in range(image.width()) for y in range(image.height()))
        check(prefix + '_numeric_value_is_visible', bool(editor.text()) and pixels > 8)

    def auth_dropdown(name):
        combo = window.auth_source
        selected = combo.currentIndex()
        item_data = [combo.itemData(index) for index in range(combo.count())]
        combo.showPopup()
        app.processEvents()
        popup = combo.view().window()
        caption_absent = True
        native_style = None
        if os.name == 'nt' and app.platformName().lower() == 'windows':
            import ctypes
            from ctypes import wintypes
            user = ctypes.WinDLL('user32', use_last_error=True)
            user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            user.GetWindowLongW.restype = ctypes.c_long
            native_style = user.GetWindowLongW(int(popup.winId()), -16) & 0xffffffff
            caption_absent = not bool(native_style & 0x00c00000)
        result.setdefault('dropdowns', {})[name] = {'visible': popup.isVisible(), 'type': int(popup.windowType()),
                                                    'qt_flags': int(popup.windowFlags()), 'native_style': native_style}
        check(name + '_is_frameless_qt_popup', popup.isVisible() and popup.windowType() == Qt.WindowType.Popup
              and caption_absent)
        check(name + '_comfortable_choice_rows', combo.view().sizeHintForRow(0) >= 38)
        shot(name, popup)
        combo.hidePopup()
        app.processEvents()
        check(name + '_dismiss_keeps_selection_and_item_data', combo.currentIndex() == selected
              and [combo.itemData(index) for index in range(combo.count())] == item_data)

    def acceptance():
        check('main_has_integrated_chrome', bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
              and window.header_widget.isAncestorOf(window.chrome.controls))
        initial = native_chrome('main', window)
        window.chrome.maximize_button.click()
        settle_window_state()
        check('body_maximize_button_maximizes', window.isMaximized())
        maximized = native_chrome('main-maximized', window)
        if maximized['enabled']:
            check('main_maximized_fits_work_area', maximized['window_rect'] == maximized['work_area'])
        window.chrome.minimize_button.click()
        settle_window_state()
        check('body_minimize_from_maximized', window.isMinimized())
        minimized = window.chrome.native_diagnostics()
        result['window_chrome']['main-maximized-minimized'] = minimized
        if minimized['enabled']:
            rect = minimized['window_rect']
            check('maximized_minimize_keeps_iconic_rect', rect is not None and rect[0] <= -30000 and rect[1] <= -30000)
        window.showMaximized()
        settle_window_state()
        check('maximized_minimize_restore_state', window.isMaximized() and not window.isMinimized())
        maximized_restored = native_chrome('main-maximized-restored', window)
        if maximized_restored['enabled']:
            check('maximized_minimize_restore_work_area', maximized_restored['window_rect'] == maximized_restored['work_area'])
        window.showFullScreen()
        settle_window_state()
        check('main_fullscreen_state', window.isFullScreen())
        fullscreen = native_chrome('main-fullscreen', window)
        if fullscreen['enabled']:
            check('main_fullscreen_fits_monitor', fullscreen['window_rect'] == fullscreen['monitor_rect'])
        window.showMaximized()
        settle_window_state()
        window.chrome.maximize_button.click()
        settle_window_state()
        check('body_maximize_button_restores', not window.isMaximized() and not window.isFullScreen())
        restored = native_chrome('main-restored', window)
        if restored['enabled']:
            check('main_restore_preserves_native_geometry', restored['window_rect'] == initial['window_rect'])
        window.chrome.minimize_button.click()
        app.processEvents()
        check('body_minimize_button_minimizes', window.isMinimized())
        window.showNormal()
        window.resize(1180, 850)
        app.processEvents()
        check('three_main_tabs', window.tabs.count() == 3)
        check('journal_has_own_tab', 'Журнал' in [window.tabs.tabText(i) for i in range(window.tabs.count())])
        window.platform_pixiv_button.click()
        check('explicit_pixiv_selects_login_and_opt_in', window._selected_platform() == 'pixiv' and window.pixiv.isChecked() and 'Pixiv' in window.login_button.text())
        window.profile.setText('https://www.pixiv.net/en/users/20151243')
        check('pixiv_url_stays_pixiv', window._selected_platform() == 'pixiv')
        window.platform_x_button.click()
        check('explicit_x_clears_conflicting_url', window._selected_platform() == 'x' and not window.profile.text().strip())
        window.profile.setText('https://www.pixiv.net/en/users/20151243')
        check('pasted_url_selects_pixiv', window._selected_platform() == 'pixiv' and window.platform_pixiv_button.isChecked())
        check('platform_icons_present', not window.platform_pixiv_button.icon().isNull() and not window.platform_x_button.icon().isNull())

        def apply_range(dialog):
            set_range(dialog, '2026-10-01', '2026-10-15')
            dialog.date_from.click()
            popup = dialog.date_from.popup
            check('whole_date_button_opens_native_calendar', popup.isVisible())
            shot('date-calendar-popup', popup)
            popup.calendar.clicked.emit(QDate(2026, 10, 2))
            check('calendar_day_selection_updates_date_and_closes',
                  dialog.date_from.date() == QDate(2026, 10, 2) and not popup.isVisible())
            dialog.date_from.click()
            popup = dialog.date_from.popup
            popup.next_month.click()
            popup.hide()
            check('dismissed_calendar_keeps_chosen_date', dialog.date_from.date() == QDate(2026, 10, 2))
            dialog.date_from.setDate(QDate(2026, 10, 1))
            shot('date-period-popup', dialog)
            dialog.apply_button.click()
        open_dates(apply_range)
        check('date_apply_commits', bounds() == ('2026-10-01', '2026-10-15'))
        check('date_label_shows_period', '01.10.2026' in window.date_button.text() and '15.10.2026' in window.date_button.text())
        def cancel_range(dialog):
            set_range(dialog, '2026-09-01', '')
            dialog.cancel_button.click()
        open_dates(cancel_range)
        check('date_cancel_keeps_range', bounds() == ('2026-10-01', '2026-10-15'))
        def invalid_range(dialog):
            set_range(dialog, '2026-10-15', '2026-10-01')
            dialog.apply_button.click()
            check('inverted_range_stays_in_popup', dialog.isVisible() and bool(dialog.error_label.text()))
            dialog.cancel_button.click()
        open_dates(invalid_range)
        check('invalid_range_did_not_commit', bounds() == ('2026-10-01', '2026-10-15'))
        def single_bound(dialog):
            set_range(dialog, '', '2026-10-15')
            dialog.apply_button.click()
        open_dates(single_bound)
        check('single_bound_applies', bounds() == ('', '2026-10-15'))
        def all_dates(dialog):
            dialog.all_dates.setChecked(True)
            dialog.apply_button.click()
        open_dates(all_dates)
        check('all_dates_clears_both_bounds', bounds() == ('', '') and window.date_button.text() == 'Все даты')

        def advanced_visit():
            dialog = QApplication.activeModalWidget()
            check('advanced_is_native_dialog', isinstance(dialog, QDialog))
            check('advanced_has_integrated_chrome', bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
                  and dialog.header_widget.isAncestorOf(dialog.chrome.controls)
                  and dialog.chrome.minimize_button is None and dialog.chrome.maximize_button is None)
            native_chrome('advanced', dialog)
            check('advanced_owns_existing_auth_controls', dialog.isAncestorOf(window.auth_source))
            check('interval_has_no_tiny_spin_buttons', window.request_delay.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons)
            initial_delay = window.request_delay.value()
            window.request_delay_plus.click()
            check('large_interval_plus_changes_value', window.request_delay.value() == initial_delay + 0.5)
            window.request_delay_minus.click()
            check('large_interval_minus_changes_value', window.request_delay.value() == initial_delay)
            window.request_delay.setValue(2.0)
            window.request_delay_minus.click()
            check('interval_minimum_is_kept', window.request_delay.value() == 2.0)
            window.request_delay.setValue(120.0)
            window.request_delay_plus.click()
            check('interval_maximum_is_kept', window.request_delay.value() == 120.0)
            window.request_delay.setValue(initial_delay)
            interval_visible('interval')
            shot('advanced-settings-popup', dialog)
            modal_shot('advanced-centered-blur-light', dialog)
            auth_dropdown('dropdown-auth-light')
            dialog.reject()
        QTimer.singleShot(100, safe(advanced_visit))
        window.advanced_button.click()
        check('advanced_popup_returned', QApplication.activeModalWidget() is None)
        def help_visit():
            dialog = QApplication.activeModalWidget()
            check('help_has_integrated_chrome', isinstance(dialog, QDialog)
                  and bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
                  and dialog.header_widget.isAncestorOf(dialog.chrome.controls))
            native_chrome('help', dialog)
            shot('help-integrated-window', dialog)
            modal_shot('help-centered-blur-light', dialog)
            dialog.chrome.close_button.click()
        QTimer.singleShot(100, safe(help_visit))
        window.help_button.click()
        check('help_body_close_button_returns', QApplication.activeModalWidget() is None)
        check('help_close_removes_backdrop', getattr(window, '_mira_modal_backdrop', None) is None)
        from PySide6.QtWidgets import QMessageBox
        prompt = QMessageBox(window)
        prompt.setWindowTitle(tr('Ошибка'))
        prompt.setText(tr('Папка будет создана при запуске задания.'))
        prompt.setStandardButtons(QMessageBox.StandardButton.Ok)
        def stock_prompt_visit():
            check('stock_qt_prompt_has_integrated_chrome', bool(prompt.windowFlags() & Qt.WindowType.FramelessWindowHint)
                  and getattr(prompt, '_mira_auto_chrome_header', None) is not None)
            native_chrome('stock-qt-prompt', prompt)
            shot('stock-qt-prompt-integrated-window', prompt)
            modal_presentation('stock-prompt', prompt)
            prompt._mira_window_chrome.close_button.click()
        QTimer.singleShot(100, safe(stock_prompt_visit))
        prompt.exec()
        check('stock_qt_prompt_body_close_returns', not prompt.isVisible())
        prompt.deleteLater()
        picker_root = root / 'picker-fixtures'
        picker_root.mkdir(exist_ok=True)
        folder_fixture = picker_root / 'collection-check'
        folder_fixture.mkdir(exist_ok=True)
        file_fixture = picker_root / 'selection-check.txt'
        file_fixture.write_text('Offline file-picker acceptance fixture; contains no cookies or account data.\n',
                                encoding='utf-8')
        for directory, name in ((True, 'folder-picker-integrated-window'), (False, 'file-picker-integrated-window')):
            def picker_visit(name=name, directory=directory):
                from PySide6.QtWidgets import QFileDialog
                dialog = QApplication.activeModalWidget()
                check(name + '_uses_frameless_qt_chooser', isinstance(dialog, QDialog)
                      and bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
                      and dialog.file_picker.testOption(QFileDialog.Option.DontUseNativeDialog)
                      and not dialog.file_picker.isWindow()
                      and getattr(dialog.file_picker, '_mira_auto_chrome_header', None) is None)
                native_chrome(name, dialog)
                from PySide6.QtCore import QUrl
                dialog.file_picker.setSidebarUrls([QUrl.fromLocalFile(str(picker_root))])
                wait_for_picker_entry(dialog, folder_fixture if directory else file_fixture, name)
                shot(name, dialog)
                dialog.chrome.close_button.click()
            previous_folder = window.destination.text()
            QTimer.singleShot(100, safe(picker_visit))
            selected = window._pick_path('Каталог коллекции' if directory else 'Ваш локальный файл cookies',
                                         directory=directory, initial=str(picker_root))
            check(name + '_cancel_keeps_destination', not selected and window.destination.text() == previous_folder)
        window.auth_source.setCurrentIndex(window.auth_source.findData('none'))

        colors=[('#efd7c7','#d9a2b5','#f8e9c5','#795e94'),('#c6dcd9','#87b5b1','#ecddac','#31575e'),
                ('#cdc7e7','#9284b7','#ead6ef','#52436e'),('#e4c39b','#c4896b','#f7d9a7','#8b5646'),
                ('#b9c9dc','#687ea3','#e0deca','#30435f'),('#d6dfbd','#92aa8b','#eee2b6','#48694e')]
        images=root/'demonstration-artwork'
        images.mkdir(exist_ok=True)
        for index, palette in enumerate(colors):
            image=QPixmap(720, 460)
            painter=QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            gradient=QLinearGradient(0, 0, 720, 460)
            gradient.setColorAt(0, QColor(palette[0]))
            gradient.setColorAt(1, QColor(palette[1]))
            painter.fillRect(image.rect(), gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette[2]))
            painter.drawEllipse(200, 45, 300, 290)
            painter.setBrush(QColor(palette[3]))
            painter.drawPolygon(QPolygon([QPoint(0,390),QPoint(190,190),QPoint(350,330),QPoint(510,140),QPoint(720,390),QPoint(720,460),QPoint(0,460)]))
            painter.end()
            path=images/f'90000{index}_01.png'
            image.save(str(path))
            window._event({'type':'item','key':f'pixiv:demo:{index}', 'post_id':f'90000{index}', 'index':1,
                           'author_id':'20151243','platform':'pixiv','path':str(path)})
        window._event({'type':'stats','found':128,'downloaded':84,'skipped':12,'failed':0})
        window._event({'type':'state','state':'stopped','message':'Остановлено · продолжение доступно в истории'})
        window._append_log('info','Количество относится только к изображениям, которые платформа вернула для текущего доступа и периода. Полнота всей истории не гарантируется.')
        window.tabs.setCurrentIndex(0)
        shot('minimalism-main-window', window)
        check('header_has_no_job_status_chip', not window.header_widget.findChildren(QLabel, 'status'))
        check('application_and_window_icons_present', not app.windowIcon().isNull() and not window.windowIcon().isNull())
        clear_buttons = window.profile.findChildren(QToolButton)
        check('profile_native_clear_button_is_centered', len(clear_buttons) == 1
              and abs(clear_buttons[0].geometry().center().y() - window.profile.rect().center().y()) <= 1)
        window.resize(1020,720)
        app.processEvents()
        bottom=window.download_button.mapTo(window.centralWidget(),window.download_button.rect().bottomLeft())
        check('primary_action_fits_minimum_window', window.download_button.isVisible() and bottom.y()<window.centralWidget().height())
        shot('minimum-window-1020x720', window)
        window.resize(1180,850)
        window.tabs.setCurrentIndex(2)
        shot('event-journal', window)
        window.tabs.setCurrentIndex(0)
        window._set_active(True)
        check('platform_date_advanced_locked_during_job', all(not widget.isEnabled() for widget in (
            window.platform_x_button,window.platform_pixiv_button,window.date_button,window.advanced_button)))
        window._event({'type':'state','state':'paused','message':'На паузе'})
        check('pause_can_resume', window.pause_button.text() == 'Продолжить' and window.pause_button.isEnabled())
        window.current_job_id = 'offline-design-checkpoint'
        unchanged = (window.profile.text(), window.destination.text(), window.auth_source.currentData(),
                     bounds(), window.only_new.isChecked(), window.request_delay.value())
        totals = dict(window.total_stats)
        for language in ('ru', 'en', 'zh_CN'):
            window._change_language(language)
            for theme in ('light', 'dark'):
                if get_theme() != theme:
                    window._toggle_theme()
                prefix = language + '_' + theme
                app.processEvents()
                check(prefix + '_live_language_and_theme', get_language() == language and get_theme() == theme)
                check(prefix + '_native_window_palette', app.palette().color(QPalette.ColorRole.Window).name() == theme_colors()['window'])
                check(prefix + '_clear_button_stays_centered',
                      abs(clear_buttons[0].geometry().center().y() - window.profile.rect().center().y()) <= 1)
                check(prefix + '_paused_job_preserved', window.active and window.worker_state == 'paused'
                      and window.current_job_id == 'offline-design-checkpoint'
                      and window.pause_button.text() == tr('Продолжить'))
                current = (window.profile.text(), window.destination.text(), window.auth_source.currentData(),
                           bounds(), window.only_new.isChecked(), window.request_delay.value())
                check(prefix + '_inputs_and_counters_preserved', current == unchanged and window.total_stats == totals)
                result['appearance_preferences'][prefix] = {
                    'language': window.settings.value('ui_language'),
                    'theme': window.settings.value('ui_theme'),
                    'status': str(window.settings.status())}
                check(prefix + '_preferences_persisted', window.settings.value('ui_language') == language
                      and window.settings.value('ui_theme') == theme)
                check(prefix + '_appearance_controls_available_during_job', window.language_button.isEnabled()
                      and window.theme_button.isEnabled() and not window.download_button.isEnabled())
                check(prefix + '_saved_gallery_captions', window.gallery.count() == 6
                      and window.gallery.item(0).text() == '900000_01.png\n' + tr('Сохранено'))
                window.resize(1020, 720)
                app.processEvents()
                bottom = window.download_button.mapTo(window.centralWidget(), window.download_button.rect().bottomLeft())
                check(prefix + '_minimum_layout_fits', bottom.y() < window.centralWidget().height()
                      and window.gallery.height() >= 120)
                shot('minimalism-' + language + '-' + theme, window)
        window._set_active(False)
        check('controls_reenabled_after_job', window.date_button.isEnabled() and window.platform_pixiv_button.isEnabled())
        window._event({'type':'state','state':'stopped','message':'Остановлено · продолжение доступно в истории'})
        for language in ('en', 'zh_CN'):
            window._change_language(language)
            if get_theme() != 'dark':
                window._toggle_theme()
            def localized_calendar(dialog, language=language):
                set_range(dialog, '2026-10-01', '2026-10-15')
                dialog.date_from.click()
                popup = dialog.date_from.popup
                check(language + '_calendar_locale', popup.isVisible()
                      and popup.calendar.locale().name() == calendar_locale_name())
                check(language + '_calendar_dark_palette', popup.palette().color(QPalette.ColorRole.Window).name()
                      in {theme_colors()['window'], theme_colors()['surface']})
                shot('calendar-' + language + '-dark', popup)
                popup.hide()
                shot('date-filter-' + language + '-dark', dialog)
                dialog.cancel_button.click()
            open_dates(localized_calendar)
            check(language + '_localized_date_cancel_preserves_range', bounds() == unchanged[3])
            def localized_advanced(language=language):
                dialog = QApplication.activeModalWidget()
                check(language + '_advanced_is_native', dialog is window.advanced_dialog)
                interval_visible(language + '_dark_interval')
                shot('advanced-' + language + '-dark', dialog)
                modal_presentation(language + '_advanced_dark', dialog)
                if language == 'en':
                    auth_dropdown('dropdown-auth-en-dark')
                dialog.reject()
            QTimer.singleShot(100, safe(localized_advanced))
            window.advanced_button.click()
            window.tabs.setCurrentIndex(2)
            shot('journal-' + language + '-dark', window)
            window.tabs.setCurrentIndex(0)
        window._change_language('ru')
        def dark_help_visit():
            dialog = QApplication.activeModalWidget()
            modal_shot('help-centered-blur-dark', dialog)
            dialog.chrome.close_button.click()
        QTimer.singleShot(100, safe(dark_help_visit))
        window.help_button.click()
        check('dark_help_close_removes_backdrop', getattr(window, '_mira_modal_backdrop', None) is None)
        window._change_language('ru')
        if get_theme() != 'light':
            window._toggle_theme()
        check('final_russian_light_restored', get_language() == 'ru' and get_theme() == 'light'
              and window.settings.value('ui_language') == 'ru' and window.settings.value('ui_theme') == 'light')
        result['passed']=True
        window.close()
        app.quit()

    QTimer.singleShot(250, safe(acceptance))
    QTimer.singleShot(30000, safe(lambda: (_ for _ in ()).throw(TimeoutError('Native design check timed out.'))))
    app.exec()
    (root/'design-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] and not result['errors'] else 1
