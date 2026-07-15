"""
theme.py
Couleurs et feuille de style de l'application, centralisées pour que
tous les widgets (fenêtre, graphe, panneaux) partagent la même palette.
"""
from __future__ import annotations

# Palette sombre (inspirée de GitHub Dark)
BACKGROUND = "#0d1117"
PANEL_BG = "#161b22"
SURFACE = "#21262d"
BORDER = "#30363d"
TEXT = "#c9d1d9"
TEXT_MUTED = "#8b949e"
HIGHLIGHT = "#ffffff"
ACCENT = "#58a6ff"
ACCENT_DIM = "#1f6feb"

# Couleur du texte des fichiers selon leur état (panneau de staging)
STATUS_COLORS = {
    "modified": "#e3b341",
    "added": "#3fb950",
    "deleted": "#f85149",
    "renamed": "#58a6ff",
    "copied": "#58a6ff",
    "untracked": "#8b949e",
    "conflict": "#f0883e",
    "typechange": "#e3b341",
}

# Palette de couleurs cycliques pour les lanes du graphe (façon GitKraken)
LANE_COLORS = [
    "#3fb950",  # vert
    "#58a6ff",  # bleu
    "#f0883e",  # orange
    "#db61a2",  # rose
    "#a371f7",  # violet
    "#e3b341",  # jaune
    "#39c5cf",  # cyan
    "#f85149",  # rouge
]

DARK_STYLESHEET = f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT};
    font-family: "Segoe UI", sans-serif;
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
    background-color: rgba(31, 111, 235, 0.45);
    color: {HIGHLIGHT};
}}

/* ---- zones de texte ---- */
QTextEdit, QPlainTextEdit {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px;
    font-family: Consolas, "Courier New", monospace;
}}
QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QLineEdit {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    font-family: Consolas, "Courier New", monospace;
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
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
    color: {HIGHLIGHT};
    border-bottom: 2px solid {ACCENT};
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
    color: {HIGHLIGHT};
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

QMessageBox, QInputDialog, QFileDialog {{
    background-color: {PANEL_BG};
}}
"""
