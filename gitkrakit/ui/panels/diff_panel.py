"""
diff_panel.py
Visionneuse de diff : affiche le diff git d'un fichier (working tree ou
commit) avec coloration des lignes ajoutées/supprimées/entêtes de hunk.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from gitkrakit import theme


class DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)

        def fmt(color: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            return f

        self._added = fmt(theme.STATUS_COLORS["added"])
        self._removed = fmt(theme.STATUS_COLORS["deleted"])
        self._hunk = fmt(theme.ACCENT, bold=True)
        self._meta = fmt(theme.TEXT_MUTED)

    def highlightBlock(self, text: str) -> None:
        if text.startswith("+++") or text.startswith("---"):
            self.setFormat(0, len(text), self._meta)
        elif text.startswith("@@"):
            self.setFormat(0, len(text), self._hunk)
        elif text.startswith("+"):
            self.setFormat(0, len(text), self._added)
        elif text.startswith("-"):
            self.setFormat(0, len(text), self._removed)
        elif text.startswith(("diff --git", "index ", "new file", "deleted file", "rename ")):
            self.setFormat(0, len(text), self._meta)


class DiffPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.title_label = QLabel("Clique un fichier pour voir son diff")
        self.title_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: Consolas, monospace;"
        )
        layout.addWidget(self.title_label)

        self.diff_view = QPlainTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.diff_view)

        self._highlighter = DiffHighlighter(self.diff_view.document())

    def show_diff(self, title: str, diff_text: str) -> None:
        self.title_label.setText(title)
        self.diff_view.setPlainText(diff_text or "(aucune différence)")
