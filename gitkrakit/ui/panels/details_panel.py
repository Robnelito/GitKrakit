"""
details_panel.py
Panneau "Détails du commit" façon GitKraken : sha + parents, message dans
un encadré, auteur/date, puis la liste des fichiers modifiés par le
commit, colorée selon leur état.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gitkrakit import theme
from gitkrakit.core import CommitInfo, FileStatus
from gitkrakit.ui.icons import status_icon


class DetailsPanel(QWidget):
    file_diff_requested = Signal(str, str)  # (sha, chemin)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_sha: str | None = None
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.sha_label = QLabel("Sélectionne un commit dans le graphe")
        self.sha_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: '{theme.MONO_FONT_FAMILY}', monospace;"
        )
        self.sha_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.sha_label)

        self.message_frame = QFrame()
        self.message_frame.setStyleSheet(
            f"background-color: {theme.PANEL_BG}; border: 1px solid {theme.BORDER};"
            "border-radius: 6px;"
        )
        frame_layout = QVBoxLayout(self.message_frame)
        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 11pt; background: transparent; border: none;"
        )
        frame_layout.addWidget(self.message_label)
        self.message_frame.hide()
        layout.addWidget(self.message_frame)

        self.author_label = QLabel("")
        self.author_label.setWordWrap(True)
        self.author_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.author_label)

        self.parents_label = QLabel("")
        self.parents_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: '{theme.MONO_FONT_FAMILY}', monospace;"
        )
        self.parents_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.parents_label)

        self.files_label = QLabel("")
        layout.addWidget(self.files_label)

        self.files_list = QListWidget()
        self.files_list.setAccessibleName("Fichiers modifiés par le commit")
        self.files_list.setToolTip("Clique un fichier pour afficher son diff")
        self.files_list.itemClicked.connect(self._on_file_clicked)
        layout.addWidget(self.files_list, stretch=1)

    def apply_theme(self) -> None:
        self.sha_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: '{theme.MONO_FONT_FAMILY}', monospace;"
        )
        self.message_frame.setStyleSheet(
            f"background-color: {theme.PANEL_BG}; border: 1px solid {theme.BORDER};"
            "border-radius: 6px;"
        )
        self.message_label.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 11pt; background: transparent; border: none;"
        )
        self.parents_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: '{theme.MONO_FONT_FAMILY}', monospace;"
        )
        for index in range(self.files_list.count()):
            item = self.files_list.item(index)
            item.setIcon(status_icon(item.toolTip()))

    def _on_file_clicked(self, item: QListWidgetItem) -> None:
        if self._current_sha:
            self.file_diff_requested.emit(self._current_sha, item.data(Qt.UserRole))

    def show_commit(self, commit: CommitInfo, files: list[FileStatus]) -> None:
        self._current_sha = commit.sha
        self.sha_label.setText(f"COMMIT {commit.short_sha}")
        self.sha_label.setToolTip(commit.sha)
        self.message_label.setText(commit.message)
        self.message_frame.show()
        self.author_label.setText(
            f"{commit.author} <{commit.author_email}> — {commit.date:%d/%m/%Y @ %H:%M}"
        )
        parents = ", ".join(p[:7] for p in commit.parents) or "(racine)"
        self.parents_label.setText(f"Parents : {parents}")

        refs = f" · {', '.join(commit.refs)}" if commit.refs else ""
        self.files_label.setText(f"{len(files)} fichier(s) modifié(s){refs}")

        self.files_list.clear()
        for f in files:
            item = QListWidgetItem(status_icon(f.status), f.path)
            item.setData(Qt.UserRole, f.path)
            item.setToolTip(f.status)
            self.files_list.addItem(item)
