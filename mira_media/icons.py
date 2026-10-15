"""Small native icons painted locally for Mira's Qt Widgets interface.

No files, fonts, network resources or browser modules are required. Create an
application before calling the helpers, just as for any other QPixmap use.
Platform marks are simple app-drawn badges and accompany a platform text label.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QStyle


def _application() -> QApplication:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        raise RuntimeError("Create QApplication before requesting a Mira icon.")
    return app


def _canvas(size: int) -> tuple[QPixmap, QPainter]:
    _application()
    size = max(8, min(256, int(size)))
    # Render at twice the logical size for crisp native high-DPI presentation.
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24.0, size / 24.0)
    return pixmap, painter


def platform_icon(platform: str, size: int = 24) -> QIcon:
    """Return a monochrome X or blue Pixiv-p badge; pair it with its label."""
    _application()
    platform = str(platform).casefold()
    if platform not in {"x", "twitter", "pixiv"}:
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    pixmap, painter = _canvas(size)
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#111318" if platform in {"x", "twitter"} else "#0096fa"))
        painter.drawRoundedRect(QRectF(1.0, 1.0, 22.0, 22.0), 5.0, 5.0)
        if platform in {"x", "twitter"}:
            painter.setBrush(QColor("#ffffff"))
            # An original, compact X mark, formed by two diagonal strokes.
            painter.drawPolygon(QPolygonF([QPointF(5.0, 5.0), QPointF(8.5, 5.0),
                                           QPointF(19.0, 19.0), QPointF(15.5, 19.0)]))
            painter.drawPolygon(QPolygonF([QPointF(16.8, 5.0), QPointF(19.0, 5.0),
                                           QPointF(7.2, 19.0), QPointF(5.0, 19.0)]))
        else:
            pen = QPen(QColor("#ffffff"), 2.6, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(8.2, 8.2), QPointF(8.2, 19.0))
            painter.drawEllipse(QRectF(8.2, 7.7, 8.4, 8.2))
    finally:
        painter.end()
    return QIcon(pixmap)


def action_icon(name: str, size: int = 20, color: str | None = None) -> QIcon:
    """Return a lightweight line icon, or Qt's native file icon for unknown names."""
    _application()
    name = str(name).casefold()
    known = {"folder", "calendar", "download", "pause", "play", "stop", "history",
             "log", "settings", "help", "login", "logout", "image", "sun", "moon", "globe"}
    if name not in known:
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
    if color is None:
        from .themes import colors
        color = colors()["muted"]
    ink = QColor(color)
    if not ink.isValid():
        ink = QColor("#5f6672")
    pixmap, painter = _canvas(size)
    try:
        painter.setPen(QPen(ink, 1.8, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        def line(x1, y1, x2, y2):
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        if name == "folder":
            path = QPainterPath(QPointF(3, 7))
            path.lineTo(3, 5)
            path.lineTo(9, 5)
            path.lineTo(11, 8)
            path.lineTo(21, 8)
            path.lineTo(21, 19)
            path.lineTo(3, 19)
            path.closeSubpath()
            painter.drawPath(path)
            line(3, 10, 21, 10)
        elif name == "calendar":
            painter.drawRoundedRect(QRectF(4, 6, 16, 15), 2, 2)
            line(4, 10, 20, 10)
            line(8, 3, 8, 8)
            line(16, 3, 16, 8)
            painter.drawPoint(QPointF(8, 14))
            painter.drawPoint(QPointF(12, 14))
            painter.drawPoint(QPointF(16, 14))
            painter.drawPoint(QPointF(8, 17.5))
            painter.drawPoint(QPointF(12, 17.5))
        elif name == "download":
            line(12, 3, 12, 15)
            line(7, 10, 12, 15)
            line(12, 15, 17, 10)
            path = QPainterPath(QPointF(4, 17))
            path.lineTo(4, 21)
            path.lineTo(20, 21)
            path.lineTo(20, 17)
            painter.drawPath(path)
        elif name == "pause":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            painter.drawRoundedRect(QRectF(6.5, 4, 3.5, 16), 1.1, 1.1)
            painter.drawRoundedRect(QRectF(14, 4, 3.5, 16), 1.1, 1.1)
        elif name == "play":
            painter.drawPolygon(QPolygonF([QPointF(7, 4), QPointF(20, 12), QPointF(7, 20)]))
        elif name == "stop":
            painter.drawRoundedRect(QRectF(5, 5, 14, 14), 1.5, 1.5)
        elif name == "history":
            painter.drawArc(QRectF(4, 4, 16, 16), 125 * 16, -300 * 16)
            line(3.5, 4, 3.5, 9)
            line(3.5, 9, 8.5, 9)
            line(12, 7, 12, 12)
            line(12, 12, 15, 14)
        elif name == "log":
            for y in (6, 12, 18):
                painter.drawPoint(QPointF(3, y))
                line(7, y, 21, y)
        elif name == "settings":
            painter.drawEllipse(QRectF(5.8, 5.8, 12.4, 12.4))
            painter.drawEllipse(QRectF(9.6, 9.6, 4.8, 4.8))
            for index in range(8):
                angle = math.pi * index / 4
                line(12 + 7.0 * math.cos(angle), 12 + 7.0 * math.sin(angle),
                     12 + 9.3 * math.cos(angle), 12 + 9.3 * math.sin(angle))
        elif name == "help":
            painter.drawEllipse(QRectF(3, 3, 18, 18))
            path = QPainterPath(QPointF(9, 8.7))
            path.cubicTo(9, 5.4, 15.7, 5.4, 15, 9.4)
            path.cubicTo(14.7, 11.4, 12, 11.2, 12, 14)
            painter.drawPath(path)
            painter.drawPoint(QPointF(12, 17.5))
        elif name == "login":
            path = QPainterPath(QPointF(14, 4))
            path.lineTo(20, 4)
            path.lineTo(20, 20)
            path.lineTo(14, 20)
            painter.drawPath(path)
            line(3, 12, 15, 12)
            line(10, 7, 15, 12)
            line(15, 12, 10, 17)
        elif name == "logout":
            path = QPainterPath(QPointF(10, 4))
            path.lineTo(4, 4)
            path.lineTo(4, 20)
            path.lineTo(10, 20)
            painter.drawPath(path)
            line(9, 12, 21, 12)
            line(16, 7, 21, 12)
            line(21, 12, 16, 17)
        elif name == "image":
            painter.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
            painter.drawEllipse(QRectF(15, 7, 3, 3))
            path = QPainterPath(QPointF(4, 17))
            path.lineTo(9, 11)
            path.lineTo(13, 15)
            path.lineTo(16, 12)
            path.lineTo(20, 17)
            painter.drawPath(path)
        elif name == "sun":
            painter.drawEllipse(QRectF(7, 7, 10, 10))
            for index in range(8):
                angle = math.pi * index / 4
                line(12 + 8.0 * math.cos(angle), 12 + 8.0 * math.sin(angle),
                     12 + 10.2 * math.cos(angle), 12 + 10.2 * math.sin(angle))
        elif name == "moon":
            path = QPainterPath(QPointF(17.8, 17.2))
            path.cubicTo(8.7, 21.2, 3.3, 9.0, 11.1, 4.1)
            path.cubicTo(8.7, 11.5, 12.9, 16.1, 17.8, 17.2)
            path.closeSubpath()
            painter.drawPath(path)
        elif name == "globe":
            painter.drawEllipse(QRectF(3, 3, 18, 18))
            painter.drawEllipse(QRectF(8, 3, 8, 18))
            line(3, 12, 21, 12)
            path = QPainterPath(QPointF(4.3, 7.3))
            path.cubicTo(9.5, 9.5, 14.5, 9.5, 19.7, 7.3)
            painter.drawPath(path)
            path = QPainterPath(QPointF(4.3, 16.7))
            path.cubicTo(9.5, 14.5, 14.5, 14.5, 19.7, 16.7)
            painter.drawPath(path)
    finally:
        painter.end()
    return QIcon(pixmap)
