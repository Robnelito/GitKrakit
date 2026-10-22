"""
GitKrakit — client Git graphique minimal en Python (PySide6 + GitPython).

Lancement :
    python main.py [--tint-hue 0-359] [chemin_du_depot]

Si aucun chemin n'est fourni, utilise "Fichier > Ouvrir un dépôt" dans l'UI,
ou double-clique un dépôt dans le panneau "Espaces".
"""
from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from gitkrakit import theme
from gitkrakit.ui import MainWindow, icons


def main() -> int:
    if sys.platform == "win32":
        # Sans identifiant propre, la barre des tâches regroupe l'app sous
        # python.exe et affiche son icône à la place du logo.
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Robnelito.GitKrakit")

    parser = argparse.ArgumentParser(prog="gitkrakit")
    parser.add_argument("path", nargs="?", help="dépôt à ouvrir")
    parser.add_argument(
        "--tint-hue", type=int, help="teinte (0-359) distinguant une instance secondaire"
    )
    options, qt_args = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_args])
    app.setOrganizationName("GitKrakit")
    app.setApplicationName("GitKrakit")
    app.setWindowIcon(icons.logo_icon())
    theme.set_instance_hue(options.tint_hue)
    theme.apply_theme(app, theme.saved_theme_mode())

    window = MainWindow()

    if options.path:
        window.open_repo(options.path)

    window.show()
    window.start_update_check()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
