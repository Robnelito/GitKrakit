"""
gitflow_dialog.py
Boîte de dialogue de configuration Git Flow : choix de la branche principale
et de la branche de développement.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
)

from gitkrakit import theme
from gitkrakit.ui.icons import app_icon


class GitFlowDialog(QDialog):
    def __init__(
        self,
        main: str,
        develop: str,
        branches: list[str],
        initialized: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Configurer Git Flow" if initialized else "Initialiser Git Flow")
        self.setWindowIcon(app_icon("gitflow", theme.ACCENT, 32))
        self.setModal(True)
        self.setMinimumWidth(380)

        self._main = self._branch_combo(main, branches)
        self._develop = self._branch_combo(develop, branches)

        form = QFormLayout()
        form.addRow("Branche principale", self._main)
        form.addRow("Branche de développement", self._develop)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._buttons.button(QDialogButtonBox.Ok).setText(
            "Enregistrer" if initialized else "Initialiser"
        )
        self._buttons.button(QDialogButtonBox.Cancel).setText("Annuler")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(self._buttons)

        self._main.currentTextChanged.connect(self._update_ok_state)
        self._develop.currentTextChanged.connect(self._update_ok_state)
        self._update_ok_state()

    @staticmethod
    def _branch_combo(current: str, branches: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(branches)
        combo.setCurrentText(current)
        return combo

    def _update_ok_state(self) -> None:
        main, develop = self.values()
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(main) and bool(develop) and main != develop
        )

    def values(self) -> tuple[str, str]:
        return self._main.currentText().strip(), self._develop.currentText().strip()
