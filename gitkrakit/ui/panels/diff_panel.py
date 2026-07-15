"""
diff_panel.py
Visionneuse de diff côte à côte façon GitKraken : deux colonnes
(ancien/nouveau) avec numéros de ligne, suppressions en rouge à gauche,
ajouts en vert à droite, lignes remplacées colorées des deux côtés, et
un séparateur pour chaque hunk ("@@ -a,b +c,d @@").
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gitkrakit import theme
from gitkrakit.core import DiffRow, parse_unified_diff
from gitkrakit.ui.syntax import detect_language, highlight_line

_COL_OLD_NO, _COL_OLD_TEXT, _COL_NEW_NO, _COL_NEW_TEXT = range(4)

def _diff_background(status: str) -> QColor:
    color = QColor(theme.STATUS_COLORS[status])
    color.setAlpha(35)
    return color


class DiffPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._language: str | None = None
        self._current_title = "Clique un fichier pour voir son diff"
        self._current_diff_text = ""
        self._current_file_path = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.title_label = QLabel("Clique un fichier pour voir son diff")
        self.title_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: '{theme.MONO_FONT_FAMILY}', monospace;"
        )
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label = QLabel("")
        self.summary_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.summary_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 9pt;")
        title_row = QHBoxLayout()
        title_row.addWidget(self.title_label, stretch=1)
        title_row.addWidget(self.summary_label)
        layout.addLayout(title_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Ancien", "", "Nouveau"])
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setAlternatingRowColors(False)
        self.table.setStyleSheet(
            f"QTableWidget {{ background-color: {theme.BACKGROUND}; border: 1px solid {theme.BORDER}; "
            "border-radius: 6px; gridline-color: transparent; }"
            f"QTableWidget::item {{ padding: 0px 6px; }}"
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_OLD_NO, QHeaderView.Fixed)
        header.setSectionResizeMode(_COL_NEW_NO, QHeaderView.Fixed)
        header.setSectionResizeMode(_COL_OLD_TEXT, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_NEW_TEXT, QHeaderView.Stretch)
        self.table.setColumnWidth(_COL_OLD_NO, 46)
        self.table.setColumnWidth(_COL_NEW_NO, 46)
        self.table.verticalHeader().setDefaultSectionSize(20)

        self._mono_font = QFont(theme.MONO_FONT_FAMILY, 9)
        self._mono_font_bold = QFont(theme.MONO_FONT_FAMILY, 9)
        self._mono_font_bold.setBold(True)

        layout.addWidget(self.table, stretch=1)

    def apply_theme(self) -> None:
        self.title_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: '{theme.MONO_FONT_FAMILY}', monospace;"
        )
        self._mono_font.setFamily(theme.MONO_FONT_FAMILY)
        self._mono_font_bold.setFamily(theme.MONO_FONT_FAMILY)
        self.summary_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 9pt;")
        self.table.setStyleSheet(
            f"QTableWidget {{ background-color: {theme.BACKGROUND}; border: 1px solid {theme.BORDER}; "
            "border-radius: 6px; gridline-color: transparent; }"
            "QTableWidget::item { padding: 0px 6px; }"
        )
        self.show_diff(
            self._current_title,
            self._current_diff_text,
            self._current_file_path,
        )

    def show_diff(self, title: str, diff_text: str, file_path: str = "") -> None:
        self._current_title = title
        self._current_diff_text = diff_text
        self._current_file_path = file_path
        self.title_label.setText(title)
        self._language = detect_language(file_path) if file_path else None
        rows = parse_unified_diff(diff_text) if diff_text else []
        added = sum(1 for row in rows if row.kind in ("add", "mod"))
        deleted = sum(1 for row in rows if row.kind in ("del", "mod"))
        self.summary_label.setText(f"+{added}  −{deleted}" if rows else "")

        self.table.setRowCount(0)
        if not rows:
            self.table.setRowCount(1)
            self._set_cell(0, _COL_OLD_TEXT, "(aucune différence)", theme.TEXT_MUTED)
            self.table.setSpan(0, _COL_OLD_TEXT, 1, 3)
            return

        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._fill_row(i, row)

    def _fill_row(self, i: int, row: DiffRow) -> None:
        if row.kind == "hunk":
            self._set_cell(i, _COL_OLD_NO, row.label, theme.ACCENT, bold=True, center=False)
            self.table.item(i, _COL_OLD_NO).setBackground(QColor(theme.PANEL_BG))
            self.table.setSpan(i, _COL_OLD_NO, 1, 4)
            for col in (_COL_OLD_TEXT, _COL_NEW_NO, _COL_NEW_TEXT):
                self._set_cell(i, col, "", theme.TEXT)
            return

        left_bg = _diff_background("deleted") if row.kind in ("del", "mod") else None
        right_bg = _diff_background("added") if row.kind in ("add", "mod") else None

        self._set_cell(i, _COL_OLD_NO, str(row.old_no) if row.old_no else "", theme.TEXT_MUTED, bg=left_bg)
        self._set_cell(i, _COL_NEW_NO, str(row.new_no) if row.new_no else "", theme.TEXT_MUTED, bg=right_bg)
        self.table.setCellWidget(i, _COL_OLD_TEXT, self._code_label(row.old_text, left_bg))
        self.table.setCellWidget(i, _COL_NEW_TEXT, self._code_label(row.new_text, right_bg))

    def _code_label(self, text: str | None, bg: QColor | None) -> QLabel:
        """Cellule de code avec coloration syntaxique (rich text) — un
        QLabel plutôt qu'un QTableWidgetItem, car un item ne peut porter
        qu'une seule couleur alors qu'une ligne de code en a plusieurs."""
        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setFont(self._mono_font)
        label.setContentsMargins(6, 0, 6, 0)
        background = f"rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()})" if bg else "transparent"
        label.setStyleSheet(f"color: {theme.TEXT}; background-color: {background}; border: none;")
        if text:
            label.setText(highlight_line(text, self._language))
        return label

    def _set_cell(
        self,
        row: int,
        col: int,
        text: str,
        color: str,
        bg: QColor | None = None,
        bold: bool = False,
        center: bool = True,
    ) -> None:
        item = QTableWidgetItem(text)
        item.setFont(self._mono_font_bold if bold else self._mono_font)
        item.setForeground(QColor(color))
        if bg is not None:
            item.setBackground(bg)
        if col in (_COL_OLD_NO, _COL_NEW_NO) and center:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, col, item)
