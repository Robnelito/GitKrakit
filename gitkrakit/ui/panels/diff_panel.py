"""
diff_panel.py
Visionneuse de diff côte à côte façon GitKraken : deux colonnes
(ancien/nouveau) avec numéros de ligne, suppressions en rouge à gauche,
ajouts en vert à droite, lignes remplacées colorées des deux côtés, et
un séparateur pour chaque hunk ("@@ -a,b +c,d @@").

Rendu en modèle/vue : le modèle ne détient que les DiffRow et la
coloration syntaxique est peinte à la demande par un delegate, uniquement
pour les lignes visibles. Le coût d'affichage ne dépend donc plus de la
taille du diff (un widget par cellule coûtait ~1,7 ms par ligne).
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gitkrakit import theme
from gitkrakit.core import DiffRow, parse_unified_diff
from gitkrakit.ui.syntax import detect_language, highlight_spans

_COL_OLD_NO, _COL_OLD_TEXT, _COL_NEW_NO, _COL_NEW_TEXT = range(4)
_CODE_COLUMNS = (_COL_OLD_TEXT, _COL_NEW_TEXT)
_SPANS_ROLE = Qt.UserRole
_CODE_LEFT_PADDING = 12  # 6 px de marge d'item + 6 px de marge du texte
_TAB_WIDTH = 4


def _diff_background(status: str) -> QColor:
    color = QColor(theme.STATUS_COLORS[status])
    color.setAlpha(35)
    return color


class _DiffModel(QAbstractTableModel):
    """Lignes de diff exposées à la vue ; segments colorés calculés à la demande."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[DiffRow] = []
        self._language: str | None = None
        self._spans_cache: dict[tuple[int, int], list[tuple[str, str | None]]] = {}
        self._mono = QFont(theme.MONO_FONT_FAMILY, 9)
        self._mono_bold = QFont(theme.MONO_FONT_FAMILY, 9)
        self._mono_bold.setBold(True)
        self._load_colors()

    def _load_colors(self) -> None:
        self._bg_deleted = _diff_background("deleted")
        self._bg_added = _diff_background("added")
        self._bg_hunk = QColor(theme.PANEL_BG)
        self._fg_muted = QColor(theme.TEXT_MUTED)
        self._fg_accent = QColor(theme.ACCENT)
        self._fg_text = QColor(theme.TEXT)

    @property
    def mono_font(self) -> QFont:
        return self._mono

    def rows(self) -> list[DiffRow]:
        return self._rows

    def set_rows(self, rows: list[DiffRow], language: str | None) -> None:
        self.beginResetModel()
        self._rows = rows
        self._language = language
        self._spans_cache.clear()
        self.endResetModel()

    def refresh_theme(self) -> None:
        """Nouvelle palette/police : repeint sans perdre la position de défilement."""
        self._load_colors()
        self._mono.setFamily(theme.MONO_FONT_FAMILY)
        self._mono_bold.setFamily(theme.MONO_FONT_FAMILY)
        self._spans_cache.clear()
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._rows) - 1, self.columnCount() - 1)
            )

    # -- QAbstractTableModel ------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else 4

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if row.kind in ("hunk", "info"):
            if col != _COL_OLD_NO:
                return self._separator_data(row, role) if role == Qt.BackgroundRole else None
            if role == Qt.DisplayRole:
                return row.label
            if role == Qt.ForegroundRole:
                return self._fg_accent if row.kind == "hunk" else self._fg_muted
            if role == Qt.FontRole:
                return self._mono_bold if row.kind == "hunk" else self._mono
            return self._separator_data(row, role)

        if role == Qt.DisplayRole:
            if col == _COL_OLD_NO:
                return str(row.old_no) if row.old_no else ""
            if col == _COL_NEW_NO:
                return str(row.new_no) if row.new_no else ""
            return (row.old_text if col == _COL_OLD_TEXT else row.new_text) or ""
        if role == _SPANS_ROLE and col in _CODE_COLUMNS:
            return self._spans(index.row(), col, row)
        if role == Qt.BackgroundRole:
            left = col in (_COL_OLD_NO, _COL_OLD_TEXT)
            if left and row.kind in ("del", "mod"):
                return self._bg_deleted
            if not left and row.kind in ("add", "mod"):
                return self._bg_added
            return None
        if role == Qt.ForegroundRole:
            return self._fg_muted if col not in _CODE_COLUMNS else self._fg_text
        if role == Qt.FontRole:
            return self._mono
        if role == Qt.TextAlignmentRole and col in (_COL_OLD_NO, _COL_NEW_NO):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def _separator_data(self, row: DiffRow, role: int):
        if role == Qt.BackgroundRole and row.kind == "hunk":
            return self._bg_hunk
        return None

    def _spans(self, row_index: int, col: int, row: DiffRow) -> list[tuple[str, str | None]]:
        key = (row_index, col)
        spans = self._spans_cache.get(key)
        if spans is None:
            text = row.old_text if col == _COL_OLD_TEXT else row.new_text
            spans = highlight_spans(text or "", self._language)
            self._spans_cache[key] = spans
        return spans


class _CodeDelegate(QStyledItemDelegate):
    """Peint une ligne de code colorée sans créer de widget."""

    def paint(self, painter, option, index) -> None:
        background = index.data(Qt.BackgroundRole)
        if background is not None:
            painter.fillRect(option.rect, background)
        spans = index.data(_SPANS_ROLE)
        if not spans:
            return

        font = index.data(Qt.FontRole) or option.font
        metrics = QFontMetrics(font)
        rect = option.rect
        x = rect.left() + _CODE_LEFT_PADDING
        baseline = rect.top() + (rect.height() + metrics.ascent() - metrics.descent()) // 2
        default_color = QColor(theme.TEXT)

        painter.save()
        painter.setClipRect(rect)
        painter.setFont(font)
        for text, color in spans:
            text = text.replace("\t", " " * _TAB_WIDTH)
            painter.setPen(QColor(color) if color else default_color)
            painter.drawText(QPoint(x, baseline), text)
            x += metrics.horizontalAdvance(text)
            if x > rect.right():
                break
        painter.restore()


class DiffPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
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

        self.model = _DiffModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setAlternatingRowColors(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setItemDelegateForColumn(_COL_OLD_TEXT, _CodeDelegate(self.table))
        self.table.setItemDelegateForColumn(_COL_NEW_TEXT, _CodeDelegate(self.table))
        self._apply_table_style()

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_OLD_NO, QHeaderView.Fixed)
        header.setSectionResizeMode(_COL_NEW_NO, QHeaderView.Fixed)
        header.setSectionResizeMode(_COL_OLD_TEXT, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_NEW_TEXT, QHeaderView.Stretch)
        self.table.setColumnWidth(_COL_OLD_NO, 46)
        self.table.setColumnWidth(_COL_NEW_NO, 46)
        # hauteur de ligne fixe : la vue n'a pas à mesurer chaque ligne
        vertical = self.table.verticalHeader()
        vertical.setSectionResizeMode(QHeaderView.Fixed)
        vertical.setDefaultSectionSize(20)

        layout.addWidget(self.table, stretch=1)

    def _apply_table_style(self) -> None:
        self.table.setStyleSheet(
            f"QTableView {{ background-color: {theme.BACKGROUND}; border: 1px solid {theme.BORDER}; "
            "border-radius: 6px; gridline-color: transparent; }"
            "QTableView::item { padding: 0px 6px; }"
        )

    def apply_theme(self) -> None:
        self.title_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: '{theme.MONO_FONT_FAMILY}', monospace;"
        )
        self.summary_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 9pt;")
        self._apply_table_style()
        self.model.refresh_theme()

    def show_diff(self, title: str, diff_text: str, file_path: str = "") -> None:
        self._current_title = title
        self._current_diff_text = diff_text
        self._current_file_path = file_path
        self.title_label.setText(title)
        language = detect_language(file_path) if file_path else None
        rows = parse_unified_diff(diff_text) if diff_text else []
        added = sum(1 for row in rows if row.kind in ("add", "mod"))
        deleted = sum(1 for row in rows if row.kind in ("del", "mod"))
        self.summary_label.setText(f"+{added}  −{deleted}" if rows else "")

        if not rows:
            message = "(fichier binaire)" if "Binary files" in diff_text else "(aucune différence)"
            rows = [DiffRow("info", label=message)]

        self.table.clearSpans()
        self.model.set_rows(rows, language)
        for index, row in enumerate(rows):
            if row.kind in ("hunk", "info"):
                self.table.setSpan(index, _COL_OLD_NO, 1, 4)
        self.table.scrollToTop()
