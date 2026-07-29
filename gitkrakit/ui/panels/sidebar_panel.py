"""
sidebar_panel.py
Barre latérale scindée en deux zones bien distinctes, façon GitKraken :

  - DÉPÔTS      : gestion de répertoires sur disque (espaces de travail,
                  dépôts récents) — n'a aucune notion d'objet Git.
  - OBJETS GIT  : références du dépôt actuellement ouvert (Git Flow,
                  branches locales/distantes, tags) — n'a aucune notion
                  de système de fichiers.

Chaque zone est un QTreeWidget séparé avec son propre bandeau de titre ;
un QSplitter vertical permet de redimensionner l'une par rapport à
l'autre. Vue "muette" : elle émet des signaux, la fenêtre principale
exécute les actions Git.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gitkrakit import theme
from gitkrakit.core import GitFlowStatus
from gitkrakit.ui.icons import app_icon
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
K_SECTION_GITFLOW = "section-gitflow"
K_GITFLOW_INIT = "gitflow-init"
K_GF_FEATURE = "feature"
K_GF_RELEASE = "release"
K_GF_HOTFIX = "hotfix"

# Séparateur de chemin d'arborescence : un caractère de contrôle, pour qu'un
# nom de branche contenant '/' ne puisse pas fabriquer la clé d'un autre nœud.
_PATH_SEPARATOR = "\x1f"


def _expansion_key(path: tuple[str, ...]) -> str:
    return _PATH_SEPARATOR.join(path)


def _same_path(a: str, b: str) -> bool:
    """Compare deux chemins de dépôt en ignorant séparateurs/casse
    (Windows n'est pas sensible à la casse, et les chemins stockés en
    JSON peuvent différer d'un `/` ou `\\` près)."""
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _make_tree() -> QTreeWidget:
    tree = QTreeWidget()
    tree.setObjectName("sidebarTree")
    tree.setColumnCount(2)
    tree.setHeaderHidden(True)
    tree.setRootIsDecorated(True)
    tree.setUniformRowHeights(True)
    tree.setAnimated(True)
    tree.setIndentation(17)
    tree.setIconSize(QSize(16, 16))
    tree.setTextElideMode(Qt.ElideRight)
    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    # colonne 0 (nom) extensible, colonne 1 (compteur) étroite et fixe
    tree.header().setStretchLastSection(False)
    tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
    tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
    tree.header().resizeSection(1, 58)
    return tree


def _group_header(text: str, accent: str) -> QWidget:
    """Compact title row separating repositories from Git references."""
    header = QWidget()
    header.setObjectName("sidebarGroupHeader")
    layout = QHBoxLayout(header)
    layout.setContentsMargins(12, 9, 10, 6)
    layout.setSpacing(8)

    dot = QLabel()
    dot.setObjectName("sidebarAccentDot")
    dot.setFixedSize(5, 5)
    dot.setStyleSheet(f"background-color: {accent}; border-radius: 2px;")
    layout.addWidget(dot, alignment=Qt.AlignVCenter)

    label = QLabel(text)
    label.setObjectName("sidebarGroupTitle")
    font = QFont(theme.UI_FONT_FAMILY, 9)
    font.setWeight(QFont.DemiBold)
    label.setFont(font)
    label.setStyleSheet(f"color: {theme.TEXT}; background: transparent;")
    layout.addWidget(label)
    layout.addStretch(1)
    return header


def _style_group_header(header: QWidget, accent: str) -> None:
    dot = header.findChild(QLabel, "sidebarAccentDot")
    label = header.findChild(QLabel, "sidebarGroupTitle")
    if dot is not None:
        dot.setStyleSheet(f"background-color: {accent}; border-radius: 2px;")
    if label is not None:
        label.setStyleSheet(f"color: {theme.TEXT}; background: transparent;")


class SidebarPanel(QWidget):
    open_repo_requested = Signal(str)
    checkout_requested = Signal(str)
    branch_delete_requested = Signal(str)
    merge_requested = Signal(str)                # branche source à fusionner dans la courante
    gitflow_init_requested = Signal()
    gitflow_start_requested = Signal(str)        # kind: feature | release | hotfix
    gitflow_finish_requested = Signal(str, str)  # (kind, nom court)

    def __init__(self, manager: WorkspaceManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._local: list[str] = []
        self._remote: list[str] = []
        self._tags: list[str] = []
        self._current_branch = ""
        self._gitflow: GitFlowStatus | None = None
        self._repo_open = False
        self._active_repo_path: str | None = None
        self._ahead_behind: dict[str, tuple[int, int]] = {}
        # Dossiers refermés par l'utilisateur : mémorisés par chemin pour
        # survivre à la reconstruction de l'arbre à chaque rafraîchissement.
        self._collapsed_refs: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.filter_edit = QLineEdit()
        self.filter_edit.setObjectName("sidebarFilter")
        self.filter_edit.setPlaceholderText("Filtrer…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setAccessibleName("Filtrer la barre latérale")
        self.filter_edit.setToolTip("Filtrer simultanément les dépôts, branches et tags")
        self.filter_edit.setContentsMargins(0, 0, 0, 0)
        self.filter_edit.textChanged.connect(self._apply_filter)
        margin_wrap = QWidget()
        margin_layout = QVBoxLayout(margin_wrap)
        margin_layout.setContentsMargins(10, 10, 10, 4)
        margin_layout.addWidget(self.filter_edit)
        layout.addWidget(margin_wrap)

        # --- zone 1 : gestion de répertoires (espaces de travail, récents) ---
        repos_widget = QWidget()
        repos_layout = QVBoxLayout(repos_widget)
        repos_layout.setContentsMargins(0, 0, 0, 0)
        repos_layout.setSpacing(0)
        self._repos_header = _group_header("Dépôts", theme.ACCENT)
        repos_layout.addWidget(self._repos_header)
        self.repos_tree = _make_tree()
        self.repos_tree.setAccessibleName("Dépôts et espaces de travail")
        self.repos_tree.setToolTip("Double-clique un dépôt pour l'ouvrir")
        self.repos_tree.itemDoubleClicked.connect(self._on_double_click)
        self.repos_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.repos_tree.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self.repos_tree, pos)
        )
        repos_layout.addWidget(self.repos_tree)

        # --- zone 2 : objets Git du dépôt ouvert (gitflow, branches, tags) ---
        refs_widget = QWidget()
        refs_layout = QVBoxLayout(refs_widget)
        refs_layout.setContentsMargins(0, 0, 0, 0)
        refs_layout.setSpacing(0)
        self._refs_header = _group_header("Branches et tags", theme.LANE_COLORS[0])
        refs_layout.addWidget(self._refs_header)
        self.refs_tree = _make_tree()
        self.refs_tree.setAccessibleName("Branches, tags et Git Flow")
        self.refs_tree.setToolTip("Double-clique une branche locale pour l'extraire")
        self.refs_tree.itemDoubleClicked.connect(self._on_double_click)
        self.refs_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.refs_tree.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self.refs_tree, pos)
        )
        refs_layout.addWidget(self.refs_tree)

        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.addWidget(repos_widget)
        self._splitter.addWidget(refs_widget)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([180, 420])
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {theme.BORDER}; }}"
        )
        layout.addWidget(self._splitter, stretch=1)

        self.refresh()

    def apply_theme(self) -> None:
        _style_group_header(self._repos_header, theme.ACCENT)
        _style_group_header(self._refs_header, theme.LANE_COLORS[0])
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {theme.BORDER}; }}"
        )
        self.refresh()

    # ------------------------------------------------------------------
    # Données
    # ------------------------------------------------------------------
    def set_active_repo(self, path: str) -> None:
        """Marque `path` comme dépôt actif dans la zone DÉPÔTS (espaces de
        travail + récents)."""
        self._active_repo_path = path
        self._refresh_repos_tree()
        self._apply_filter(self.filter_edit.text())

    def update_refs(
        self,
        local: list[str],
        remote: list[str],
        tags: list[str],
        current_branch: str,
        gitflow: GitFlowStatus | None = None,
        ahead_behind: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        self._local = local
        self._remote = remote
        self._tags = tags
        self._current_branch = current_branch
        self._gitflow = gitflow
        self._ahead_behind = ahead_behind or {}
        self._repo_open = True
        self.refresh()

    def refresh(self) -> None:
        self._refresh_repos_tree()
        self._refresh_refs_tree()
        self._apply_filter(self.filter_edit.text())

    def _refresh_repos_tree(self) -> None:
        tree = self.repos_tree
        tree.clear()
        active_item: QTreeWidgetItem | None = None

        ws_section = self._add_section(
            tree, "Espaces de travail", len(self._manager.workspaces)
        )
        ws_section.setData(0, _KIND_ROLE, K_SECTION_WORKSPACES)
        for workspace in self._manager.workspaces:
            ws_item = QTreeWidgetItem([workspace.name, ""])
            ws_item.setData(0, _KIND_ROLE, K_WORKSPACE)
            ws_item.setIcon(0, app_icon("workspace", theme.TEXT_MUTED, 16))
            ws_section.addChild(ws_item)
            for repo_path in workspace.repos:
                item = self._repo_item(repo_path, K_REPO)
                ws_item.addChild(item)
                if self._mark_active_repo(item, repo_path):
                    active_item = item
            ws_item.setExpanded(True)

        if self._manager.recent:
            recent_section = self._add_section(tree, "Récents", len(self._manager.recent))
            for repo_path in self._manager.recent:
                item = self._repo_item(repo_path, K_RECENT)
                recent_section.addChild(item)
                if self._mark_active_repo(item, repo_path):
                    active_item = item

        if active_item is not None:
            tree.scrollToItem(active_item)

    def _remember_refs_expansion(self) -> None:
        """Snapshot the folders the user closed, before the tree is rebuilt."""
        collapsed: set[str] = set()
        seen_folder = False

        def visit(item: QTreeWidgetItem, path: tuple[str, ...]) -> None:
            nonlocal seen_folder
            if item.childCount() == 0:  # une feuille ne se replie pas
                return
            seen_folder = True
            if not item.isExpanded():
                collapsed.add(_expansion_key(path))
            for index in range(item.childCount()):
                child = item.child(index)
                visit(child, path + (child.text(0),))

        tree = self.refs_tree
        for index in range(tree.topLevelItemCount()):
            section = tree.topLevelItem(index)
            visit(section, (section.text(0),))

        # Un arbre sans dossier (dépôt fermé, placeholder) ne dit rien des
        # choix de l'utilisateur : on garde la mémoire précédente.
        if seen_folder:
            self._collapsed_refs = collapsed

    def _restore_expansion(self, item: QTreeWidgetItem, path: tuple[str, ...]) -> None:
        """Re-apply the last collapse choice; a folder never seen opens."""
        item.setExpanded(_expansion_key(path) not in self._collapsed_refs)

    def _refresh_refs_tree(self) -> None:
        tree = self.refs_tree
        self._remember_refs_expansion()
        tree.clear()

        if not self._repo_open:
            placeholder = QTreeWidgetItem(["Ouvre un dépôt pour voir ses branches", ""])
            placeholder.setForeground(0, QBrush(QColor(theme.TEXT_MUTED)))
            tree.addTopLevelItem(placeholder)
            return

        self._build_gitflow_section(tree)

        # "origin/HEAD" est un alias symbolique (pas une vraie branche) :
        # pur bruit dans la liste, on l'exclut.
        remote_names = [n for n in self._remote if n.rsplit("/", 1)[-1] != "HEAD"]

        local_section = self._add_section(tree, "Local", len(self._local))
        self._add_branch_tree(
            local_section, K_LOCAL_BRANCH, self._local, mark_current=True, path=("Local",)
        )
        self._restore_expansion(local_section, ("Local",))

        remote_section = self._add_section(tree, "Remote", len(remote_names))
        self._add_branch_tree(
            remote_section, K_REMOTE_BRANCH, remote_names, mark_current=False, path=("Remote",)
        )
        self._restore_expansion(remote_section, ("Remote",))

        tags_section = self._add_section(tree, "Tags", len(self._tags))
        self._add_branch_tree(
            tags_section, K_TAG, self._tags, mark_current=False, path=("Tags",)
        )
        self._restore_expansion(tags_section, ("Tags",))

    def _build_gitflow_section(self, tree: QTreeWidget) -> None:
        status = self._gitflow

        if status is None:
            section = self._add_section(tree, "Git Flow", 0)
            section.setData(0, _KIND_ROLE, K_SECTION_GITFLOW)
            init_item = QTreeWidgetItem(["Initialiser Git Flow…", ""])
            init_item.setData(0, _KIND_ROLE, K_GITFLOW_INIT)
            init_item.setForeground(0, QBrush(QColor(theme.ACCENT)))
            section.addChild(init_item)
            self._restore_expansion(section, ("Git Flow",))
            return

        total = len(status.features) + len(status.releases) + len(status.hotfixes)
        section = self._add_section(tree, "Git Flow", total)
        section.setData(0, _KIND_ROLE, K_SECTION_GITFLOW)

        for branch in (status.config.develop, status.config.main):
            item = QTreeWidgetItem([branch, ""])
            item.setData(0, _KIND_ROLE, K_LOCAL_BRANCH)
            item.setData(0, _DATA_ROLE, branch)
            item.setIcon(0, app_icon("branch", theme.TEXT_MUTED, 16))
            self._mark_if_current(item, branch)
            self._set_sync_badge(item, branch)
            section.addChild(item)

        for kind, label, names in (
            (K_GF_FEATURE, "feature", status.features),
            (K_GF_RELEASE, "release", status.releases),
            (K_GF_HOTFIX, "hotfix", status.hotfixes),
        ):
            folder = QTreeWidgetItem([label, str(len(names)) if names else ""])
            folder.setForeground(0, QBrush(QColor(theme.TEXT_MUTED)))
            folder.setForeground(1, QBrush(QColor(theme.TEXT_MUTED)))
            folder.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            section.addChild(folder)
            for name in names:
                child = QTreeWidgetItem([name, ""])
                child.setData(0, _KIND_ROLE, kind)
                child.setData(0, _DATA_ROLE, name)
                child.setIcon(0, app_icon("branch", theme.TEXT_MUTED, 16))
                full_name = self._gitflow_full_name(kind, name)
                self._mark_if_current(child, full_name)
                self._set_sync_badge(child, full_name)
                folder.addChild(child)
            self._restore_expansion(folder, ("Git Flow", label))

        self._restore_expansion(section, ("Git Flow",))

    def _add_branch_tree(
        self,
        parent: QTreeWidgetItem,
        kind: str,
        names: list[str],
        mark_current: bool,
        path: tuple[str, ...] = (),
    ) -> None:
        """Regroupe des noms de branches/tags en dossiers selon les
        segments séparés par '/' (ex: "origin/feature/x" -> origin >
        feature > x), au lieu d'une liste plate de chaînes à rallonge."""
        root: dict = {}
        for name in names:
            self._insert_branch_path(root, name.split("/"), name)
        self._render_branch_tree(parent, root, kind, mark_current, path)

    @staticmethod
    def _insert_branch_path(node: dict, parts: list[str], full_name: str) -> None:
        if len(parts) == 1:
            node.setdefault("__leaves__", []).append((parts[0], full_name))
            return
        child = node.setdefault(parts[0], {})
        SidebarPanel._insert_branch_path(child, parts[1:], full_name)

    def _render_branch_tree(
        self,
        parent: QTreeWidgetItem,
        node: dict,
        kind: str,
        mark_current: bool,
        path: tuple[str, ...] = (),
    ) -> None:
        for key in sorted(k for k in node if k != "__leaves__"):
            child_node = node[key]
            folder = QTreeWidgetItem([key, str(self._count_leaves(child_node))])
            folder.setForeground(0, QBrush(QColor(theme.TEXT_MUTED)))
            folder.setForeground(1, QBrush(QColor(theme.TEXT_MUTED)))
            folder.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            parent.addChild(folder)
            folder_path = path + (key,)
            self._render_branch_tree(folder, child_node, kind, mark_current, folder_path)
            self._restore_expansion(folder, folder_path)

        for label, full_name in sorted(node.get("__leaves__", [])):
            item = QTreeWidgetItem([label, ""])
            item.setData(0, _KIND_ROLE, kind)
            item.setData(0, _DATA_ROLE, full_name)
            icon_kind = "tag" if kind == K_TAG else "branch"
            icon_color = theme.LANE_COLORS[6] if kind == K_REMOTE_BRANCH else theme.TEXT_MUTED
            item.setIcon(0, app_icon(icon_kind, icon_color, 16))
            if mark_current:
                self._mark_if_current(item, full_name)
                self._set_sync_badge(item, full_name)
            parent.addChild(item)

    @staticmethod
    def _count_leaves(node: dict) -> int:
        total = len(node.get("__leaves__", []))
        for key, child in node.items():
            if key != "__leaves__":
                total += SidebarPanel._count_leaves(child)
        return total

    def _gitflow_full_name(self, kind: str, short_name: str) -> str:
        assert self._gitflow is not None
        prefix = {
            K_GF_FEATURE: self._gitflow.config.feature_prefix,
            K_GF_RELEASE: self._gitflow.config.release_prefix,
            K_GF_HOTFIX: self._gitflow.config.hotfix_prefix,
        }[kind]
        return prefix + short_name

    def _mark_active_repo(self, item: QTreeWidgetItem, repo_path: str) -> bool:
        """Style l'item comme dépôt actif (coché, gras, accent, fond
        teinté) s'il correspond au dépôt actuellement ouvert. Retourne
        True si c'était le cas, pour que l'appelant sache où défiler."""
        if self._active_repo_path is None or not _same_path(repo_path, self._active_repo_path):
            return False
        item.setIcon(0, app_icon("repo", theme.ACCENT, 16))
        item.setForeground(0, QBrush(QColor(theme.ACCENT)))
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        tint = QColor(theme.ACCENT)
        tint.setAlpha(35)
        item.setBackground(0, QBrush(tint))
        item.setBackground(1, QBrush(tint))
        item.setToolTip(0, f"{repo_path}  (dépôt actif)")
        return True

    def _mark_if_current(self, item: QTreeWidgetItem, branch: str) -> None:
        if branch == self._current_branch:
            item.setIcon(0, app_icon("branch", theme.ACCENT, 16))
            item.setForeground(0, QBrush(QColor(theme.ACCENT)))
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            tint = QColor(theme.ACCENT)
            tint.setAlpha(20)
            item.setBackground(0, QBrush(tint))
            item.setBackground(1, QBrush(tint))
            item.setToolTip(0, f"{branch} — branche actuelle")

    def _set_sync_badge(self, item: QTreeWidgetItem, branch_name: str) -> None:
        """Ajoute, dans la colonne de droite, un indicateur ↓N/↑N quand la
        branche a divergé de son amont (nécessite pull/push). Rien si elle
        n'a pas d'amont ou si elle est déjà à jour."""
        ahead, behind = self._ahead_behind.get(branch_name, (0, 0))
        if not ahead and not behind:
            return

        parts = []
        if behind:
            parts.append(f"↓{behind}")  # ↓N : à tirer (pull)
        if ahead:
            parts.append(f"↑{ahead}")  # ↑N : à pousser (push)

        if behind and ahead:
            color = theme.LANE_COLORS[4]  # violet : a divergé (pull ET push)
            tip = f"{behind} commit(s) à tirer, {ahead} à pousser — la branche a divergé"
        elif behind:
            color = theme.LANE_COLORS[2]  # orange : pull nécessaire
            tip = f"{behind} commit(s) en retard sur l'amont — pull nécessaire"
        else:
            color = theme.LANE_COLORS[0]  # vert : push nécessaire
            tip = f"{ahead} commit(s) en avance sur l'amont — push nécessaire"

        item.setText(1, " ".join(parts))
        item.setForeground(1, QBrush(QColor(color)))
        font = item.font(1)
        font.setBold(True)
        item.setFont(1, font)
        item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        item.setToolTip(1, tip)

    @staticmethod
    def _add_section(tree: QTreeWidget, title: str, count: int) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title, str(count) if count else ""])
        font = QFont(theme.UI_FONT_FAMILY, 8)
        font.setWeight(QFont.DemiBold)
        item.setFont(0, font)
        item.setForeground(0, QBrush(QColor(theme.TEXT_MUTED)))
        item.setFont(1, font)
        item.setForeground(1, QBrush(QColor(theme.TEXT_MUTED)))
        item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        tree.addTopLevelItem(item)
        item.setExpanded(True)
        return item

    @staticmethod
    def _repo_item(repo_path: str, kind: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([Path(repo_path).name or repo_path, ""])
        item.setIcon(0, app_icon("repo", theme.TEXT_MUTED, 16))
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

        for tree in (self.repos_tree, self.refs_tree):
            for i in range(tree.topLevelItemCount()):
                filter_item(tree.topLevelItem(i))

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
        elif kind in (K_GF_FEATURE, K_GF_RELEASE, K_GF_HOTFIX):
            self.checkout_requested.emit(self._gitflow_full_name(kind, data))
        elif kind == K_GITFLOW_INIT:
            self.gitflow_init_requested.emit()

    def _add_merge_action(self, menu: QMenu, source: str) -> None:
        """Ajoute « Merge <source> dans <branche courante> » (sauf sur la branche courante)."""
        if not self._current_branch or source == self._current_branch:
            return
        menu.addAction(
            app_icon("merge"),
            f"Merge {source} dans {self._current_branch}",
            lambda: self.merge_requested.emit(source),
        )

    def _show_context_menu(self, tree: QTreeWidget, pos) -> None:
        item = tree.itemAt(pos)
        menu = QMenu(self)
        kind = item.data(0, _KIND_ROLE) if item else None
        data = item.data(0, _DATA_ROLE) if item else None

        if kind == K_SECTION_WORKSPACES or (item is None and tree is self.repos_tree):
            menu.addAction(app_icon("plus"), "Nouvel espace de travail…", self._create_workspace)
        elif kind == K_WORKSPACE:
            name = item.text(0)
            menu.addAction(app_icon("plus"), "Ajouter un dépôt…", lambda: self._add_repo(name))
            menu.addAction(app_icon("rename"), "Renommer…", lambda: self._rename_workspace(name))
            menu.addAction(
                app_icon("clear"), "Supprimer l'espace", lambda: self._delete_workspace(name)
            )
        elif kind == K_REPO:
            workspace_name = item.parent().text(0)
            menu.addAction(app_icon("open"), "Ouvrir", lambda: self.open_repo_requested.emit(data))
            menu.addAction(
                app_icon("remove"),
                "Retirer de l'espace",
                lambda: self._try(lambda: self._manager.remove_repo(workspace_name, data)),
            )
        elif kind == K_RECENT:
            menu.addAction(app_icon("open"), "Ouvrir", lambda: self.open_repo_requested.emit(data))
        elif kind == K_LOCAL_BRANCH:
            menu.addAction(app_icon("checkout"), "Checkout", lambda: self.checkout_requested.emit(data))
            self._add_merge_action(menu, data)
            menu.addAction(
                app_icon("clear"), "Supprimer la branche", lambda: self._confirm_delete_branch(data)
            )
        elif kind == K_SECTION_GITFLOW:
            if self._gitflow is None:
                menu.addAction(
                    app_icon("gitflow"), "Initialiser Git Flow…", self.gitflow_init_requested.emit
                )
            else:
                menu.addAction(
                    app_icon("plus"),
                    "Démarrer une feature…", lambda: self.gitflow_start_requested.emit(K_GF_FEATURE)
                )
                menu.addAction(
                    app_icon("plus"),
                    "Démarrer une release…", lambda: self.gitflow_start_requested.emit(K_GF_RELEASE)
                )
                menu.addAction(
                    app_icon("plus"),
                    "Démarrer un hotfix…", lambda: self.gitflow_start_requested.emit(K_GF_HOTFIX)
                )
        elif kind == K_GITFLOW_INIT:
            menu.addAction(
                app_icon("gitflow"), "Initialiser Git Flow…", self.gitflow_init_requested.emit
            )
        elif kind in (K_GF_FEATURE, K_GF_RELEASE, K_GF_HOTFIX):
            full = self._gitflow_full_name(kind, data)
            finish_label = {
                K_GF_FEATURE: "Terminer la feature (merge dans develop)",
                K_GF_RELEASE: "Terminer la release (merge main + develop, tag)",
                K_GF_HOTFIX: "Terminer le hotfix (merge main + develop, tag)",
            }[kind]
            menu.addAction(app_icon("checkout"), "Checkout", lambda: self.checkout_requested.emit(full))
            self._add_merge_action(menu, full)
            menu.addAction(
                app_icon("merge"), finish_label, lambda: self.gitflow_finish_requested.emit(kind, data)
            )
            menu.addAction(
                app_icon("clear"), "Supprimer la branche", lambda: self._confirm_delete_branch(full)
            )
        else:
            return

        menu.exec(tree.viewport().mapToGlobal(pos))

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
