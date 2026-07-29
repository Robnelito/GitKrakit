"""
staging_panel.py
Panneau de staging : fichiers non indexés / indexés, message et bouton de
commit. N'appelle jamais le backend directement : il émet des signaux
(stage/unstage/commit) que la fenêtre principale relie à GitBackend.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gitkrakit.core import FileStatus
from gitkrakit.ui.icons import app_icon, status_icon


class StagingPanel(QWidget):
    stage_requested = Signal(list)      # list[str] : chemins à indexer
    unstage_requested = Signal(list)    # list[str] : chemins à désindexer
    commit_requested = Signal(str)      # message de commit
    diff_requested = Signal(str, bool)  # (chemin, staged) : voir le diff
    generate_message_requested = Signal(str)  # fournisseur ACP : codex | claude

    def __init__(self, parent=None):
        super().__init__(parent)
        self._staged_count = 0
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.unstaged_label = QLabel("MODIFICATIONS · 0")
        self.unstaged_label.setToolTip("Fichiers modifiés qui ne seront pas dans le prochain commit")
        layout.addWidget(self.unstaged_label)
        self.unstaged_list = QListWidget()
        self.unstaged_list.setAccessibleName("Fichiers non indexés")
        self.unstaged_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.unstaged_list.setToolTip(
            "Clique un fichier pour voir son diff. Ctrl+clic permet une sélection multiple."
        )
        self.unstaged_list.itemClicked.connect(
            lambda item: self.diff_requested.emit(item.data(Qt.UserRole), False)
        )
        self.unstaged_list.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.unstaged_list)

        self.stage_btn = QPushButton(app_icon("forward"), "Indexer la sélection")
        self.stage_btn.setIconSize(QSize(18, 18))
        self.stage_btn.setToolTip("Ajouter les fichiers sélectionnés au prochain commit")
        self.stage_btn.clicked.connect(self._emit_stage)
        layout.addWidget(self.stage_btn)

        self.staged_label = QLabel("PRÊTS À COMMITTER · 0")
        self.staged_label.setToolTip("Fichiers inclus dans le prochain commit")
        layout.addWidget(self.staged_label)
        self.staged_list = QListWidget()
        self.staged_list.setAccessibleName("Fichiers indexés")
        self.staged_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.staged_list.setToolTip(
            "Clique un fichier pour voir son diff. Ctrl+clic permet une sélection multiple."
        )
        self.staged_list.itemClicked.connect(
            lambda item: self.diff_requested.emit(item.data(Qt.UserRole), True)
        )
        self.staged_list.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.staged_list)

        self.unstage_btn = QPushButton(app_icon("back"), "Retirer la sélection")
        self.unstage_btn.setIconSize(QSize(18, 18))
        self.unstage_btn.setToolTip("Retirer les fichiers sélectionnés du prochain commit")
        self.unstage_btn.clicked.connect(self._emit_unstage)
        layout.addWidget(self.unstage_btn)

        layout.addWidget(QLabel("MESSAGE DU COMMIT"))
        self.commit_message_edit = QPlainTextEdit()
        self.commit_message_edit.setObjectName("commitMessageEdit")
        self.commit_message_edit.setPlaceholderText("Résume clairement la modification…")
        self.commit_message_edit.setAccessibleName("Message du commit")
        self.commit_message_edit.setTabChangesFocus(True)
        self.commit_message_edit.setFixedHeight(86)
        self.commit_message_edit.textChanged.connect(self._update_buttons)
        layout.addWidget(self.commit_message_edit)

        generator_row = QHBoxLayout()
        self.agent_combo = QComboBox()
        self.agent_combo.setAccessibleName("Agent ACP pour le message de commit")
        self.agent_combo.setToolTip("Choisir l'agent local utilisé via ACP")
        generator_row.addWidget(self.agent_combo, stretch=1)

        self.generate_btn = QPushButton(app_icon("sparkles"), "Générer via ACP")
        self.generate_btn.setIconSize(QSize(18, 18))
        self.generate_btn.clicked.connect(self._emit_generate_message)
        self._update_generate_tooltip()
        generator_row.addWidget(self.generate_btn)
        layout.addLayout(generator_row)

        self.commit_btn = QPushButton(app_icon("commit"), "Créer le commit")
        self.commit_btn.setIconSize(QSize(18, 18))
        self.commit_btn.setObjectName("primaryButton")
        self.commit_btn.setShortcut("Ctrl+Return")
        self.commit_btn.setToolTip("Créer le commit (Ctrl+Entrée)")
        self.commit_btn.clicked.connect(self._emit_commit)
        layout.addWidget(self.commit_btn)
        self._update_buttons()

    def apply_theme(self) -> None:
        self.stage_btn.setIcon(app_icon("forward"))
        self.unstage_btn.setIcon(app_icon("back"))
        self.generate_btn.setIcon(app_icon("sparkles"))
        self.commit_btn.setIcon(app_icon("commit"))
        for list_widget in (self.unstaged_list, self.staged_list):
            for index in range(list_widget.count()):
                item = list_widget.item(index)
                item.setIcon(status_icon(item.toolTip()))

    def update_status(self, staged: list[FileStatus], unstaged: list[FileStatus]) -> None:
        self._staged_count = len(staged)
        self._fill(self.staged_list, staged)
        self._fill(self.unstaged_list, unstaged)
        self.staged_label.setText(f"PRÊTS À COMMITTER · {len(staged)}")
        self.unstaged_label.setText(f"MODIFICATIONS · {len(unstaged)}")
        self._update_buttons()

    @staticmethod
    def _fill(list_widget: QListWidget, files: list[FileStatus]) -> None:
        list_widget.clear()
        for f in files:
            item = QListWidgetItem(status_icon(f.status), f.path)
            item.setData(Qt.UserRole, f.path)
            item.setToolTip(f.status)
            list_widget.addItem(item)

    def set_available_agents(self, agents: list[tuple[str, str]]) -> None:
        """Re-fill the ACP agent list, keeping the current choice when possible."""
        previous = self.agent_combo.currentData()
        self.agent_combo.blockSignals(True)
        self.agent_combo.clear()
        for provider_id, label in agents:
            self.agent_combo.addItem(label, provider_id)
        index = self.agent_combo.findData(previous)
        self.agent_combo.setCurrentIndex(max(index, 0))
        self.agent_combo.blockSignals(False)
        self.agent_combo.setEnabled(bool(agents))
        self._update_generate_tooltip()
        self._update_buttons()

    def _update_generate_tooltip(self) -> None:
        if self.agent_combo.count():
            self.generate_btn.setToolTip(
                "Analyser uniquement le diff indexé et proposer un message Conventional Commit"
            )
        else:
            self.generate_btn.setToolTip(
                "Active au moins un agent ACP dans Fichier > Préférences…"
            )

    def clear_message(self) -> None:
        self.commit_message_edit.clear()

    def set_commit_message(self, message: str) -> None:
        self.commit_message_edit.setPlainText(message)
        self.commit_message_edit.setFocus()
        self.commit_message_edit.selectAll()

    def _update_buttons(self) -> None:
        self.stage_btn.setEnabled(bool(self.unstaged_list.selectedItems()))
        self.unstage_btn.setEnabled(bool(self.staged_list.selectedItems()))
        has_message = bool(self.commit_message_edit.toPlainText().strip())
        self.commit_btn.setEnabled(self._staged_count > 0 and has_message)
        self.generate_btn.setEnabled(self._staged_count > 0 and self.agent_combo.count() > 0)

    # ------------------------------------------------------------------
    def _emit_stage(self) -> None:
        paths = self._selected_paths(self.unstaged_list)
        if paths:
            self.stage_requested.emit(paths)

    def _emit_unstage(self) -> None:
        paths = self._selected_paths(self.staged_list)
        if paths:
            self.unstage_requested.emit(paths)

    def _emit_commit(self) -> None:
        self.commit_requested.emit(self.commit_message_edit.toPlainText().strip())

    def _emit_generate_message(self) -> None:
        provider = self.agent_combo.currentData()
        if provider:
            self.generate_message_requested.emit(str(provider))

    @staticmethod
    def _selected_paths(list_widget: QListWidget) -> list[str]:
        return [i.data(Qt.UserRole) for i in list_widget.selectedItems()]
