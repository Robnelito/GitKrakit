"""
details_panel.py
Panneau "Détails du commit" : affichage en lecture seule des métadonnées
et du message du commit sélectionné dans le graphe.
"""
from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from gitkrakit.core import CommitInfo


class DetailsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.commit_details = QPlainTextEdit()
        self.commit_details.setReadOnly(True)
        layout.addWidget(self.commit_details)

    def show_commit(self, commit: CommitInfo) -> None:
        text = (
            f"Commit    : {commit.sha}\n"
            f"Auteur    : {commit.author} <{commit.author_email}>\n"
            f"Date      : {commit.date:%Y-%m-%d %H:%M:%S}\n"
            f"Parents   : {', '.join(p[:7] for p in commit.parents) or '(racine)'}\n"
            f"Refs      : {', '.join(commit.refs) or '-'}\n\n"
            f"Message   :\n{commit.message}\n"
        )
        self.commit_details.setPlainText(text)
