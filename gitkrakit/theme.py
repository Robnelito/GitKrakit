"""
theme.py
Couleurs et feuille de style de l'application, centralisées pour que
tous les widgets (fenêtre, graphe, panneaux) partagent la même palette.
"""
from __future__ import annotations

# Palette sombre (inspirée de GitHub Dark)
BACKGROUND = "#0d1117"
PANEL_BG = "#161b22"
BORDER = "#30363d"
TEXT = "#c9d1d9"
TEXT_MUTED = "#8b949e"
HIGHLIGHT = "#ffffff"

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
QMainWindow, QWidget {{ background-color: {BACKGROUND}; color: {TEXT}; }}
QListWidget, QTreeWidget, QTextEdit, QPlainTextEdit, QLineEdit {{
    background-color: {PANEL_BG}; color: {TEXT}; border: 1px solid {BORDER};
}}
QPushButton {{
    background-color: #21262d; color: {TEXT}; border: 1px solid {BORDER};
    padding: 4px 10px; border-radius: 4px;
}}
QPushButton:hover {{ background-color: {BORDER}; }}
QToolBar {{ background-color: {PANEL_BG}; border: none; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; }}
QLabel {{ color: {TEXT_MUTED}; }}
"""
