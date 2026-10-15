"""Popup rendering and native selection must preserve the original item data."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from mira_media.dropdown import PolishedComboBox
from mira_media.themes import apply_theme


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_native_popup_is_roomy_and_keyboard_selection_preserves_data(app, theme):
    apply_theme(app, theme)
    combo = PolishedComboBox()
    combo.addItem('В приложении / In app / 应用内', 'embedded')
    combo.addItem('Firefox — generated fixture', {'browser': 'firefox', 'id': 'fixture'})
    combo.addItem('Файл cookies / Cookie file / 文件', 'file')
    combo.resize(420, 44)
    combo.show()
    combo.setFocus()
    app.processEvents()
    combo.showPopup()
    app.processEvents()
    try:
        assert combo.view().isVisible()
        option = QStyleOptionViewItem()
        option.fontMetrics = combo.fontMetrics()
        assert combo.view().itemDelegate().sizeHint(option, combo.model().index(0, 0)).height() >= 38
        assert combo.view().window().objectName() == 'miraComboPopup'
        assert not combo.view().grab().isNull()
        QTest.keyClick(combo.view(), Qt.Key.Key_Down)
        QTest.keyClick(combo.view(), Qt.Key.Key_Return)
        assert combo.currentData() == {'browser': 'firefox', 'id': 'fixture'}
        before = combo.currentData()
        combo.showPopup()
        QTest.keyClick(combo.view(), Qt.Key.Key_Down)
        QTest.keyClick(combo.view(), Qt.Key.Key_Escape)
        assert combo.currentData() == before
    finally:
        combo.hidePopup()
        combo.close()
        combo.deleteLater()
        app.processEvents()
