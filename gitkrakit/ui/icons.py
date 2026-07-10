"""
icons.py
Icônes générées par code (aucun fichier d'asset) : pastille carrée arrondie
colorée avec la lettre de l'état du fichier (M/A/D/R…), façon GitKraken.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

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

    font = QFont("Segoe UI", 8)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, _LETTERS.get(status, "?"))
    painter.end()

    return QIcon(pixmap)
