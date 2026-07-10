"""
GitKrakit — client Git graphique minimal en Python (PySide6 + GitPython).

Lancement :
    python main.py [chemin_du_depot]

Si aucun chemin n'est fourni, utilise "Fichier > Ouvrir un dépôt" dans l'UI,
ou double-clique un dépôt dans le panneau "Espaces".
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from gitkrakit.theme import DARK_STYLESHEET
from gitkrakit.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()

    if len(sys.argv) > 1:
        window.open_repo(sys.argv[1])

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
