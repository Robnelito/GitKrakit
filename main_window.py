"""
main_window.py
Fenêtre principale de GitKrakit : barre d'outils (fetch/pull/push/branche),
panneau de gauche (branches/tags), graphe de commits au centre, panneau de
staging + détails de commit à droite, mini-terminal git en bas.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QTextEdit,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QToolBar,
    QTabWidget,
    QPlainTextEdit,
)
from PySide6.QtGui import QAction

from git_backend import GitBackend, GitBackendError
from graph_view import GraphView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitKrakit")
        self.resize(1280, 800)

        self.backend = GitBackend()

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
        fetch_action.triggered.connect(self.do_fetch)
        toolbar.addAction(fetch_action)

        pull_action = QAction("Pull", self)
        pull_action.triggered.connect(self.do_pull)
        toolbar.addAction(pull_action)

        push_action = QAction("Push", self)
        push_action.triggered.connect(self.do_push)
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

        # --- panneau gauche : branches / tags ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Branches locales"))
        self.branch_list = QListWidget()
        self.branch_list.itemDoubleClicked.connect(self._checkout_from_list)
        left_layout.addWidget(self.branch_list)
        left_layout.addWidget(QLabel("Branches distantes"))
        self.remote_branch_list = QListWidget()
        left_layout.addWidget(self.remote_branch_list)
        left_layout.addWidget(QLabel("Tags"))
        self.tag_list = QListWidget()
        left_layout.addWidget(self.tag_list)
        splitter.addWidget(left_panel)

        # --- centre : graphe de commits ---
        self.graph_view = GraphView()
        self.graph_view.commit_selected.connect(self.show_commit_details)
        splitter.addWidget(self.graph_view)

        # --- droite : staging + détails ---
        right_panel = QTabWidget()

        staging_tab = QWidget()
        staging_layout = QVBoxLayout(staging_tab)
        staging_layout.addWidget(QLabel("Fichiers modifiés (non indexés)"))
        self.unstaged_list = QListWidget()
        self.unstaged_list.setSelectionMode(QListWidget.ExtendedSelection)
        staging_layout.addWidget(self.unstaged_list)

        stage_buttons = QHBoxLayout()
        stage_btn = QPushButton("Indexer (stage) →")
        stage_btn.clicked.connect(self.stage_selected)
        stage_buttons.addWidget(stage_btn)
        staging_layout.addLayout(stage_buttons)

        staging_layout.addWidget(QLabel("Fichiers indexés (staged)"))
        self.staged_list = QListWidget()
        self.staged_list.setSelectionMode(QListWidget.ExtendedSelection)
        staging_layout.addWidget(self.staged_list)

        unstage_btn = QPushButton("← Désindexer (unstage)")
        unstage_btn.clicked.connect(self.unstage_selected)
        staging_layout.addWidget(unstage_btn)

        staging_layout.addWidget(QLabel("Message de commit"))
        self.commit_message_edit = QTextEdit()
        self.commit_message_edit.setFixedHeight(80)
        staging_layout.addWidget(self.commit_message_edit)

        commit_btn = QPushButton("Commit")
        commit_btn.clicked.connect(self.do_commit)
        staging_layout.addWidget(commit_btn)

        right_panel.addTab(staging_tab, "Staging")

        details_tab = QWidget()
        details_layout = QVBoxLayout(details_tab)
        self.commit_details = QPlainTextEdit()
        self.commit_details.setReadOnly(True)
        details_layout.addWidget(self.commit_details)
        right_panel.addTab(details_tab, "Détails du commit")

        splitter.addWidget(right_panel)
        splitter.setSizes([220, 700, 360])

        self.setCentralWidget(splitter)

    def _build_terminal_dock(self) -> None:
        from PySide6.QtWidgets import QDockWidget

        dock = QDockWidget("Terminal git intégré", self)
        dock_widget = QWidget()
        layout = QVBoxLayout(dock_widget)

        self.terminal_output = QPlainTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setMaximumHeight(180)
        layout.addWidget(self.terminal_output)

        input_row = QHBoxLayout()
        self.terminal_input = QLineEdit()
        self.terminal_input.setPlaceholderText("ex: status, log --oneline -5, remote -v ...")
        self.terminal_input.returnPressed.connect(self.run_terminal_command)
        input_row.addWidget(QLabel("git"))
        input_row.addWidget(self.terminal_input)
        run_btn = QPushButton("Exécuter")
        run_btn.clicked.connect(self.run_terminal_command)
        input_row.addWidget(run_btn)
        layout.addLayout(input_row)

        dock.setWidget(dock_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def open_repo_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dépôt Git")
        if not path:
            return
        try:
            self.backend.open(path)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.setWindowTitle(f"GitKrakit — {path}")
        self.refresh_all()

    def refresh_all(self) -> None:
        if not self.backend.is_open:
            return
        try:
            self._refresh_branches()
            self._refresh_graph()
            self._refresh_status()
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
        self.statusBar().showMessage(f"Branche courante : {self.backend.current_branch}")

    def _refresh_branches(self) -> None:
        self.branch_list.clear()
        for name in self.backend.local_branches():
            label = name
            if name == self.backend.current_branch:
                label = f"* {name}"
            self.branch_list.addItem(QListWidgetItem(label))

        self.remote_branch_list.clear()
        for name in self.backend.remote_branches():
            self.remote_branch_list.addItem(QListWidgetItem(name))

        self.tag_list.clear()
        for name in self.backend.tags():
            self.tag_list.addItem(QListWidgetItem(name))

    def _refresh_graph(self) -> None:
        commits = self.backend.commit_log()
        self.graph_view.set_commits(commits)

    def _refresh_status(self) -> None:
        staged, unstaged = self.backend.status()
        self.staged_list.clear()
        for f in staged:
            self.staged_list.addItem(QListWidgetItem(f"[{f.status}] {f.path}"))
        self.unstaged_list.clear()
        for f in unstaged:
            self.unstaged_list.addItem(QListWidgetItem(f"[{f.status}] {f.path}"))

    def _checkout_from_list(self, item: QListWidgetItem) -> None:
        name = item.text().lstrip("* ").strip()
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

    def stage_selected(self) -> None:
        paths = [self._strip_status_prefix(i.text()) for i in self.unstaged_list.selectedItems()]
        if not paths:
            return
        self.backend.stage(paths)
        self._refresh_status()

    def unstage_selected(self) -> None:
        paths = [self._strip_status_prefix(i.text()) for i in self.staged_list.selectedItems()]
        if not paths:
            return
        self.backend.unstage(paths)
        self._refresh_status()

    @staticmethod
    def _strip_status_prefix(text: str) -> str:
        # "[modified] chemin/fichier.py" -> "chemin/fichier.py"
        return text.split("] ", 1)[-1]

    def do_commit(self) -> None:
        message = self.commit_message_edit.toPlainText().strip()
        try:
            self.backend.commit(message)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.commit_message_edit.clear()
        self.refresh_all()

    def do_fetch(self) -> None:
        self._run_remote_op(self.backend.fetch)

    def do_pull(self) -> None:
        self._run_remote_op(self.backend.pull)

    def do_push(self) -> None:
        self._run_remote_op(self.backend.push)

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
        if commit is None:
            return
        text = (
            f"Commit    : {commit.sha}\n"
            f"Auteur    : {commit.author} <{commit.author_email}>\n"
            f"Date      : {commit.date:%Y-%m-%d %H:%M:%S}\n"
            f"Parents   : {', '.join(p[:7] for p in commit.parents) or '(racine)'}\n"
            f"Refs      : {', '.join(commit.refs) or '-'}\n\n"
            f"Message   :\n{commit.message}\n"
        )
        self.commit_details.setPlainText(text)

    def run_terminal_command(self) -> None:
        raw = self.terminal_input.text().strip()
        if not raw or not self.backend.is_open:
            return
        args = raw.split()
        self.terminal_output.appendPlainText(f"$ git {raw}")
        try:
            output = self.backend.run_raw(args)
            self.terminal_output.appendPlainText(output or "(aucune sortie)")
        except GitBackendError as exc:
            self.terminal_output.appendPlainText(f"Erreur: {exc}")
        self.terminal_input.clear()
        self.refresh_all()
