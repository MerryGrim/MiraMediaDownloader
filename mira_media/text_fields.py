"""Narrow style fix for Qt's native clear actions inside text fields.

Append this to the application stylesheet before constructing fields. General
toolbar button padding/minimum heights must not change the small embedded Qt
button after QLineEdit positions it. Its QAction, icon, keyboard, text-editing,
read-only and undo behavior remain Qt's own implementation.
"""


CLEAR_BUTTON_STYLESHEET = """
QLineEdit QToolButton {
    padding:0; margin:0; min-width:0; min-height:0;
    border:none; background:transparent;
}
"""
