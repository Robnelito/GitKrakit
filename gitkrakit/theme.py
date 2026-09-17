"""
theme.py
Couleurs et feuille de style de l'application, centralisées pour que
tous les widgets (fenêtre, graphe, panneaux) partagent la même palette.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont, QFontDatabase, QPalette

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_MODES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)

UI_FONT_FAMILY = "Segoe UI"
MONO_FONT_FAMILY = "Consolas"


def configure_fonts(app) -> None:
    """Select modern installed fonts while retaining cross-platform fallbacks."""
    global UI_FONT_FAMILY, MONO_FONT_FAMILY
    available = set(QFontDatabase.families())

    ui_candidates = (
        "Bahnschrift",
        "Segoe UI Variable Text",
        "Inter",
        "Segoe UI",
        "SF Pro Text",
        "Noto Sans",
        "Ubuntu",
    )
    mono_candidates = (
        "Cascadia Mono",
        "Cascadia Code",
        "JetBrains Mono",
        "Consolas",
        "DejaVu Sans Mono",
    )
    UI_FONT_FAMILY = next(
        (family for family in ui_candidates if family in available),
        app.font().family(),
    )
    MONO_FONT_FAMILY = next(
        (family for family in mono_candidates if family in available),
        "monospace",
    )

    ui_font = QFont(UI_FONT_FAMILY)
    ui_font.setPointSizeF(10.0)
    ui_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    ui_font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    app.setFont(ui_font)

_DARK = {
    "colors": (
        "#0d1117", "#161b22", "#21262d", "#30363d", "#c9d1d9",
        "#8b949e", "#ffffff", "#58a6ff", "#1f6feb", "#172b42",
    ),
    "status": {
        "modified": "#e3b341", "added": "#3fb950", "deleted": "#f85149",
        "renamed": "#58a6ff", "copied": "#58a6ff", "untracked": "#8b949e",
        "conflict": "#f0883e", "typechange": "#e3b341",
    },
    "lanes": ["#3fb950", "#58a6ff", "#f0883e", "#db61a2", "#a371f7", "#e3b341", "#39c5cf", "#f85149"],
}

_LIGHT = {
    "colors": (
        "#f6f8fa", "#ffffff", "#f0f3f6", "#d0d7de", "#24292f",
        "#57606a", "#ffffff", "#0969da", "#0550ae", "#ddf4ff",
    ),
    "status": {
        "modified": "#9a6700", "added": "#1a7f37", "deleted": "#cf222e",
        "renamed": "#0969da", "copied": "#0969da", "untracked": "#57606a",
        "conflict": "#bc4c00", "typechange": "#9a6700",
    },
    "lanes": ["#1a7f37", "#0969da", "#bc4c00", "#bf3989", "#8250df", "#9a6700", "#1b7c83", "#cf222e"],
}

STATUS_COLORS: dict[str, str] = {}
LANE_COLORS: list[str] = []
CURRENT_EFFECTIVE_MODE = THEME_DARK


def _set_palette(palette: dict, effective_mode: str) -> None:
    global BACKGROUND, PANEL_BG, SURFACE, BORDER, TEXT, TEXT_MUTED
    global HIGHLIGHT, ACCENT, ACCENT_DIM, ACCENT_SOFT, CURRENT_EFFECTIVE_MODE
    (
        BACKGROUND, PANEL_BG, SURFACE, BORDER, TEXT, TEXT_MUTED,
        HIGHLIGHT, ACCENT, ACCENT_DIM, ACCENT_SOFT,
    ) = palette["colors"]
    STATUS_COLORS.clear()
    STATUS_COLORS.update(palette["status"])
    LANE_COLORS[:] = palette["lanes"]
    CURRENT_EFFECTIVE_MODE = effective_mode


_set_palette(_DARK, THEME_DARK)


def saved_theme_mode() -> str:
    mode = str(QSettings("GitKrakit", "GitKrakit").value("appearance/theme", THEME_SYSTEM))
    return mode if mode in THEME_MODES else THEME_SYSTEM


def save_theme_mode(mode: str) -> None:
    if mode in THEME_MODES:
        QSettings("GitKrakit", "GitKrakit").setValue("appearance/theme", mode)


def system_uses_dark_mode(app) -> bool:
    try:
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    except (AttributeError, RuntimeError):
        pass
    return app.palette().color(QPalette.Window).lightness() < 128


def resolve_theme_mode(mode: str, system_dark: bool) -> str:
    requested = mode if mode in THEME_MODES else THEME_SYSTEM
    if requested == THEME_SYSTEM:
        return THEME_DARK if system_dark else THEME_LIGHT
    return requested


def build_stylesheet() -> str:
    return f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT};
    font-family: "{UI_FONT_FAMILY}", sans-serif;
    font-size: 10pt;
}}

/* ---- listes / arbres ---- */
QListWidget, QTreeWidget {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 2px;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 3px 6px;
    border-radius: 4px;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background-color: {SURFACE};
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {ACCENT_DIM};
    color: {HIGHLIGHT};
}}

/* ---- barre latérale ---- */
QTreeWidget#sidebarTree {{
    background-color: {PANEL_BG};
    border: none;
    border-radius: 0;
    padding: 3px 7px 8px 4px;
    outline: none;
}}
QTreeWidget#sidebarTree::item {{
    color: {TEXT};
    min-height: 22px;
    padding: 2px 6px;
    margin: 1px 0;
    border: none;
    border-radius: 6px;
}}
QTreeWidget#sidebarTree::item:hover {{
    background-color: {SURFACE};
}}
QTreeWidget#sidebarTree::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {TEXT};
}}
QWidget#sidebarGroupHeader {{
    background-color: {PANEL_BG};
    border: none;
}}
QLineEdit#sidebarFilter {{
    background-color: {SURFACE};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 10px;
    font-family: "{UI_FONT_FAMILY}", sans-serif;
}}
QLineEdit#sidebarFilter:hover {{
    border-color: {BORDER};
}}
QLineEdit#sidebarFilter:focus {{
    background-color: {PANEL_BG};
    border-color: {ACCENT};
}}

/* ---- zones de texte ---- */
QTextEdit, QPlainTextEdit {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px;
    font-family: "{MONO_FONT_FAMILY}", monospace;
}}
QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QLineEdit {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    font-family: "{UI_FONT_FAMILY}", sans-serif;
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
}}
QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM};
}}

/* ---- boutons ---- */
QPushButton {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    padding: 7px 12px;
    border-radius: 6px;
}}
QPushButton:hover {{
    background-color: {BORDER};
    border-color: {TEXT_MUTED};
}}
QPushButton:pressed {{
    background-color: {ACCENT_DIM};
    color: {HIGHLIGHT};
}}
QPushButton:focus, QToolButton:focus {{
    border: 1px solid {ACCENT};
}}
QPushButton:disabled, QToolButton:disabled {{
    color: {TEXT_MUTED};
    background-color: transparent;
    border-color: {BORDER};
}}
QPushButton#primaryButton {{
    color: {HIGHLIGHT};
    background-color: {ACCENT_DIM};
    border-color: {ACCENT};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background-color: {ACCENT};
}}
QPushButton#primaryButton:disabled {{
    color: {TEXT_MUTED};
    background-color: {SURFACE};
    border-color: {BORDER};
}}
QPushButton#compactButton {{
    color: {TEXT_MUTED};
    background-color: transparent;
    border-color: transparent;
    padding: 4px 7px;
    font-size: 8.5pt;
}}
QPushButton#compactButton:hover {{
    color: {TEXT};
    background-color: {SURFACE};
    border-color: {BORDER};
}}
QPushButton#compactButton:disabled {{
    color: {TEXT_MUTED};
    background-color: transparent;
    border-color: transparent;
}}

/* ---- barre d'outils ---- */
QToolBar {{
    background-color: {PANEL_BG};
    border: none;
    padding: 3px;
    spacing: 2px;
}}
QToolBar QToolButton {{
    background: transparent;
    padding: 5px 10px;
    border-radius: 6px;
}}
QToolBar QToolButton:hover {{
    background-color: {SURFACE};
}}
QToolBar QToolButton:pressed {{
    background-color: {ACCENT_DIM};
}}
QToolBar::separator {{
    background-color: {BORDER};
    width: 1px;
    margin: 4px 6px;
}}
QPlainTextEdit#commitMessageEdit {{
    font-family: "{UI_FONT_FAMILY}", sans-serif;
}}
QPlainTextEdit#terminalOutput, QLineEdit#terminalInput {{
    font-family: "{MONO_FONT_FAMILY}", monospace;
}}

/* ---- barre d'actions principale ---- */
QToolBar#mainToolbar {{
    background-color: {PANEL_BG};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 10px;
    spacing: 0;
}}
QToolBar#mainToolbar QWidget#toolbarGroup {{
    background-color: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 9px;
}}
QToolBar#mainToolbar QWidget#toolbarGap,
QToolBar#mainToolbar QWidget#toolbarStretch {{
    background-color: transparent;
    border: none;
}}
QToolBar#mainToolbar QToolButton {{
    color: {TEXT_MUTED};
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 6px 9px;
    margin: 0;
    font-size: 9pt;
    font-weight: 500;
}}
QToolBar#mainToolbar QToolButton:hover {{
    color: {TEXT};
    background-color: {SURFACE};
    border-color: transparent;
}}
QToolBar#mainToolbar QToolButton:pressed,
QToolBar#mainToolbar QToolButton:checked {{
    color: {TEXT};
    background-color: {ACCENT_SOFT};
    border-color: {ACCENT_DIM};
}}
QToolBar#mainToolbar QToolButton:disabled {{
    color: {TEXT_MUTED};
    background-color: transparent;
    border-color: transparent;
}}
QToolBar#mainToolbar QToolButton#toolbarPrimaryButton {{
    color: {TEXT};
    background-color: {SURFACE};
    border-color: {BORDER};
    padding-left: 11px;
    padding-right: 11px;
}}
QToolBar#mainToolbar QToolButton#toolbarPrimaryButton:hover {{
    color: {TEXT};
    border-color: {TEXT_MUTED};
}}
QToolBar#mainToolbar QToolButton#toolbarUtilityButton {{
    min-width: 30px;
    padding-left: 6px;
    padding-right: 6px;
}}
QToolBar#mainToolbar QToolButton#toolbarMenuButton::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 9px;
    height: 9px;
    right: 5px;
}}
QToolBar#mainToolbar QToolButton#toolbarMenuButton {{
    padding-right: 18px;
}}

/* ---- onglets ---- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 6px 14px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}

/* ---- onglets de l'inspecteur droit ---- */
QTabWidget#inspectorTabs::pane {{
    background-color: {BACKGROUND};
    border: none;
    border-top: 1px solid {BORDER};
    top: 0;
}}
QTabBar#inspectorTabBar {{
    background-color: {PANEL_BG};
}}
QTabBar#inspectorTabBar::tab {{
    color: {TEXT_MUTED};
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    margin: 6px 3px;
    padding: 7px 12px;
    font-size: 9pt;
    font-weight: 500;
}}
QTabBar#inspectorTabBar::tab:first {{
    margin-left: 6px;
}}
QTabBar#inspectorTabBar::tab:last {{
    margin-right: 6px;
}}
QTabBar#inspectorTabBar::tab:hover {{
    color: {TEXT};
    background-color: {SURFACE};
}}
QTabBar#inspectorTabBar::tab:selected {{
    color: {TEXT};
    background-color: {ACCENT_SOFT};
    border-color: {ACCENT_DIM};
}}

/* ---- menus ---- */
QMenuBar {{
    background-color: {PANEL_BG};
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item {{
    padding: 5px 9px;
    background: transparent;
}}
QMenuBar::item:selected, QMenu::item:selected {{
    background-color: {SURFACE};
    color: {TEXT};
}}
QMenu {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 28px 6px 10px;
    border-radius: 4px;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 6px;
}}

/* ---- barres de défilement ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {TEXT_MUTED};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0; width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ---- divers ---- */
QSplitter::handle {{
    background-color: {BORDER};
}}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}

QDockWidget {{
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background-color: {PANEL_BG};
    padding: 5px 10px;
    color: {TEXT_MUTED};
}}

QStatusBar {{
    background-color: {PANEL_BG};
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER};
}}

QProgressBar {{
    background-color: {SURFACE};
    border: none;
    border-radius: 5px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 5px;
}}

QLabel {{
    color: {TEXT_MUTED};
    background: transparent;
}}

QToolTip {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}

/* ---- accueil ---- */
QWidget#welcomeRecentCard {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#welcomeRecentTitle {{
    color: {TEXT};
    font-size: 9pt;
    font-weight: 600;
}}
QLabel#welcomeRecentHint {{
    color: {TEXT_MUTED};
    font-size: 9pt;
}}
QPushButton#welcomeRecentButton {{
    color: {TEXT};
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 7px 9px;
    text-align: left;
}}
QPushButton#welcomeRecentButton:hover {{
    background-color: {SURFACE};
    border-color: {BORDER};
}}

QMessageBox, QInputDialog, QFileDialog {{
    background-color: {PANEL_BG};
}}
"""


def apply_theme(app, mode: str) -> str:
    """Apply a requested mode and return the resolved light/dark mode."""
    effective = resolve_theme_mode(mode, system_uses_dark_mode(app))
    configure_fonts(app)
    _set_palette(_DARK if effective == THEME_DARK else _LIGHT, effective)
    app.setStyleSheet(build_stylesheet())
    return effective


# Backward-compatible startup constant for callers that still import it.
DARK_STYLESHEET = build_stylesheet()
