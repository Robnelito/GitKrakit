"""Theme-aware flat SVG icons shared by every GitKrakit surface."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from gitkrakit import theme

_STATUS_LETTERS = {
    "modified": "M",
    "added": "A",
    "deleted": "D",
    "renamed": "R",
    "copied": "C",
    "untracked": "U",
    "conflict": "!",
    "typechange": "T",
}

# Every icon uses the same Lucide-like 24 px grid and stroke treatment.
_ICON_PARTS = {
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "back": '<path d="m15 18-6-6 6-6"/><path d="M9 12h10"/>',
    "forward": '<path d="m9 18 6-6-6-6"/><path d="M15 12H5"/>',
    "fetch": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    "pull": '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><path d="M6 7v10M16 4v11"/><path d="m12 11 4 4 4-4"/>',
    "push": '<path d="M12 21V9"/><path d="m7 14 5-5 5 5"/><path d="M5 3h14"/>',
    "branch": '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="6" r="2"/><path d="M6 7v10M18 8c0 5-3 7-7 7H6"/>',
    "gitflow": '<circle cx="6" cy="5" r="2"/><circle cx="18" cy="5" r="2"/><circle cx="12" cy="19" r="2"/><path d="M6 7v2c0 3 2 5 6 5s6-2 6-5V7M12 14v3"/>',
    "stash": '<rect x="3" y="5" width="18" height="4" rx="1"/><path d="M5 9v10h14V9M10 13h4"/>',
    "pop": '<path d="M5 10v9h14v-9M3 5h18v5H3zM12 16V8"/><path d="m8.5 11.5 3.5-3.5 3.5 3.5"/>',
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5M6.1 8a7 7 0 0 1 11.5-2.6L20 8M17.9 16a7 7 0 0 1-11.5 2.6L4 16"/>',
    "system": '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "light": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "dark": '<path d="M20.5 14.3A8.5 8.5 0 0 1 9.7 3.5 8.5 8.5 0 1 0 20.5 14.3Z"/>',
    "tag": '<path d="M20 13 13 20l-9-9V4h7Z"/><circle cx="8.5" cy="8.5" r="1.5"/>',
    "workspace": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "repo": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5Z"/><path d="M4 5.5v16M8 7h8"/>',
    "staging": '<path d="M9 5H4v14h16v-5"/><path d="m9 12 2 2 9-9"/>',
    "details": '<path d="M6 3h9l4 4v14H6Z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "sparkles": '<path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2Z"/><path d="m19 14 .7 2.3L22 17l-2.3.7L19 20l-.7-2.3L16 17l2.3-.7ZM5 13l.8 2.2L8 16l-2.2.8L5 19l-.8-2.2L2 16l2.2-.8Z"/>',
    "commit": '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.7 2.7L16.5 9"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>',
    "run": '<path d="m8 5 11 7-11 7Z"/>',
    "clear": '<path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "remove": '<path d="M5 12h14"/>',
    "rename": '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/>',
    "checkout": '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    "merge": '<circle cx="6" cy="5" r="2"/><circle cx="18" cy="5" r="2"/><circle cx="12" cy="19" r="2"/><path d="M6 7v2c0 4 6 4 6 8M18 7v2c0 4-6 4-6 8"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "toolbar": '<path d="M4 5h16v14H4Z"/><path d="M4 9h16M8 5v4"/>',
}


def _svg_document(parts: str, color: str) -> str:
    stroke = QColor(color).name()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" '
        f'stroke="{stroke}" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round">{parts}</svg>'
    )


def _render_svg(svg: str, size: int) -> QIcon:
    """Render at 2x and retain a logical size for sharp high-DPI display."""
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=None)
def app_icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """Return a named flat SVG icon in the active palette."""
    return _render_svg(_svg_document(_ICON_PARTS[name], color or theme.TEXT), size)


def toolbar_icon(name: str, color: str | None = None) -> QIcon:
    """Compatibility helper for the main 20 px action bar."""
    return app_icon(name, color, 20)


@lru_cache(maxsize=None)
def status_icon(status: str) -> QIcon:
    """Return a compact SVG badge for a Git file status."""
    color = QColor(theme.STATUS_COLORS.get(status, theme.TEXT_MUTED)).name()
    letter = _STATUS_LETTERS.get(status, "?")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24">'
        f'<rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="{color}" '
        f'fill-opacity=".16" stroke="{color}" stroke-width="1.5"/>'
        f'<text x="12" y="12.5" fill="{color}" text-anchor="middle" '
        'dominant-baseline="middle" font-family="Bahnschrift, sans-serif" '
        f'font-size="11" font-weight="700">{letter}</text></svg>'
    )
    return _render_svg(svg, 16)


def clear_icon_caches() -> None:
    """Regenerate palette-dependent icons after a live theme change."""
    app_icon.cache_clear()
    status_icon.cache_clear()
