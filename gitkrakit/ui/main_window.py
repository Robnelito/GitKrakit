"""
main_window.py
Fenêtre principale de GitKrakit : orchestration entre le backend Git et
les panneaux (barre latérale, graphe, staging, détails, terminal). Les
panneaux sont des vues "muettes" qui émettent des signaux ; toute la
logique Git et la gestion d'erreurs sont centralisées ici.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QInputDialog,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
)

from gitkrakit.core import CommitInfo, GitBackend, GitBackendError, GitFlow
from gitkrakit.ui.graph_view import GraphPanel
from gitkrakit.ui.panels import (
    DetailsPanel,
    DiffPanel,
    SidebarPanel,
    StagingPanel,
    TerminalDock,
)
from gitkrakit.workspace import WorkspaceManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitKrakit")
        self.resize(1280, 800)

        self.backend = GitBackend()
        self.gitflow = GitFlow(self.backend)
        self.workspace_manager = WorkspaceManager()
        self._commits_by_sha: dict[str, CommitInfo] = {}
        self._last_refresh = 0.0

        self._build_toolbar()
        self._build_central_widget()
        self._build_terminal_dock()

        self.statusBar().showMessage("Ouvre un dépôt pour commencer (Ouvrir un dépôt)")

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
        fetch_action.triggered.connect(lambda: self._run_backend_op(self.backend.fetch))
        toolbar.addAction(fetch_action)

        pull_action = QAction("Pull", self)
        pull_action.triggered.connect(lambda: self._run_backend_op(self.backend.pull))
        toolbar.addAction(pull_action)

        push_action = QAction("Push", self)
        push_action.triggered.connect(lambda: self._run_backend_op(self.backend.push))
        toolbar.addAction(push_action)

        toolbar.addSeparator()

        branch_action = QAction("Nouvelle branche", self)
        branch_action.triggered.connect(self.create_branch_dialog)
        toolbar.addAction(branch_action)

        gitflow_menu = QMenu("Git Flow", self)
        gitflow_menu.addAction("Initialiser Git Flow…", self._gitflow_init)
        gitflow_menu.addSeparator()
        gitflow_menu.addAction("Démarrer une feature…", lambda: self._gitflow_start("feature"))
        gitflow_menu.addAction("Démarrer une release…", lambda: self._gitflow_start("release"))
        gitflow_menu.addAction("Démarrer un hotfix…", lambda: self._gitflow_start("hotfix"))
        gitflow_button = QToolButton()
        gitflow_button.setText("Git Flow")
        gitflow_button.setMenu(gitflow_menu)
        gitflow_button.setPopupMode(QToolButton.InstantPopup)
        toolbar.addWidget(gitflow_button)

        stash_action = QAction("Stash", self)
        stash_action.triggered.connect(lambda: self._run_backend_op(self.backend.stash))
        toolbar.addAction(stash_action)

        pop_action = QAction("Pop", self)
        pop_action.triggered.connect(lambda: self._run_backend_op(self.backend.stash_pop))
        toolbar.addAction(pop_action)

        toolbar.addSeparator()

        refresh_action = QAction("Rafraîchir", self)
        # lambda : triggered émet un bool (checked) qui écraserait show_errors
        refresh_action.triggered.connect(lambda: self.refresh_all())
        toolbar.addAction(refresh_action)

    def _build_central_widget(self) -> None:
        splitter = QSplitter(Qt.Horizontal)

        # --- gauche : barre latérale unifiée ---
        self.sidebar = SidebarPanel(self.workspace_manager)
        self.sidebar.open_repo_requested.connect(self.open_repo)
        self.sidebar.checkout_requested.connect(self._checkout_branch)
        self.sidebar.branch_delete_requested.connect(self._delete_branch)
        self.sidebar.gitflow_init_requested.connect(self._gitflow_init)
        self.sidebar.gitflow_start_requested.connect(self._gitflow_start)
        self.sidebar.gitflow_finish_requested.connect(self._gitflow_finish)
        splitter.addWidget(self.sidebar)

        # --- centre : graphe de commits ---
        self.graph_panel = GraphPanel()
        self.graph_panel.commit_selected.connect(self.show_commit_details)
        splitter.addWidget(self.graph_panel)

        # --- droite : staging + détails ---
        right_panel = QTabWidget()

        self.staging_panel = StagingPanel()
        self.staging_panel.stage_requested.connect(self._stage)
        self.staging_panel.unstage_requested.connect(self._unstage)
        self.staging_panel.commit_requested.connect(self._commit)
        self.staging_panel.diff_requested.connect(self._show_working_diff)
        right_panel.addTab(self.staging_panel, "Staging")

        self.details_panel = DetailsPanel()
        self.details_panel.file_diff_requested.connect(self._show_commit_diff)
        right_panel.addTab(self.details_panel, "Détails du commit")

        self.diff_panel = DiffPanel()
        right_panel.addTab(self.diff_panel, "Diff")
        self._right_panel = right_panel

        splitter.addWidget(right_panel)
        splitter.setSizes([230, 720, 330])

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
        """Point d'entrée unique pour ouvrir un dépôt (dialogue, sidebar, CLI)."""
        try:
            self.backend.open(path)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        active_path = self.backend.working_dir or path
        self.workspace_manager.touch_recent(active_path)
        self.sidebar.set_active_repo(active_path)
        self.setWindowTitle(f"GitKrakit — {path}")
        self.refresh_all()

    # ------------------------------------------------------------------
    # Rafraîchissement
    # ------------------------------------------------------------------
    def event(self, event) -> bool:
        # rafraîchissement auto quand la fenêtre reprend le focus (fichiers
        # modifiés dans un éditeur externe, commits faits en ligne de commande…)
        if (
            event.type() == QEvent.WindowActivate
            and self.backend.is_open
            and time.monotonic() - self._last_refresh > 1.0
        ):
            self.refresh_all(show_errors=False)
        return super().event(event)

    def refresh_all(self, show_errors: bool = True) -> None:
        """Recharge branches, graphe et statut. Avec show_errors=False
        (rafraîchissement auto), les erreurs vont dans la barre de statut au
        lieu d'un dialogue — sinon fermer le dialogue redonnerait le focus à
        la fenêtre et relancerait le rafraîchissement en boucle."""
        if not self.backend.is_open:
            return
        try:
            self.sidebar.update_refs(
                local=self.backend.local_branches(),
                remote=self.backend.remote_branches(),
                tags=self.backend.tags(),
                current_branch=self.backend.current_branch,
                gitflow=self.gitflow.status(),
            )
            commits = self.backend.commit_log()
            self._commits_by_sha = {c.sha: c for c in commits}
            self.graph_panel.set_commits(commits)
            self._refresh_status()
        except GitBackendError as exc:
            if show_errors:
                QMessageBox.critical(self, "Erreur", str(exc))
            else:
                self.statusBar().showMessage(f"Rafraîchissement échoué : {exc}", 5000)
            return
        finally:
            self._last_refresh = time.monotonic()
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

    def _delete_branch(self, name: str) -> None:
        try:
            self.backend.delete_branch(name)
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

    def _run_backend_op(self, fn, done_message: str | None = None) -> None:
        """Opération backend qui retourne un message de statut (fetch, pull,
        push, stash, git flow…) : affiche le résultat dans la barre de statut."""
        if not self.backend.is_open:
            return
        try:
            result = fn()
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        message = done_message or (result if isinstance(result, str) else "")
        if message:
            self.statusBar().showMessage(message, 5000)
        self.refresh_all()

    def show_commit_details(self, sha: str) -> None:
        commit = self._commits_by_sha.get(sha)
        if commit is None:
            return
        try:
            files = self.backend.commit_files(sha)
        except GitBackendError:
            files = []
        self.details_panel.show_commit(commit, files)
        self._right_panel.setCurrentWidget(self.details_panel)

    # ------------------------------------------------------------------
    # Git Flow
    # ------------------------------------------------------------------
    def _gitflow_init(self) -> None:
        if not self.backend.is_open:
            return
        if self.gitflow.is_initialized():
            QMessageBox.information(self, "Git Flow", "Git Flow est déjà initialisé.")
            return
        answer = QMessageBox.question(
            self,
            "Initialiser Git Flow",
            "Initialiser Git Flow avec les valeurs par défaut ?\n\n"
            "  branche de production : main (ou master)\n"
            "  branche d'intégration : develop (créée si absente)\n"
            "  préfixes : feature/  release/  hotfix/",
        )
        if answer != QMessageBox.Yes:
            return
        self._run_backend_op(self.gitflow.init, done_message="Git Flow initialisé — branche develop")

    def _gitflow_start(self, kind: str) -> None:
        if not self.backend.is_open:
            return
        if not self.gitflow.is_initialized():
            self._gitflow_init()
            if not self.gitflow.is_initialized():
                return
        prompts = {
            "feature": ("Nouvelle feature", "Nom de la feature :", self.gitflow.feature_start),
            "release": ("Nouvelle release", "Version (ex: 1.2.0) :", self.gitflow.release_start),
            "hotfix": ("Nouveau hotfix", "Version (ex: 1.2.1) :", self.gitflow.hotfix_start),
        }
        title, label, start_fn = prompts[kind]
        name, ok = QInputDialog.getText(self, title, label)
        if not ok or not name.strip():
            return
        self._run_backend_op(lambda: start_fn(name))

    def _gitflow_finish(self, kind: str, name: str) -> None:
        confirmations = {
            "feature": (
                f"Terminer la feature '{name}' ?\n\n"
                "→ merge dans develop puis suppression de la branche.",
                self.gitflow.feature_finish,
            ),
            "release": (
                f"Terminer la release '{name}' ?\n\n"
                f"→ merge dans main, tag '{name}', merge dans develop,\n"
                "puis suppression de la branche.",
                self.gitflow.release_finish,
            ),
            "hotfix": (
                f"Terminer le hotfix '{name}' ?\n\n"
                f"→ merge dans main, tag '{name}', merge dans develop,\n"
                "puis suppression de la branche.",
                self.gitflow.hotfix_finish,
            ),
        }
        message, finish_fn = confirmations[kind]
        answer = QMessageBox.question(self, "Git Flow", message)
        if answer != QMessageBox.Yes:
            return
        self._run_backend_op(lambda: finish_fn(name))

    def _show_working_diff(self, path: str, staged: bool) -> None:
        diff = self.backend.diff_for_file(path, staged=staged)
        origin = "indexé" if staged else "non indexé"
        self.diff_panel.show_diff(f"{path}  ({origin})", diff)
        self._right_panel.setCurrentWidget(self.diff_panel)

    def _show_commit_diff(self, sha: str, path: str) -> None:
        try:
            diff = self.backend.diff_for_commit_file(sha, path)
        except GitBackendError as exc:
            diff = str(exc)
        self.diff_panel.show_diff(f"{path}  (commit {sha[:7]})", diff)
        self._right_panel.setCurrentWidget(self.diff_panel)

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
