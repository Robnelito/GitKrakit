"""
sidebar_panel.py
Barre latérale unique façon GitKraken : sections repliables (Espaces de
travail, Récents, Local, Remote, Tags) avec compteurs, champ de filtre en
haut, menu contextuel pour gérer espaces/dépôts/branches. Vue "muette" :
elle émet des signaux, la fenêtre principale exécute les actions Git.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gitkrakit import theme
from gitkrakit.workspace import WorkspaceError, WorkspaceManager

_KIND_ROLE = Qt.UserRole
_DATA_ROLE = Qt.UserRole + 1

K_WORKSPACE = "workspace"
K_REPO = "repo"
K_RECENT = "recent"
K_LOCAL_BRANCH = "local-branch"
K_REMOTE_BRANCH = "remote-branch"
K_TAG = "tag"
K_SECTION_WORKSPACES = "section-workspaces"


class SidebarPanel(QWidget):
    open_repo_requested = Signal(str)
    checkout_requested = Signal(str)
    branch_delete_requested = Signal(str)

    def __init__(self, manager: WorkspaceManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._local: list[str] = []
        self._remote: list[str] = []
        self._tags: list[str] = []
        self._current_branch = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filtrer…")
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().resizeSection(1, 36)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.tree)

        self.refresh()

    # ------------------------------------------------------------------
    # Données
    # ------------------------------------------------------------------
    def update_refs(
        self,
        local: list[str],
        remote: list[str],
        tags: list[str],
        current_branch: str,
    ) -> None:
        self._local = local
        self._remote = remote
        self._tags = tags
        self._current_branch = current_branch
        self.refresh()

    def refresh(self) -> None:
        self.tree.clear()

        ws_section = self._add_section("Espaces de travail", len(self._manager.workspaces))
        ws_section.setData(0, _KIND_ROLE, K_SECTION_WORKSPACES)
        for workspace in self._manager.workspaces:
            ws_item = QTreeWidgetItem([workspace.name, ""])
            ws_item.setData(0, _KIND_ROLE, K_WORKSPACE)
            ws_section.addChild(ws_item)
            for repo_path in workspace.repos:
                ws_item.addChild(self._repo_item(repo_path, K_REPO))
            ws_item.setExpanded(True)

        if self._manager.recent:
            recent_section = self._add_section("Récents", len(self._manager.recent))
            for repo_path in self._manager.recent:
                recent_section.addChild(self._repo_item(repo_path, K_RECENT))

        local_section = self._add_section("Local", len(self._local))
        for name in self._local:
            item = QTreeWidgetItem([name, ""])
            item.setData(0, _KIND_ROLE, K_LOCAL_BRANCH)
            item.setData(0, _DATA_ROLE, name)
            if name == self._current_branch:
                item.setText(0, f"✓ {name}")
                item.setForeground(0, QBrush(QColor(theme.ACCENT)))
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            local_section.addChild(item)

        remote_section = self._add_section("Remote", len(self._remote))
        for name in self._remote:
            item = QTreeWidgetItem([name, ""])
            item.setData(0, _KIND_ROLE, K_REMOTE_BRANCH)
            item.setData(0, _DATA_ROLE, name)
            remote_section.addChild(item)

        tags_section = self._add_section("Tags", len(self._tags))
        for name in self._tags:
            item = QTreeWidgetItem([name, ""])
            item.setData(0, _KIND_ROLE, K_TAG)
            item.setData(0, _DATA_ROLE, name)
            tags_section.addChild(item)

        self._apply_filter(self.filter_edit.text())

    def _add_section(self, title: str, count: int) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title.upper(), str(count) if count else ""])
        font = QFont("Segoe UI", 8)
        font.setBold(True)
        item.setFont(0, font)
        item.setForeground(0, QBrush(QColor(theme.TEXT_MUTED)))
        item.setFont(1, font)
        item.setForeground(1, QBrush(QColor(theme.TEXT_MUTED)))
        item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        self.tree.addTopLevelItem(item)
        item.setExpanded(True)
        return item

    @staticmethod
    def _repo_item(repo_path: str, kind: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([Path(repo_path).name or repo_path, ""])
        item.setToolTip(0, repo_path)
        item.setData(0, _KIND_ROLE, kind)
        item.setData(0, _DATA_ROLE, repo_path)
        return item

    # ------------------------------------------------------------------
    # Filtre
    # ------------------------------------------------------------------
    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            """Cache les feuilles qui ne matchent pas ; retourne True si
            l'item (ou un descendant) reste visible."""
            if item.childCount() == 0:
                visible = not needle or needle in item.text(0).lower()
                item.setHidden(not visible)
                return visible
            any_child = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    any_child = True
            item.setHidden(not any_child)
            return any_child

        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------
    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        kind = item.data(0, _KIND_ROLE)
        data = item.data(0, _DATA_ROLE)
        if kind in (K_REPO, K_RECENT):
            self.open_repo_requested.emit(data)
        elif kind == K_LOCAL_BRANCH:
            self.checkout_requested.emit(data)

    def _show_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        kind = item.data(0, _KIND_ROLE) if item else None
        data = item.data(0, _DATA_ROLE) if item else None

        if kind == K_SECTION_WORKSPACES or item is None:
            menu.addAction("Nouvel espace de travail…", self._create_workspace)
        elif kind == K_WORKSPACE:
            name = item.text(0)
            menu.addAction("Ajouter un dépôt…", lambda: self._add_repo(name))
            menu.addAction("Renommer…", lambda: self._rename_workspace(name))
            menu.addAction("Supprimer l'espace", lambda: self._delete_workspace(name))
        elif kind == K_REPO:
            workspace_name = item.parent().text(0)
            menu.addAction("Ouvrir", lambda: self.open_repo_requested.emit(data))
            menu.addAction(
                "Retirer de l'espace",
                lambda: self._try(lambda: self._manager.remove_repo(workspace_name, data)),
            )
        elif kind == K_RECENT:
            menu.addAction("Ouvrir", lambda: self.open_repo_requested.emit(data))
        elif kind == K_LOCAL_BRANCH:
            menu.addAction("Checkout", lambda: self.checkout_requested.emit(data))
            menu.addAction("Supprimer la branche", lambda: self._confirm_delete_branch(data))
        else:
            return

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Actions espaces de travail
    # ------------------------------------------------------------------
    def _create_workspace(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvel espace de travail", "Nom :")
        if ok:
            self._try(lambda: self._manager.create_workspace(name))

    def _rename_workspace(self, old_name: str) -> None:
        name, ok = QInputDialog.getText(
            self, "Renommer l'espace", "Nouveau nom :", text=old_name
        )
        if ok:
            self._try(lambda: self._manager.rename_workspace(old_name, name))

    def _add_repo(self, workspace_name: str) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dépôt Git")
        if path:
            self._try(lambda: self._manager.add_repo(workspace_name, path))

    def _delete_workspace(self, name: str) -> None:
        answer = QMessageBox.question(
            self,
            "Supprimer l'espace de travail",
            f"Supprimer l'espace '{name}' ? (les dépôts sur disque ne sont pas touchés)",
        )
        if answer == QMessageBox.Yes:
            self._try(lambda: self._manager.delete_workspace(name))

    def _confirm_delete_branch(self, name: str) -> None:
        answer = QMessageBox.question(
            self, "Supprimer la branche", f"Supprimer la branche locale '{name}' ?"
        )
        if answer == QMessageBox.Yes:
            self.branch_delete_requested.emit(name)

    def _try(self, action) -> None:
        try:
            action()
        except WorkspaceError as exc:
            QMessageBox.warning(self, "Espaces de travail", str(exc))
        self.refresh()
