"""Roomy native combo popups with keyboard behavior provided by Qt."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QListView, QStyle,
                              QStyledItemDelegate)

from .themes import colors


class _ChoiceDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width() + 48, max(38, option.fontMetrics.height() + 20))

    def paint(self, painter, option, index):
        c = colors()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(3, 2, -3, -2)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(c['selected'] if selected else c['hover']))
            painter.drawRoundedRect(QRectF(rect), 6, 6)
        ink = c['disabled'] if not enabled else c['selection_text'] if selected else c['text']
        painter.setPen(QColor(ink))
        font = option.font
        font.setWeight(font.Weight.DemiBold if selected else font.Weight.Normal)
        painter.setFont(font)
        text_rect = rect.adjusted(12, 0, -34, 0)
        caption = option.fontMetrics.elidedText(str(index.data() or ''), Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, caption)
        if selected:
            x, y = rect.right() - 20, rect.center().y()
            painter.setPen(QPen(QColor(ink), 1.8, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(QPointF(x-4, y), QPointF(x-1, y+3))
            painter.drawLine(QPointF(x-1, y+3), QPointF(x+5, y-4))
        painter.restore()


class PolishedComboBox(QComboBox):
    """Qt selection/scrolling/keyboard semantics, with a quiet rounded popup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(8)
        view = QListView(self)
        view.setObjectName('miraChoices')
        view.setItemDelegate(_ChoiceDelegate(view))
        view.setMouseTracking(True)
        view.setSpacing(0)
        view.setUniformItemSizes(True)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setView(view)

    def showPopup(self):
        super().showPopup()
        popup = self.view().window()
        popup.setObjectName('miraComboPopup')
        # This is the existing Qt popup, not a replacement model or menu.
        # Item data, keyboard navigation, selection and cancel remain native.
        c = colors()
        popup.setStyleSheet(
            f'QFrame#miraComboPopup {{ background:{c["surface"]}; border:1px solid {c["border"]}; border-radius:9px; }}'
            f'QListView#miraChoices {{ background:{c["surface"]}; color:{c["text"]}; border:none; padding:5px; outline:0; }}'
        )
        self.view().setMinimumWidth(self.width())
        self.view().viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = colors()
        painter.setPen(QPen(QColor(c['muted'] if self.isEnabled() else c['disabled']), 1.6,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        x, y = self.width() - 18, self.height() / 2
        painter.drawLine(QPointF(x-4, y-2), QPointF(x, y+2))
        painter.drawLine(QPointF(x, y+2), QPointF(x+4, y-2))
        painter.end()
