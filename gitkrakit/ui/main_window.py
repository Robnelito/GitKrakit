"""
main_window.py
Fenêtre principale de GitKrakit : orchestration entre le backend Git et
les panneaux (espaces de travail, branches, graphe, staging, détails,
terminal). Les panneaux sont des vues "muettes" qui émettent des signaux ;
toute la logique Git et la gestion d'erreurs sont centralisées ici.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QSplitter,
    QTabWidget,
    QToolBar,
)

from gitkrakit.core import GitBackend, GitBackendError
from gitkrakit.ui.graph_view import GraphView
from gitkrakit.ui.panels import (
    BranchesPanel,
    DetailsPanel,
    StagingPanel,
    TerminalDock,
    WorkspacePanel,
)
from gitkrakit.workspace import WorkspaceManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitKrakit")
        self.resize(1280, 800)

        self.backend = GitBackend()
        self.workspace_manager = WorkspaceManager()

        self._build_toolbar()
        self._build_central_widget()
        self._build_terminal_dock()

        self.statusBar().showMessage("Ouvre un dépôt pour commencer (Fichier > Ouvrir un dépôt)")

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Actions")
        self.addToolBar(toolbar)

        open_action = QAction("Ouvrir un dépôt", self)
        open_action.triggered.connect(self.open_repo_dialog)
        toolbar.addAction(open_action)

        toolbar.addSeparator()

        fetch_action = QAction("Fetch", self)
        fetch_action.triggered.connect(lambda: self._run_remote_op(self.backend.fetch))
        toolbar.addAction(fetch_action)

        pull_action = QAction("Pull", self)
        pull_action.triggered.connect(lambda: self._run_remote_op(self.backend.pull))
        toolbar.addAction(pull_action)

        push_action = QAction("Push", self)
        push_action.triggered.connect(lambda: self._run_remote_op(self.backend.push))
        toolbar.addAction(push_action)

        toolbar.addSeparator()

        branch_action = QAction("Nouvelle branche", self)
        branch_action.triggered.connect(self.create_branch_dialog)
        toolbar.addAction(branch_action)

        refresh_action = QAction("Rafraîchir", self)
        refresh_action.triggered.connect(self.refresh_all)
        toolbar.addAction(refresh_action)

    def _build_central_widget(self) -> None:
        splitter = QSplitter(Qt.Horizontal)

        # --- panneau gauche : espaces de travail + branches/tags ---
        left_tabs = QTabWidget()

        self.workspace_panel = WorkspacePanel(self.workspace_manager)
        self.workspace_panel.open_repo_requested.connect(self.open_repo)
        left_tabs.addTab(self.workspace_panel, "Espaces")

        self.branches_panel = BranchesPanel()
        self.branches_panel.checkout_requested.connect(self._checkout_branch)
        left_tabs.addTab(self.branches_panel, "Branches")

        splitter.addWidget(left_tabs)

        # --- centre : graphe de commits ---
        self.graph_view = GraphView()
        self.graph_view.commit_selected.connect(self.show_commit_details)
        splitter.addWidget(self.graph_view)

        # --- droite : staging + détails ---
        right_panel = QTabWidget()

        self.staging_panel = StagingPanel()
        self.staging_panel.stage_requested.connect(self._stage)
        self.staging_panel.unstage_requested.connect(self._unstage)
        self.staging_panel.commit_requested.connect(self._commit)
        right_panel.addTab(self.staging_panel, "Staging")

        self.details_panel = DetailsPanel()
        right_panel.addTab(self.details_panel, "Détails du commit")

        splitter.addWidget(right_panel)
        splitter.setSizes([220, 700, 360])

        self.setCentralWidget(splitter)

    def _build_terminal_dock(self) -> None:
        self.terminal = TerminalDock(self)
        self.terminal.command_entered.connect(self._run_terminal_command)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.terminal)

    # ------------------------------------------------------------------
    # Ouverture de dépôt
    # ------------------------------------------------------------------
    def open_repo_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dépôt Git")
        if path:
            self.open_repo(path)

    def open_repo(self, path: str) -> None:
        """Point d'entrée unique pour ouvrir un dépôt (dialogue, workspace, CLI)."""
        try:
            self.backend.open(path)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.workspace_manager.touch_recent(self.backend.working_dir or path)
        self.workspace_panel.refresh()
        self.setWindowTitle(f"GitKrakit — {path}")
        self.refresh_all()

    # ------------------------------------------------------------------
    # Rafraîchissement
    # ------------------------------------------------------------------
    def refresh_all(self) -> None:
        if not self.backend.is_open:
            return
        try:
            self.branches_panel.update_data(
                local=self.backend.local_branches(),
                remote=self.backend.remote_branches(),
                tags=self.backend.tags(),
                current_branch=self.backend.current_branch,
            )
            self.graph_view.set_commits(self.backend.commit_log())
            self._refresh_status()
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
        self.statusBar().showMessage(f"Branche courante : {self.backend.current_branch}")

    def _refresh_status(self) -> None:
        staged, unstaged = self.backend.status()
        self.staging_panel.update_status(staged, unstaged)

    # ------------------------------------------------------------------
    # Actions Git
    # ------------------------------------------------------------------
    def _checkout_branch(self, name: str) -> None:
        try:
            self.backend.checkout(name)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.refresh_all()

    def create_branch_dialog(self) -> None:
        if not self.backend.is_open:
            return
        name, ok = QInputDialog.getText(self, "Nouvelle branche", "Nom de la branche :")
        if not ok or not name.strip():
            return
        try:
            self.backend.create_branch(name.strip())
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.refresh_all()

    def _stage(self, paths: list[str]) -> None:
        try:
            self.backend.stage(paths)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
        self._refresh_status()

    def _unstage(self, paths: list[str]) -> None:
        try:
            self.backend.unstage(paths)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
        self._refresh_status()

    def _commit(self, message: str) -> None:
        try:
            self.backend.commit(message)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.staging_panel.clear_message()
        self.refresh_all()

    def _run_remote_op(self, fn) -> None:
        if not self.backend.is_open:
            return
        try:
            result = fn()
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.statusBar().showMessage(result, 5000)
        self.refresh_all()

    def show_commit_details(self, sha: str) -> None:
        commits = {c.sha: c for c in self.backend.commit_log()}
        commit = commits.get(sha)
        if commit is not None:
            self.details_panel.show_commit(commit)

    def _run_terminal_command(self, args: list[str]) -> None:
        if not self.backend.is_open:
            self.terminal.append_output("Erreur: aucun dépôt ouvert.")
            return
        try:
            output = self.backend.run_raw(args)
            self.terminal.append_output(output or "(aucune sortie)")
        except GitBackendError as exc:
            self.terminal.append_output(f"Erreur: {exc}")
        self.refresh_all()
