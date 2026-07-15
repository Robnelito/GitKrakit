"""
terminal_dock.py
Mini-terminal git intégré (dock du bas). Émet command_entered avec les
arguments saisis ; la fenêtre principale exécute la commande via le
backend et renvoie la sortie avec append_output().
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gitkrakit.core import split_command


class TerminalDock(QDockWidget):
    command_entered = Signal(list)  # list[str] : arguments après "git"

    def __init__(self, parent=None):
        super().__init__("Terminal git intégré", parent)

        dock_widget = QWidget()
        layout = QVBoxLayout(dock_widget)

        self.terminal_output = QPlainTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setMinimumHeight(70)
        self.terminal_output.setMaximumHeight(130)
        self.terminal_output.setPlaceholderText(
            "Les commandes Git et leur sortie apparaîtront ici."
        )
        layout.addWidget(self.terminal_output)

        input_row = QHBoxLayout()
        self.terminal_input = QLineEdit()
        self.terminal_input.setPlaceholderText(
            'ex: status, log --oneline -5, commit -m "mon message"'
        )
        self.terminal_input.setClearButtonEnabled(True)
        self.terminal_input.setAccessibleName("Sous-commande Git")
        self.terminal_input.returnPressed.connect(self._submit)
        input_row.addWidget(QLabel("git"))
        input_row.addWidget(self.terminal_input)
        run_btn = QPushButton("Exécuter")
        run_btn.setToolTip("Exécuter la sous-commande Git (Entrée)")
        run_btn.clicked.connect(self._submit)
        input_row.addWidget(run_btn)

        clear_btn = QPushButton("Effacer")
        clear_btn.setToolTip("Effacer l'historique du terminal")
        clear_btn.clicked.connect(self.terminal_output.clear)
        input_row.addWidget(clear_btn)
        layout.addLayout(input_row)

        self.setWidget(dock_widget)

    def append_output(self, text: str) -> None:
        self.terminal_output.appendPlainText(text)

    def _submit(self) -> None:
        raw = self.terminal_input.text().strip()
        if not raw:
            return
        self.append_output(f"$ git {raw}")
        try:
            args = split_command(raw)
        except ValueError as exc:
            self.append_output(f"Erreur: {exc}")
            return
        self.terminal_input.clear()
        self.command_entered.emit(args)
