"""
details_panel.py
Panneau "Détails du commit" façon GitKraken : sha + parents, message dans
un encadré, auteur/date, puis la liste des fichiers modifiés par le
commit, colorée selon leur état.
"""
from __future__ import annotations

from PySide6.QtGui import QBrush, QColor
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


class DetailsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.sha_label = QLabel("Sélectionne un commit dans le graphe")
        self.sha_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: Consolas, monospace;"
        )
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
        layout.addWidget(self.author_label)

        self.parents_label = QLabel("")
        self.parents_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: Consolas, monospace;"
        )
        layout.addWidget(self.parents_label)

        self.files_label = QLabel("")
        layout.addWidget(self.files_label)

        self.files_list = QListWidget()
        layout.addWidget(self.files_list, stretch=1)

    def show_commit(self, commit: CommitInfo, files: list[FileStatus]) -> None:
        self.sha_label.setText(f"commit : {commit.short_sha}")
        self.message_label.setText(commit.message)
        self.message_frame.show()
        self.author_label.setText(
            f"{commit.author} <{commit.author_email}> — {commit.date:%d/%m/%Y @ %H:%M}"
        )
        parents = ", ".join(p[:7] for p in commit.parents) or "(racine)"
        self.parents_label.setText(f"parents : {parents}")

        refs = f" · {', '.join(commit.refs)}" if commit.refs else ""
        self.files_label.setText(f"{len(files)} fichier(s) modifié(s){refs}")

        self.files_list.clear()
        for f in files:
            item = QListWidgetItem(f"[{f.status}] {f.path}")
            color = theme.STATUS_COLORS.get(f.status)
            if color:
                item.setForeground(QBrush(QColor(color)))
            self.files_list.addItem(item)
