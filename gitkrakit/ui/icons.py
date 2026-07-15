"""
icons.py
Icônes générées par code (aucun fichier d'asset) : pastille carrée arrondie
colorée avec la lettre de l'état du fichier (M/A/D/R…), façon GitKraken.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from gitkrakit import theme

_LETTERS = {
    "modified": "M",
    "added": "A",
    "deleted": "D",
    "renamed": "R",
    "copied": "C",
    "untracked": "U",
    "conflict": "!",
    "typechange": "T",
}

_SIZE = 16


@lru_cache(maxsize=None)
def status_icon(status: str) -> QIcon:
    """Icône de l'état d'un fichier ; mise en cache (un état = une icône)."""
    color = QColor(theme.STATUS_COLORS.get(status, theme.TEXT_MUTED))

    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    background = QColor(color)
    background.setAlpha(50)
    painter.setBrush(background)
    painter.setPen(color)
    painter.drawRoundedRect(QRectF(0.5, 0.5, _SIZE - 1, _SIZE - 1), 4, 4)

    font = QFont(theme.UI_FONT_FAMILY, 8)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, _LETTERS.get(status, "?"))
    painter.end()

    return QIcon(pixmap)


# ----------------------------------------------------------------------
# Icônes de la barre d'outils : glyphes vectoriels simples dessinés au
# QPainter (pas de fichiers d'assets), dans le style épuré de l'appli.
# ----------------------------------------------------------------------
_TB_SIZE = 18


def _pen(color: str, width: float = 1.6) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _arrowhead(painter: QPainter, tip: QPointF, color: str, pointing_down: bool, size: float = 3.2) -> None:
    dy = -size if pointing_down else size
    poly = QPolygonF([QPointF(tip.x() - size, tip.y() + dy), QPointF(tip.x() + size, tip.y() + dy), tip])
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPolygon(poly)


def _draw_open(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    folder = QPolygonF(
        [QPointF(2, 5), QPointF(7, 5), QPointF(8.5, 3.5), QPointF(16, 3.5), QPointF(16, 14), QPointF(2, 14)]
    )
    painter.drawPolygon(folder)


def _draw_fetch(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.drawLine(QPointF(9, 3), QPointF(9, 11.5))
    _arrowhead(painter, QPointF(9, 13.5), color, pointing_down=True)


def _draw_pull(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.drawLine(QPointF(9, 2.5), QPointF(9, 9.5))
    _arrowhead(painter, QPointF(9, 11.5), color, pointing_down=True)
    painter.drawLine(QPointF(4, 15), QPointF(14, 15))


def _draw_push(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.drawLine(QPointF(9, 14.5), QPointF(9, 6.5))
    _arrowhead(painter, QPointF(9, 3.5), color, pointing_down=False)
    painter.drawLine(QPointF(4, 15), QPointF(14, 15))


def _draw_branch(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.drawLine(QPointF(6, 6), QPointF(6, 13))
    path = QPainterPath(QPointF(6, 9.5))
    path.cubicTo(QPointF(6, 7), QPointF(9, 7), QPointF(12.5, 7))
    painter.drawPath(path)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    for point in (QPointF(6, 4.5), QPointF(6, 14), QPointF(12.5, 7)):
        painter.drawEllipse(point, 1.6, 1.6)


def _draw_gitflow(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.drawLine(QPointF(5.5, 4.5), QPointF(5.5, 13.5))
    painter.drawLine(QPointF(5.5, 9), QPointF(12.5, 9))
    painter.drawLine(QPointF(12.5, 9), QPointF(12.5, 5))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    for point in (QPointF(5.5, 4.5), QPointF(5.5, 13.5), QPointF(12.5, 5)):
        painter.drawEllipse(point, 1.5, 1.5)


def _draw_stash(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(3, 7, 12, 7), 1.5, 1.5)
    painter.drawLine(QPointF(3, 9.8), QPointF(15, 9.8))


def _draw_pop(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(3, 10, 12, 5), 1.5, 1.5)
    painter.drawLine(QPointF(9, 8.5), QPointF(9, 3))
    _arrowhead(painter, QPointF(9, 2), color, pointing_down=False)


def _draw_back(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.drawLine(QPointF(13, 9), QPointF(4.5, 9))
    poly = QPolygonF([QPointF(8, 4.5), QPointF(4, 9), QPointF(8, 13.5)])
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPolygon(poly)


def _draw_refresh(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    rect = QRectF(3.5, 3.5, 11, 11)
    painter.drawArc(rect, 40 * 16, 260 * 16)
    _arrowhead(painter, QPointF(13.2, 5.4), color, pointing_down=True)


def _draw_system(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(2.5, 3, 13, 9), 1.5, 1.5)
    painter.drawLine(QPointF(7, 15), QPointF(11, 15))
    painter.drawLine(QPointF(9, 12), QPointF(9, 15))


def _draw_light(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color, 1.5))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QPointF(9, 9), 3.2, 3.2)
    for start, end in (
        ((9, 1.5), (9, 3.3)), ((9, 14.7), (9, 16.5)),
        ((1.5, 9), (3.3, 9)), ((14.7, 9), (16.5, 9)),
        ((3.7, 3.7), (5, 5)), ((13, 13), (14.3, 14.3)),
        ((13, 5), (14.3, 3.7)), ((3.7, 14.3), (5, 13)),
    ):
        painter.drawLine(QPointF(*start), QPointF(*end))


def _draw_dark(painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(12.8, 3.2))
    path.cubicTo(QPointF(7.2, 3.5), QPointF(5.4, 10), QPointF(10.2, 13.4))
    path.cubicTo(QPointF(6, 14.2), QPointF(2.8, 11.1), QPointF(3.1, 7.2))
    path.cubicTo(QPointF(3.4, 3.5), QPointF(7.5, 1), QPointF(12.8, 3.2))
    painter.drawPath(path)


_TB_DRAWERS = {
    "open": _draw_open,
    "back": _draw_back,
    "fetch": _draw_fetch,
    "pull": _draw_pull,
    "push": _draw_push,
    "branch": _draw_branch,
    "gitflow": _draw_gitflow,
    "stash": _draw_stash,
    "pop": _draw_pop,
    "refresh": _draw_refresh,
    "system": _draw_system,
    "light": _draw_light,
    "dark": _draw_dark,
}


@lru_cache(maxsize=None)
def toolbar_icon(name: str, color: str | None = None) -> QIcon:
    """Icône de la barre d'outils, dessinée à la volée et mise en cache."""
    color = color or theme.TEXT
    drawer = _TB_DRAWERS[name]
    pixmap = QPixmap(_TB_SIZE, _TB_SIZE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    drawer(painter, color)
    painter.end()
    return QIcon(pixmap)


def clear_icon_caches() -> None:
    """Regenerate palette-dependent icons after a live theme change."""
    status_icon.cache_clear()
    toolbar_icon.cache_clear()
