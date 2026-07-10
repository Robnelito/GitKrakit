"""
staging_panel.py
Panneau de staging : fichiers non indexés / indexés, message et bouton de
commit. N'appelle jamais le backend directement : il émet des signaux
(stage/unstage/commit) que la fenêtre principale relie à GitBackend.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gitkrakit.core import FileStatus
from gitkrakit.ui.icons import status_icon


class StagingPanel(QWidget):
    stage_requested = Signal(list)      # list[str] : chemins à indexer
    unstage_requested = Signal(list)    # list[str] : chemins à désindexer
    commit_requested = Signal(str)      # message de commit
    diff_requested = Signal(str, bool)  # (chemin, staged) : voir le diff

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Fichiers modifiés (non indexés)"))
        self.unstaged_list = QListWidget()
        self.unstaged_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.unstaged_list.itemClicked.connect(
            lambda item: self.diff_requested.emit(item.data(Qt.UserRole), False)
        )
        layout.addWidget(self.unstaged_list)

        stage_btn = QPushButton("Indexer (stage) →")
        stage_btn.clicked.connect(self._emit_stage)
        layout.addWidget(stage_btn)

        layout.addWidget(QLabel("Fichiers indexés (staged)"))
        self.staged_list = QListWidget()
        self.staged_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.staged_list.itemClicked.connect(
            lambda item: self.diff_requested.emit(item.data(Qt.UserRole), True)
        )
        layout.addWidget(self.staged_list)

        unstage_btn = QPushButton("← Désindexer (unstage)")
        unstage_btn.clicked.connect(self._emit_unstage)
        layout.addWidget(unstage_btn)

        layout.addWidget(QLabel("Message de commit"))
        self.commit_message_edit = QTextEdit()
        self.commit_message_edit.setFixedHeight(80)
        layout.addWidget(self.commit_message_edit)

        commit_btn = QPushButton("Commit")
        commit_btn.clicked.connect(self._emit_commit)
        layout.addWidget(commit_btn)

    def update_status(self, staged: list[FileStatus], unstaged: list[FileStatus]) -> None:
        self._fill(self.staged_list, staged)
        self._fill(self.unstaged_list, unstaged)

    @staticmethod
    def _fill(list_widget: QListWidget, files: list[FileStatus]) -> None:
        list_widget.clear()
        for f in files:
            item = QListWidgetItem(status_icon(f.status), f.path)
            item.setData(Qt.UserRole, f.path)
            item.setToolTip(f.status)
            list_widget.addItem(item)

    def clear_message(self) -> None:
        self.commit_message_edit.clear()

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

    @staticmethod
    def _selected_paths(list_widget: QListWidget) -> list[str]:
        return [i.data(Qt.UserRole) for i in list_widget.selectedItems()]
