"""
workspace_panel.py
Panneau "Espaces de travail" : arbre des espaces (groupes de dépôts) et
des dépôts récents. Double-cliquer un dépôt demande son ouverture à la
fenêtre principale via le signal open_repo_requested ; les boutons gèrent
la création/suppression des espaces et l'ajout/retrait de dépôts.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gitkrakit.workspace import WorkspaceError, WorkspaceManager

# rôles internes des items de l'arbre
_KIND_ROLE = Qt.UserRole
_PATH_ROLE = Qt.UserRole + 1
_KIND_WORKSPACE = "workspace"
_KIND_REPO = "repo"
_KIND_RECENT = "recent"


class WorkspacePanel(QWidget):
    open_repo_requested = Signal(str)

    def __init__(self, manager: WorkspaceManager, parent=None):
        super().__init__(parent)
        self._manager = manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree)

        buttons = QHBoxLayout()
        new_btn = QPushButton("Nouvel espace")
        new_btn.clicked.connect(self._create_workspace)
        buttons.addWidget(new_btn)

        add_btn = QPushButton("+ Dépôt")
        add_btn.clicked.connect(self._add_repo)
        buttons.addWidget(add_btn)

        remove_btn = QPushButton("Retirer")
        remove_btn.clicked.connect(self._remove_selected)
        buttons.addWidget(remove_btn)
        layout.addLayout(buttons)

        self.refresh()

    # ------------------------------------------------------------------
    # Affichage
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self.tree.clear()

        for workspace in self._manager.workspaces:
            ws_item = QTreeWidgetItem([workspace.name])
            ws_item.setData(0, _KIND_ROLE, _KIND_WORKSPACE)
            for repo_path in workspace.repos:
                ws_item.addChild(self._repo_item(repo_path, _KIND_REPO))
            self.tree.addTopLevelItem(ws_item)
            ws_item.setExpanded(True)

        if self._manager.recent:
            recent_item = QTreeWidgetItem(["Récents"])
            recent_item.setData(0, _KIND_ROLE, None)
            for repo_path in self._manager.recent:
                recent_item.addChild(self._repo_item(repo_path, _KIND_RECENT))
            self.tree.addTopLevelItem(recent_item)
            recent_item.setExpanded(True)

    @staticmethod
    def _repo_item(repo_path: str, kind: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([Path(repo_path).name or repo_path])
        item.setToolTip(0, repo_path)
        item.setData(0, _KIND_ROLE, kind)
        item.setData(0, _PATH_ROLE, repo_path)
        return item

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, _PATH_ROLE)
        if path:
            self.open_repo_requested.emit(path)

    def _create_workspace(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvel espace de travail", "Nom :")
        if not ok:
            return
        self._try(lambda: self._manager.create_workspace(name))

    def _add_repo(self) -> None:
        workspace_name = self._selected_workspace_name()
        if workspace_name is None:
            QMessageBox.information(
                self,
                "Espaces de travail",
                "Sélectionne d'abord un espace de travail (ou crée-en un).",
            )
            return
        path = QFileDialog.getExistingDirectory(self, "Choisir un dépôt Git")
        if not path:
            return
        self._try(lambda: self._manager.add_repo(workspace_name, path))

    def _remove_selected(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        kind = item.data(0, _KIND_ROLE)

        if kind == _KIND_WORKSPACE:
            name = item.text(0)
            answer = QMessageBox.question(
                self,
                "Supprimer l'espace de travail",
                f"Supprimer l'espace '{name}' ? (les dépôts sur disque ne sont pas touchés)",
            )
            if answer == QMessageBox.Yes:
                self._try(lambda: self._manager.delete_workspace(name))
        elif kind == _KIND_REPO:
            workspace_name = item.parent().text(0)
            repo_path = item.data(0, _PATH_ROLE)
            self._try(lambda: self._manager.remove_repo(workspace_name, repo_path))

    def _selected_workspace_name(self) -> str | None:
        """Espace sélectionné, ou parent du dépôt sélectionné, ou l'unique espace."""
        item = self.tree.currentItem()
        if item is not None:
            if item.data(0, _KIND_ROLE) == _KIND_WORKSPACE:
                return item.text(0)
            if item.data(0, _KIND_ROLE) == _KIND_REPO:
                return item.parent().text(0)
        if len(self._manager.workspaces) == 1:
            return self._manager.workspaces[0].name
        return None

    def _try(self, action) -> None:
        try:
            action()
        except WorkspaceError as exc:
            QMessageBox.warning(self, "Espaces de travail", str(exc))
        self.refresh()
