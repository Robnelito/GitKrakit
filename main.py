"""
GitKrakit — client Git graphique minimal en Python (PySide6 + GitPython).

Lancement :
    python main.py [chemin_du_depot]

Si aucun chemin n'est fourni, utilise "Fichier > Ouvrir un dépôt" dans l'UI.
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from main_window import MainWindow
from git_backend import GitBackendError


DARK_STYLESHEET = """
QMainWindow, QWidget { background-color: #0d1117; color: #c9d1d9; }
QListWidget, QTextEdit, QPlainTextEdit, QLineEdit {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
}
QPushButton {
    background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d;
    padding: 4px 10px; border-radius: 4px;
}
QPushButton:hover { background-color: #30363d; }
QToolBar { background-color: #161b22; border: none; }
QTabWidget::pane { border: 1px solid #30363d; }
QLabel { color: #8b949e; }
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()

    if len(sys.argv) > 1:
        try:
            window.backend.open(sys.argv[1])
            window.setWindowTitle(f"GitKrakit — {sys.argv[1]}")
            window.refresh_all()
        except GitBackendError as exc:
            print(f"Erreur au démarrage: {exc}", file=sys.stderr)

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
