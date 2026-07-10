"""
branches_panel.py
Panneau listant branches locales, branches distantes et tags.
Double-cliquer une branche locale demande un checkout via le signal
checkout_requested ; le panneau ne touche jamais au backend lui-même.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class BranchesPanel(QWidget):
    checkout_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Branches locales"))
        self.branch_list = QListWidget()
        self.branch_list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.branch_list)

        layout.addWidget(QLabel("Branches distantes"))
        self.remote_branch_list = QListWidget()
        layout.addWidget(self.remote_branch_list)

        layout.addWidget(QLabel("Tags"))
        self.tag_list = QListWidget()
        layout.addWidget(self.tag_list)

    def update_data(
        self,
        local: list[str],
        remote: list[str],
        tags: list[str],
        current_branch: str,
    ) -> None:
        self.branch_list.clear()
        for name in local:
            label = f"* {name}" if name == current_branch else name
            self.branch_list.addItem(QListWidgetItem(label))

        self.remote_branch_list.clear()
        for name in remote:
            self.remote_branch_list.addItem(QListWidgetItem(name))

        self.tag_list.clear()
        for name in tags:
            self.tag_list.addItem(QListWidgetItem(name))

    def _on_double_click(self, item: QListWidgetItem) -> None:
        self.checkout_requested.emit(item.text().lstrip("* ").strip())
