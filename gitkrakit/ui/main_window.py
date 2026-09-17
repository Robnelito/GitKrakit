"""
main_window.py
Fenêtre principale de GitKrakit : orchestration entre le backend Git et
les panneaux (barre latérale, graphe, staging, détails, terminal). Les
panneaux sont des vues "muettes" qui émettent des signaux ; toute la
logique Git et la gestion d'erreurs sont centralisées ici.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QEvent, QSize, QThread, QTimer
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QInputDialog,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gitkrakit import __version__, preferences, theme
from gitkrakit.core import CommitInfo, GitBackend, GitBackendError, GitFlow
from gitkrakit.core.acp_commit import ACP_PROVIDERS
from gitkrakit.core.acp_commit import generate_commit_message as generate_acp_commit_message
from gitkrakit.ui import icons
from gitkrakit.ui.preferences_dialog import PreferencesDialog
from gitkrakit.ui.graph_view import GraphPanel
from gitkrakit.ui.panels import (
    DetailsPanel,
    DiffPanel,
    SidebarPanel,
    StagingPanel,
    TerminalDock,
)
from gitkrakit.ui.updater import UpdateBanner, UpdaterController
from gitkrakit.workspace import WorkspaceError, WorkspaceManager

AUTO_FETCH_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes


class _OperationThread(QThread):
    """Execute one backend callable without blocking Qt's event loop."""

    def __init__(self, operation: Callable[[], Any], parent=None):
        super().__init__(parent)
        self._operation = operation
        self.result: Any = None
        self.error: Exception | None = None

    def run(self) -> None:
        try:
            self.result = self._operation()
        except Exception as exc:  # surfaced in the UI on the main thread
            self.error = exc


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitKrakit")
        self.resize(1280, 800)
        self.setMinimumSize(980, 640)

        self.backend = GitBackend()
        self._operation_thread: _OperationThread | None = None
        self._operation_label = ""
        self._operation_done_message: str | None = None
        self._operation_silent = False
        self._operation_refresh = True
        self._operation_on_success: Callable[[Any], None] | None = None
        self._operation_on_error: Callable[[str], None] | None = None
        self._close_when_idle = False
        self.gitflow = GitFlow(self.backend)
        self.workspace_manager = WorkspaceManager()
        self._commits_by_sha: dict[str, CommitInfo] = {}
        self._last_refresh = 0.0
        self._theme_mode = theme.saved_theme_mode()
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, self._theme_mode)

        self._build_toolbar()
        self._build_central_widget()
        self._build_terminal_dock()
        self._build_menus()
        self._build_status_bar()
        self._updater = UpdaterController(self)
        self._connect_updater()
        self.setWindowIcon(icons.app_icon("repo", theme.ACCENT, 32))

        self._auto_fetch_timer = QTimer(self)
        self._auto_fetch_timer.setInterval(AUTO_FETCH_INTERVAL_MS)
        self._auto_fetch_timer.timeout.connect(self._auto_fetch)
        self._auto_fetch_timer.start()

        try:
            QApplication.instance().styleHints().colorSchemeChanged.connect(
                self._on_system_color_scheme_changed
            )
        except AttributeError:
            pass

        self._update_action_state()
        self.statusBar().showMessage("Ouvre un dépôt pour commencer")

    def closeEvent(self, event) -> None:
        if self._operation_thread is not None and self._operation_thread.isRunning():
            self._close_when_idle = True
            self.statusBar().showMessage(
                "Fermeture dès que l'opération Git en cours est terminée…"
            )
            event.ignore()
            return
        self.backend.close()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Actions principales")
        toolbar.setObjectName("mainToolbar")
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setMinimumHeight(50)
        self.addToolBar(toolbar)

        self.open_action = QAction(icons.toolbar_icon("open"), "Ouvrir", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setToolTip("Ouvrir un dépôt Git (Ctrl+O)")
        self.open_action.triggered.connect(self.open_repo_dialog)
        open_button = self._make_toolbar_button(self.open_action, object_name="toolbarPrimaryButton")
        toolbar.addWidget(open_button)
        toolbar.addWidget(self._toolbar_gap())

        self.fetch_action = QAction(icons.toolbar_icon("fetch"), "Fetch", self)
        self.fetch_action.setToolTip("Récupérer les références de origin")
        self.fetch_action.triggered.connect(
            lambda: self._run_backend_op(self.backend.fetch, label="Fetch en cours…")
        )

        self.pull_action = QAction(icons.toolbar_icon("pull"), "Pull", self)
        self.pull_action.setToolTip("Récupérer et intégrer les commits de origin")
        self.pull_action.triggered.connect(
            lambda: self._run_backend_op(self.backend.pull, label="Pull en cours…")
        )

        self.push_action = QAction(icons.toolbar_icon("push"), "Push", self)
        self.push_action.setToolTip("Publier les commits vers origin")
        self.push_action.triggered.connect(
            lambda: self._run_backend_op(self.backend.push, label="Push en cours…")
        )
        sync_group = self._toolbar_group(
            self._make_toolbar_button(self.fetch_action),
            self._make_toolbar_button(self.pull_action),
            self._make_toolbar_button(self.push_action),
        )
        toolbar.addWidget(sync_group)
        toolbar.addWidget(self._toolbar_gap())

        self.branch_action = QAction(icons.toolbar_icon("branch"), "Nouvelle branche", self)
        self.branch_action.setShortcut("Ctrl+Shift+B")
        self.branch_action.setToolTip("Créer une branche (Ctrl+Shift+B)")
        self.branch_action.triggered.connect(self.create_branch_dialog)

        gitflow_menu = QMenu("Git Flow", self)
        self._gitflow_init_action = gitflow_menu.addAction(
            icons.app_icon("gitflow"), "Initialiser Git Flow…", self._gitflow_init
        )
        gitflow_menu.addSeparator()
        self._gitflow_start_actions = [
            gitflow_menu.addAction(
                icons.app_icon("plus"),
                f"Démarrer une {kind}…",
                lambda _checked=False, value=kind: self._gitflow_start(value),
            )
            for kind in ("feature", "release", "hotfix")
        ]
        self.gitflow_action = QAction(icons.toolbar_icon("gitflow"), "Git Flow", self)
        self.gitflow_action.setToolTip("Initialiser ou gérer un workflow Git Flow")
        self.gitflow_action.setMenu(gitflow_menu)
        gitflow_button = self._make_toolbar_button(
            self.gitflow_action, object_name="toolbarMenuButton"
        )
        gitflow_button.setMenu(gitflow_menu)
        gitflow_button.setPopupMode(QToolButton.InstantPopup)
        branch_group = self._toolbar_group(
            self._make_toolbar_button(self.branch_action),
            gitflow_button,
        )
        toolbar.addWidget(branch_group)
        toolbar.addWidget(self._toolbar_gap())

        self.stash_action = QAction(icons.toolbar_icon("stash"), "Stash", self)
        self.stash_action.setToolTip("Mettre les modifications de côté")
        self.stash_action.triggered.connect(
            lambda: self._run_backend_op(self.backend.stash, label="Création du stash…")
        )

        self.pop_action = QAction(icons.toolbar_icon("pop"), "Pop", self)
        self.pop_action.setToolTip("Réappliquer le dernier stash")
        self.pop_action.triggered.connect(
            lambda: self._run_backend_op(self.backend.stash_pop, label="Application du stash…")
        )
        stash_group = self._toolbar_group(
            self._make_toolbar_button(self.stash_action),
            self._make_toolbar_button(self.pop_action),
        )
        toolbar.addWidget(stash_group)

        stretch = QWidget()
        stretch.setObjectName("toolbarStretch")
        stretch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(stretch)

        self._appearance_menu = QMenu("Apparence", self)
        appearance_group = QActionGroup(self)
        appearance_group.setExclusive(True)
        self._appearance_actions: dict[str, QAction] = {}
        for mode, label in (
            (theme.THEME_SYSTEM, "Système"),
            (theme.THEME_LIGHT, "Clair"),
            (theme.THEME_DARK, "Sombre"),
        ):
            action = QAction(icons.toolbar_icon(mode), label, self)
            action.setCheckable(True)
            action.setChecked(mode == self._theme_mode)
            action.triggered.connect(
                lambda _checked=False, selected=mode: self._set_theme_mode(selected)
            )
            appearance_group.addAction(action)
            self._appearance_menu.addAction(action)
            self._appearance_actions[mode] = action

        self._appearance_button = QToolButton()
        self._appearance_button.setObjectName("toolbarMenuButton")
        self._appearance_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._appearance_button.setMenu(self._appearance_menu)
        self._appearance_button.setPopupMode(QToolButton.InstantPopup)
        self._appearance_button.setAutoRaise(True)
        self._appearance_button.setCursor(Qt.PointingHandCursor)
        self._appearance_button.setToolTip("Choisir le thème de l'interface")
        self._update_appearance_button()
        toolbar.addWidget(self._appearance_button)
        toolbar.addWidget(self._toolbar_gap(4))

        self.refresh_action = QAction(icons.toolbar_icon("refresh"), "Rafraîchir", self)
        self.refresh_action.setShortcuts(["F5", "Ctrl+R"])
        self.refresh_action.setToolTip("Rafraîchir le dépôt (F5)")
        # lambda : triggered émet un bool (checked) qui écraserait show_errors
        self.refresh_action.triggered.connect(lambda: self.refresh_all())
        refresh_button = self._make_toolbar_button(
            self.refresh_action,
            icon_only=True,
            object_name="toolbarUtilityButton",
        )
        refresh_button.setAccessibleName("Rafraîchir le dépôt")
        toolbar.addWidget(refresh_button)

        self._repo_actions = [
            self.fetch_action,
            self.pull_action,
            self.push_action,
            self.branch_action,
            self.gitflow_action,
            self.stash_action,
            self.pop_action,
            self.refresh_action,
        ]
        self._toolbar = toolbar

    def _update_appearance_button(self) -> None:
        labels = {
            theme.THEME_SYSTEM: "Système",
            theme.THEME_LIGHT: "Clair",
            theme.THEME_DARK: "Sombre",
        }
        self._appearance_button.setIcon(icons.toolbar_icon(self._theme_mode))
        self._appearance_button.setText(labels[self._theme_mode])

    def _set_theme_mode(self, mode: str, *, persist: bool = True) -> None:
        if mode not in theme.THEME_MODES:
            return
        self._theme_mode = mode
        if persist:
            theme.save_theme_mode(mode)
        app = QApplication.instance()
        if app is None:
            return
        theme.apply_theme(app, mode)
        icons.clear_icon_caches()
        for value, action in self._appearance_actions.items():
            action.setChecked(value == mode)
            action.setIcon(icons.toolbar_icon(value))
        self._update_appearance_button()
        self._apply_theme_to_widgets()

    def _on_system_color_scheme_changed(self, _scheme) -> None:
        if self._theme_mode == theme.THEME_SYSTEM:
            self._set_theme_mode(theme.THEME_SYSTEM, persist=False)

    def _apply_theme_to_widgets(self) -> None:
        action_icons = {
            self.open_action: "open",
            self.fetch_action: "fetch",
            self.pull_action: "pull",
            self.push_action: "push",
            self.branch_action: "branch",
            self.gitflow_action: "gitflow",
            self.stash_action: "stash",
            self.pop_action: "pop",
            self.refresh_action: "refresh",
        }
        for action, icon_name in action_icons.items():
            action.setIcon(icons.toolbar_icon(icon_name))

        self.setWindowIcon(icons.app_icon("repo", theme.ACCENT, 32))
        self._gitflow_init_action.setIcon(icons.app_icon("gitflow"))
        for action in self._gitflow_start_actions:
            action.setIcon(icons.app_icon("plus"))
        self._welcome_open_button.setIcon(icons.app_icon("open"))
        self._right_panel.setTabIcon(0, icons.app_icon("staging"))
        self._right_panel.setTabIcon(1, icons.app_icon("details"))
        self._quit_action.setIcon(icons.app_icon("close"))
        self._preferences_action.setIcon(icons.app_icon("settings"))
        self._toolbar_toggle_action.setIcon(icons.app_icon("toolbar"))
        self._terminal_toggle_action.setIcon(icons.app_icon("terminal"))
        self._check_updates_action.setIcon(icons.app_icon("refresh"))
        self._update_banner.apply_theme()

        self._welcome_title.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 28pt; font-weight: 700;"
        )
        self._welcome_subtitle.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11pt;"
        )
        self._diff_header.setStyleSheet(
            f"background-color: {theme.PANEL_BG}; border-bottom: 1px solid {theme.BORDER};"
        )
        self._diff_close_btn.setIcon(icons.toolbar_icon("back"))
        self._diff_close_btn.setStyleSheet(
            "QToolButton { border: 1px solid " + theme.BORDER + "; background: " + theme.SURFACE + ";"
            f" color: {theme.TEXT}; padding: 3px 10px; border-radius: 5px; }}"
            f"QToolButton:hover {{ background-color: {theme.BORDER}; border-color: {theme.ACCENT}; }}"
        )
        self._busy_label.setStyleSheet(f"color: {theme.TEXT}; padding-left: 8px;")
        self._version_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; padding: 0 8px;")

        for panel in (
            self.sidebar,
            self.graph_panel,
            self.diff_panel,
            self.staging_panel,
            self.details_panel,
            self.terminal,
        ):
            apply_panel_theme = getattr(panel, "apply_theme", None)
            if apply_panel_theme is not None:
                apply_panel_theme()

    @staticmethod
    def _make_toolbar_button(
        action: QAction,
        *,
        icon_only: bool = False,
        object_name: str = "toolbarActionButton",
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName(object_name)
        button.setDefaultAction(action)
        button.setToolButtonStyle(
            Qt.ToolButtonIconOnly if icon_only else Qt.ToolButtonTextBesideIcon
        )
        button.setAutoRaise(True)
        button.setCursor(Qt.PointingHandCursor)
        return button

    @staticmethod
    def _toolbar_group(*buttons: QToolButton) -> QWidget:
        group = QWidget()
        group.setObjectName("toolbarGroup")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(1)
        for button in buttons:
            layout.addWidget(button)
        return group

    @staticmethod
    def _toolbar_gap(width: int = 10) -> QWidget:
        gap = QWidget()
        gap.setObjectName("toolbarGap")
        gap.setFixedWidth(width)
        return gap

    def _build_central_widget(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # --- gauche : barre latérale unifiée ---
        self.sidebar = SidebarPanel(self.workspace_manager)
        self.sidebar.open_repo_requested.connect(self.open_repo)
        self.sidebar.checkout_requested.connect(self._checkout_branch)
        self.sidebar.branch_delete_requested.connect(self._delete_branch)
        self.sidebar.merge_requested.connect(self._merge_branch)
        self.sidebar.gitflow_init_requested.connect(self._gitflow_init)
        self.sidebar.gitflow_start_requested.connect(self._gitflow_start)
        self.sidebar.gitflow_finish_requested.connect(self._gitflow_finish)
        splitter.addWidget(self.sidebar)

        # --- centre : graphe de commits, remplacé par le diff d'un fichier
        #     quand on en sélectionne un (bascule via QStackedWidget) ---
        self.graph_panel = GraphPanel()
        self.graph_panel.commit_selected.connect(self.show_commit_details)

        self.diff_panel = DiffPanel()
        self.diff_page = self._build_diff_page(self.diff_panel)
        self.welcome_page = self._build_welcome_page()

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.welcome_page)
        self.center_stack.addWidget(self.graph_panel)
        self.center_stack.addWidget(self.diff_page)
        self.center_stack.setCurrentWidget(self.welcome_page)
        splitter.addWidget(self.center_stack)

        # --- droite : staging + détails ---
        right_panel = QTabWidget()
        right_panel.setObjectName("inspectorTabs")
        right_panel.setDocumentMode(True)
        right_panel.setAccessibleName("Inspecteur du dépôt")
        right_panel.tabBar().setObjectName("inspectorTabBar")
        right_panel.tabBar().setExpanding(True)
        right_panel.tabBar().setDrawBase(False)
        right_panel.tabBar().setUsesScrollButtons(False)
        right_panel.setIconSize(QSize(17, 17))

        self.staging_panel = StagingPanel()
        self.staging_panel.stage_requested.connect(self._stage)
        self.staging_panel.unstage_requested.connect(self._unstage)
        self.staging_panel.commit_requested.connect(self._commit)
        self.staging_panel.diff_requested.connect(self._show_working_diff)
        self.staging_panel.generate_message_requested.connect(
            self._generate_commit_message
        )
        self._refresh_acp_agents()
        right_panel.addTab(self.staging_panel, icons.app_icon("staging"), "Staging")
        right_panel.setTabToolTip(0, "Préparer les fichiers et créer un commit")

        self.details_panel = DetailsPanel()
        self.details_panel.file_diff_requested.connect(self._show_commit_diff)
        right_panel.addTab(self.details_panel, icons.app_icon("details"), "Détails")
        right_panel.setTabToolTip(1, "Inspecter le commit sélectionné et ses fichiers")
        self._right_panel = right_panel

        splitter.addWidget(right_panel)
        splitter.setSizes([230, 720, 330])

        self._update_banner = UpdateBanner()
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._update_banner)
        central_layout.addWidget(splitter, stretch=1)
        self.setCentralWidget(central)

    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.addStretch(1)

        self._welcome_title = QLabel("GitKrakit")
        self._welcome_title.setAlignment(Qt.AlignCenter)
        self._welcome_title.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 28pt; font-weight: 700;"
        )
        layout.addWidget(self._welcome_title)

        self._welcome_subtitle = QLabel(
            "Visualise l'historique, prépare tes commits et garde tes branches synchronisées."
        )
        self._welcome_subtitle.setAlignment(Qt.AlignCenter)
        self._welcome_subtitle.setWordWrap(True)
        self._welcome_subtitle.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11pt;")
        layout.addWidget(self._welcome_subtitle)

        self._welcome_open_button = QPushButton(icons.app_icon("open"), "Ouvrir un dépôt Git")
        self._welcome_open_button.setObjectName("primaryButton")
        self._welcome_open_button.setIconSize(QSize(18, 18))
        self._welcome_open_button.setMinimumWidth(190)
        self._welcome_open_button.setToolTip("Choisir un dossier contenant un dépôt Git")
        self._welcome_open_button.clicked.connect(self.open_repo_dialog)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._welcome_open_button)
        button_row.addStretch(1)
        layout.addSpacing(12)
        layout.addLayout(button_row)

        self._welcome_recent_card = QWidget()
        self._welcome_recent_card.setObjectName("welcomeRecentCard")
        self._welcome_recent_layout = QVBoxLayout(self._welcome_recent_card)
        self._welcome_recent_layout.setContentsMargins(12, 10, 12, 10)
        self._welcome_recent_layout.setSpacing(2)
        self._refresh_welcome_recents()
        layout.addSpacing(18)
        layout.addWidget(self._welcome_recent_card, alignment=Qt.AlignHCenter)

        hint = QLabel("Astuce : tu peux aussi épingler tes dépôts dans un espace de travail, à gauche.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(2)
        return page

    def _refresh_welcome_recents(self) -> None:
        """Expose les derniers dépôts dès l'accueil, là où ils sont utiles."""
        if not hasattr(self, "_welcome_recent_layout"):
            return
        layout = self._welcome_recent_layout
        while layout.count():
            item = layout.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()

        title = QLabel("REPRENDRE LE TRAVAIL")
        title.setObjectName("welcomeRecentTitle")
        layout.addWidget(title)
        recent_paths = self.workspace_manager.recent[:4]
        if not recent_paths:
            hint = QLabel("Tes dépôts ouverts récemment apparaîtront ici.")
            hint.setObjectName("welcomeRecentHint")
            layout.addWidget(hint)
            return

        for repo_path in recent_paths:
            button = QPushButton(icons.app_icon("repo", theme.ACCENT, 16), Path(repo_path).name)
            button.setObjectName("welcomeRecentButton")
            button.setIconSize(QSize(16, 16))
            button.setMinimumWidth(280)
            button.setToolTip(repo_path)
            button.setAccessibleName(f"Ouvrir le dépôt récent {repo_path}")
            button.clicked.connect(lambda _checked=False, path=repo_path: self.open_repo(path))
            layout.addWidget(button)

    def _build_diff_page(self, diff_panel: DiffPanel) -> QWidget:
        """Page du diff dans la zone centrale : une barre avec un bouton de
        fermeture (retour au graphe) au-dessus du panneau de diff."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._diff_header = QWidget()
        self._diff_header.setStyleSheet(
            f"background-color: {theme.PANEL_BG}; border-bottom: 1px solid {theme.BORDER};"
        )
        bar_layout = QHBoxLayout(self._diff_header)
        bar_layout.setContentsMargins(4, 4, 4, 4)

        self._diff_close_btn = QToolButton()
        self._diff_close_btn.setIcon(icons.toolbar_icon("back"))
        self._diff_close_btn.setText("Retour au graphe")
        self._diff_close_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._diff_close_btn.setToolTip("Fermer le diff et revenir au graphe")
        self._diff_close_btn.setCursor(Qt.PointingHandCursor)
        self._diff_close_btn.setStyleSheet(
            "QToolButton { border: 1px solid " + theme.BORDER + "; background: " + theme.SURFACE + ";"
            f" color: {theme.TEXT}; padding: 3px 10px; border-radius: 5px; }}"
            f"QToolButton:hover {{ background-color: {theme.BORDER}; border-color: {theme.ACCENT}; }}"
        )
        self._diff_close_btn.clicked.connect(self._close_diff)
        bar_layout.addWidget(self._diff_close_btn)
        bar_layout.addStretch(1)

        layout.addWidget(self._diff_header)
        layout.addWidget(diff_panel, stretch=1)
        return page

    def _close_diff(self) -> None:
        target = self.graph_panel if self.backend.is_open else self.welcome_page
        self.center_stack.setCurrentWidget(target)

    def _build_terminal_dock(self) -> None:
        self.terminal = TerminalDock(self)
        self.terminal.setObjectName("gitTerminalDock")
        self.terminal.command_entered.connect(self._run_terminal_command)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.terminal)
        self.terminal.hide()

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Fichier")
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        self._preferences_action = QAction(icons.app_icon("settings"), "Préférences…", self)
        self._preferences_action.setShortcut("Ctrl+,")
        self._preferences_action.setMenuRole(QAction.PreferencesRole)  # menu applicatif macOS
        self._preferences_action.setToolTip("Activer ou désactiver les agents ACP")
        self._preferences_action.triggered.connect(self._open_preferences)
        file_menu.addAction(self._preferences_action)
        file_menu.addSeparator()
        self._quit_action = QAction(icons.app_icon("close"), "Quitter", self)
        self._quit_action.setShortcut("Ctrl+Q")
        self._quit_action.triggered.connect(self.close)
        file_menu.addAction(self._quit_action)

        repository_menu = self.menuBar().addMenu("&Dépôt")
        for action in (
            self.fetch_action,
            self.pull_action,
            self.push_action,
            self.branch_action,
            self.gitflow_action,
            self.stash_action,
            self.pop_action,
            self.refresh_action,
        ):
            repository_menu.addAction(action)

        view_menu = self.menuBar().addMenu("&Affichage")
        view_menu.addMenu(self._appearance_menu)
        view_menu.addSeparator()
        self._toolbar_toggle_action = self._toolbar.toggleViewAction()
        self._toolbar_toggle_action.setIcon(icons.app_icon("toolbar"))
        self._terminal_toggle_action = self.terminal.toggleViewAction()
        self._terminal_toggle_action.setIcon(icons.app_icon("terminal"))
        view_menu.addAction(self._toolbar_toggle_action)
        view_menu.addAction(self._terminal_toggle_action)

        help_menu = self.menuBar().addMenu("&Aide")
        self._check_updates_action = QAction(
            icons.app_icon("refresh"), "Rechercher des mises à jour…", self
        )
        self._check_updates_action.triggered.connect(self.check_for_updates)
        help_menu.addAction(self._check_updates_action)

    def _build_status_bar(self) -> None:
        self._busy_label = QLabel("")
        self._busy_label.setStyleSheet(f"color: {theme.TEXT}; padding-left: 8px;")
        self._busy_label.hide()
        self.statusBar().addPermanentWidget(self._busy_label)

        self._busy_progress = QProgressBar()
        self._busy_progress.setRange(0, 0)
        self._busy_progress.setTextVisible(False)
        self._busy_progress.setFixedSize(90, 10)
        self._busy_progress.hide()
        self.statusBar().addPermanentWidget(self._busy_progress)

        self._version_label = QLabel(f"v{__version__}")
        self._version_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; padding: 0 8px;")
        self.statusBar().addPermanentWidget(self._version_label)

    # ------------------------------------------------------------------
    # Mises à jour de l'application
    # ------------------------------------------------------------------
    def _connect_updater(self) -> None:
        self._updater.update_available.connect(self._update_banner.show_available)
        self._updater.no_update.connect(self._on_no_update)
        self._updater.check_failed.connect(self._on_update_check_failed)
        self._updater.unavailable.connect(self._on_updater_unavailable)
        self._updater.download_progress.connect(self._update_banner.set_progress)
        self._updater.download_failed.connect(self._on_update_download_failed)
        self._updater.install_ready.connect(self._on_update_install_ready)
        self._update_banner.update_requested.connect(self._start_update_download)

    def start_update_check(self) -> None:
        """Check shortly after startup without delaying the first paint."""
        QTimer.singleShot(1500, lambda: self._updater.check(manual=False))

    def check_for_updates(self) -> None:
        self.statusBar().showMessage("Recherche de mises à jour…")
        if not self._updater.check(manual=True):
            self.statusBar().showMessage("La vérification est déjà en cours.", 3000)

    def _start_update_download(self) -> None:
        self._update_banner.show_downloading()
        self._updater.download()

    def _on_no_update(self, manual: bool) -> None:
        if manual:
            self.statusBar().showMessage("GitKrakit est à jour.", 4000)

    def _on_update_check_failed(self, manual: bool) -> None:
        if manual:
            self.statusBar().showMessage(
                "Impossible de vérifier les mises à jour pour le moment.", 5000
            )

    def _on_updater_unavailable(self, manual: bool) -> None:
        if manual:
            self.statusBar().showMessage(
                "La mise à jour automatique est disponible dans l'application installée.",
                5000,
            )

    def _on_update_download_failed(self, _message: str) -> None:
        self._update_banner.show_retry()
        self.statusBar().showMessage(
            "Téléchargement interrompu ; aucun fichier installé n'a été modifié.", 5000
        )

    def _on_update_install_ready(self) -> None:
        self._update_banner.show_installing()
        QTimer.singleShot(150, self._updater.install_and_restart)

    # ------------------------------------------------------------------
    # Ouverture de dépôt
    # ------------------------------------------------------------------
    def open_repo_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dépôt Git")
        if path:
            self.open_repo(path)

    def open_repo(self, path: str) -> None:
        """Point d'entrée unique pour ouvrir un dépôt (dialogue, sidebar, CLI)."""
        if self._is_busy:
            self.statusBar().showMessage(
                "Attends la fin de l'opération Git avant de changer de dépôt.", 4000
            )
            return
        try:
            self.backend.open(path)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Dépôt Git invalide", str(exc))
            return
        active_path = self.backend.working_dir or path
        try:
            self.workspace_manager.touch_recent(active_path)
        except WorkspaceError as exc:
            QMessageBox.warning(self, "Dépôts récents", str(exc))
        self._refresh_welcome_recents()
        self.sidebar.set_active_repo(active_path)
        self.setWindowTitle(f"GitKrakit — {active_path}")
        self._close_diff()  # un diff affiché appartient à l'ancien dépôt
        self.center_stack.setCurrentWidget(self.graph_panel)
        self._update_action_state()
        self.refresh_all()
        self._auto_fetch()

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
        if not self.backend.is_open or self._is_busy:
            return
        try:
            self.sidebar.update_refs(
                local=self.backend.local_branches(),
                remote=self.backend.remote_branches(),
                tags=self.backend.tags(),
                current_branch=self.backend.current_branch,
                gitflow=self.gitflow.status(),
                ahead_behind=self.backend.branch_ahead_behind(),
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
    # Fetch automatique
    # ------------------------------------------------------------------
    def _auto_fetch(self) -> None:
        """Start a quiet background fetch when no other Git task is active."""
        if not self.backend.is_open:
            return
        self._start_backend_operation(
            self.backend.fetch,
            label="Synchronisation automatique…",
            silent=True,
        )

    # ------------------------------------------------------------------
    # Actions Git
    # ------------------------------------------------------------------
    def _checkout_branch(self, name: str) -> None:
        if self._is_busy:
            return
        try:
            self.backend.checkout(name)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.refresh_all()

    def _merge_branch(self, source: str) -> None:
        if not self.backend.is_open or self._is_busy:
            return
        target = self.backend.current_branch
        answer = QMessageBox.question(
            self,
            "Merge",
            f"Fusionner '{source}' dans '{target}' ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            message = self.backend.merge_branch(source)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            self.refresh_all()
            return
        self.statusBar().showMessage(message, 5000)
        self.refresh_all()

    def _delete_branch(self, name: str) -> None:
        if self._is_busy:
            return
        try:
            self.backend.delete_branch(name, force=force)
        except GitBackendError as exc:
            # git refuse par sécurité de supprimer une branche non fusionnée ;
            # on propose de forcer plutôt que de laisser un message sans issue
            if not force and "not fully merged" in str(exc):
                answer = QMessageBox.warning(
                    self,
                    "Branche non fusionnée",
                    f"La branche '{name}' contient des commits qui ne sont fusionnés "
                    "dans aucune autre branche.\n\n"
                    "Si tu la supprimes quand même, ces commits deviendront orphelins "
                    "(récupérables un temps via le reflog, mais pas depuis le graphe).\n\n"
                    "Forcer la suppression ?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer == QMessageBox.Yes:
                    self._delete_branch(name, force=True)
                return
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.refresh_all()

    def create_branch_dialog(self) -> None:
        if not self.backend.is_open or self._is_busy:
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
        if self._is_busy:
            return
        try:
            self.backend.stage(paths)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
        self._refresh_status()

    def _unstage(self, paths: list[str]) -> None:
        if self._is_busy:
            return
        try:
            self.backend.unstage(paths)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
        self._refresh_status()

    def _commit(self, message: str) -> None:
        if self._is_busy:
            return
        try:
            self.backend.commit(message)
        except GitBackendError as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return
        self.staging_panel.clear_message()
        self.refresh_all()

    def _refresh_acp_agents(self) -> None:
        self.staging_panel.set_available_agents(preferences.enabled_acp_provider_choices())

    def _open_preferences(self) -> None:
        dialog = PreferencesDialog(self)
        dialog.acp_providers_changed.connect(lambda _enabled: self._refresh_acp_agents())
        dialog.exec()

    def _generate_commit_message(self, provider_id: str) -> None:
        if not self.backend.is_open or self._is_busy:
            return
        if provider_id not in preferences.enabled_acp_providers():
            self.statusBar().showMessage(
                "Cet agent ACP est désactivé dans les préférences.", 4000
            )
            return
        working_dir = self.backend.working_dir
        provider = ACP_PROVIDERS.get(provider_id)
        provider_label = provider.label if provider else provider_id

        def generate() -> str:
            diff_text = self.backend.staged_diff()
            return generate_acp_commit_message(provider_id, diff_text, working_dir)

        def generated(message: str) -> None:
            self.staging_panel.set_commit_message(message)
            self.statusBar().showMessage(
                f"Message généré avec {provider_label} — vérifie-le avant de committer.",
                7000,
            )

        self._start_backend_operation(
            generate,
            label=f"{provider_label} analyse le diff indexé via ACP…",
            on_success=generated,
            refresh_after=False,
        )

    @property
    def _is_busy(self) -> bool:
        return self._operation_thread is not None

    def _run_backend_op(
        self,
        fn: Callable[[], Any],
        done_message: str | None = None,
        label: str = "Opération Git en cours…",
    ) -> None:
        """Run a potentially slow Git operation outside the UI thread."""
        self._start_backend_operation(fn, label=label, done_message=done_message)

    def _start_backend_operation(
        self,
        fn: Callable[[], Any],
        *,
        label: str,
        done_message: str | None = None,
        silent: bool = False,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        refresh_after: bool = True,
    ) -> bool:
        if not self.backend.is_open:
            if not silent:
                self.statusBar().showMessage("Aucun dépôt Git n'est ouvert.", 4000)
            return False
        if self._is_busy:
            if not silent:
                self.statusBar().showMessage("Une opération Git est déjà en cours.", 4000)
            return False

        self._operation_label = label
        self._operation_done_message = done_message
        self._operation_silent = silent
        self._operation_refresh = refresh_after
        self._operation_on_success = on_success
        self._operation_on_error = on_error
        self._operation_thread = _OperationThread(fn, self)
        self._operation_thread.finished.connect(self._on_operation_finished)
        self._set_busy(True)
        self._operation_thread.start()
        return True

    def _on_operation_finished(self) -> None:
        thread = self._operation_thread
        if thread is None:
            return

        error = thread.error
        result = thread.result
        silent = self._operation_silent
        refresh_after = self._operation_refresh
        done_message = self._operation_done_message
        on_success = self._operation_on_success
        on_error = self._operation_on_error
        thread.deleteLater()
        self._operation_thread = None
        self._set_busy(False)

        if error is not None:
            message = str(error)
            # A failed pull/merge can still have changed the working tree.
            if refresh_after:
                self.refresh_all(show_errors=False)
            if on_error is not None:
                on_error(message)
            elif silent:
                self.statusBar().showMessage(f"Synchronisation échouée : {message}", 5000)
            else:
                QMessageBox.critical(self, "Opération Git échouée", message)
        else:
            if refresh_after:
                self.refresh_all(show_errors=not silent)
            if on_success is not None:
                on_success(result)
            else:
                message = done_message or (result if isinstance(result, str) else "")
                if silent and message:
                    message = f"Fetch auto : {message}"
                if message:
                    self.statusBar().showMessage(message, 5000)

        if self._close_when_idle:
            self._close_when_idle = False
            QTimer.singleShot(0, self.close)

    def _set_busy(self, busy: bool) -> None:
        self._busy_label.setText(self._operation_label if busy else "")
        self._busy_label.setVisible(busy)
        self._busy_progress.setVisible(busy)
        self._update_action_state()

    def _update_action_state(self) -> None:
        repo_open = self.backend.is_open
        repo_ready = repo_open and not self._is_busy
        self.open_action.setEnabled(not self._is_busy)
        for action in self._repo_actions:
            action.setEnabled(repo_ready)
        if hasattr(self, "staging_panel"):
            self._right_panel.setVisible(repo_open)
            self.staging_panel.setEnabled(repo_ready)
            self._right_panel.setEnabled(repo_ready)
            self.sidebar.refs_tree.setEnabled(repo_ready)
            self.terminal.setEnabled(repo_ready)

    def show_commit_details(self, sha: str) -> None:
        if self._is_busy:
            return
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
        self._start_gitflow_initialization()

    def _start_gitflow_initialization(
        self, after_init: Callable[[], None] | None = None
    ) -> None:
        if not self.backend.is_open or self._is_busy:
            return
        if self.gitflow.is_initialized():
            if after_init is not None:
                after_init()
            else:
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

        def initialized(_result: Any) -> None:
            self.statusBar().showMessage("Git Flow initialisé — branche develop", 5000)
            if after_init is not None:
                after_init()

        self._start_backend_operation(
            self.gitflow.init,
            label="Initialisation de Git Flow…",
            on_success=initialized,
        )

    def _gitflow_start(self, kind: str) -> None:
        if not self.backend.is_open or self._is_busy:
            return
        if not self.gitflow.is_initialized():
            self._start_gitflow_initialization(lambda: self._gitflow_start(kind))
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
        self._run_backend_op(
            lambda: start_fn(name.strip()), label=f"Création de {kind}/{name.strip()}…"
        )

    def _gitflow_finish(self, kind: str, name: str) -> None:
        if self._is_busy:
            return
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
        if self._is_busy:
            return
        diff = self.backend.diff_for_file(path, staged=staged)
        origin = "indexé" if staged else "non indexé"
        self.diff_panel.show_diff(f"{path}  ({origin})", diff, file_path=path)
        self.center_stack.setCurrentWidget(self.diff_page)

    def _show_commit_diff(self, sha: str, path: str) -> None:
        if self._is_busy:
            return
        try:
            diff = self.backend.diff_for_commit_file(sha, path)
        except GitBackendError as exc:
            diff = str(exc)
        self.diff_panel.show_diff(f"{path}  (commit {sha[:7]})", diff, file_path=path)
        self.center_stack.setCurrentWidget(self.diff_page)

    def _run_terminal_command(self, args: list[str]) -> None:
        if not self.backend.is_open:
            self.terminal.append_output("Erreur: aucun dépôt ouvert.")
            return
        self._start_backend_operation(
            lambda: self.backend.run_raw(args),
            label=f"git {args[0]}…" if args else "Commande Git…",
            on_success=lambda output: self.terminal.append_output(output or "(aucune sortie)"),
            on_error=lambda message: self.terminal.append_output(f"Erreur: {message}"),
        )
