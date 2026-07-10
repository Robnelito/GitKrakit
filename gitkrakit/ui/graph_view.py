"""
graph_view.py
Rendu du graphe de commits façon GitKraken : chaque commit occupe une
ligne pleine largeur découpée en colonnes — pastilles branche/tag,
lanes du graphe, message (élidé), date. Toute la ligne est cliquable et
surlignée au survol ; la ligne sélectionnée reste en surbrillance.

GraphPanel = en-tête de colonnes fixe + GraphView (QGraphicsView).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from gitkrakit.core import GraphLayout, GraphNode
from gitkrakit import theme

ROW_HEIGHT = 28
LANE_WIDTH = 16
NODE_RADIUS = 5
MERGE_NODE_RADIUS = 3.5
REF_COL_WIDTH = 160   # colonne "branche / tag"
MSG_COL_WIDTH = 480   # colonne message (élidé au-delà)
DATE_COL_WIDTH = 150
CHIP_PADDING = 7
MAX_VISIBLE_REFS = 2  # au-delà : pastille "+N"


class CommitRowItem(QGraphicsRectItem):
    """Fond pleine largeur d'une ligne : teinte lane, survol, sélection."""

    def __init__(self, node: GraphNode, view: "GraphView", width: float):
        super().__init__(0, node.row * ROW_HEIGHT, width, ROW_HEIGHT)
        self.node = node
        self._view = view
        self._hovered = False

        tint = QColor(node.color)
        tint.setAlpha(14)
        self._base_brush = QBrush(tint)

        hover = QColor(theme.SURFACE)
        hover.setAlpha(150)
        self._hover_brush = QBrush(hover)

        selected = QColor(theme.ACCENT_DIM)
        selected.setAlpha(110)
        self._selected_brush = QBrush(selected)

        self.setPen(QPen(Qt.NoPen))
        self.setZValue(0)
        self.setAcceptHoverEvents(True)
        self.update_state()

    def update_state(self) -> None:
        if self._view.selected_sha == self.node.commit.sha:
            self.setBrush(self._selected_brush)
        elif self._hovered:
            self.setBrush(self._hover_brush)
        else:
            self.setBrush(self._base_brush)

    def mousePressEvent(self, event):
        self._view.select_commit(self.node.commit.sha)
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update_state()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update_state()
        super().hoverLeaveEvent(event)


class CommitNodeItem(QGraphicsEllipseItem):
    def __init__(self, node: GraphNode, view: "GraphView"):
        r = MERGE_NODE_RADIUS if len(node.commit.parents) > 1 else NODE_RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.node = node
        self._view = view
        self.setBrush(QBrush(QColor(node.color)))
        self.setPen(QPen(QColor(theme.BACKGROUND), 2))
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self._view.select_commit(self.node.commit.sha)
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor(theme.HIGHLIGHT), 2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor(theme.BACKGROUND), 2))
        super().hoverLeaveEvent(event)


class GraphView(QGraphicsView):
    commit_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        # sans ça, Qt centre la scène quand elle est plus petite que la vue
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(theme.BACKGROUND)))

        self._graph_layout: GraphLayout | None = None
        self._rows: dict[str, CommitRowItem] = {}
        self._content_width = 0.0
        self.selected_sha: str | None = None
        self.graph_col_width = 120  # exposé pour aligner l'en-tête de colonnes

        self._ui_font = QFont("Segoe UI", 9)
        self._chip_font = QFont("Segoe UI", 8)

    def set_commits(self, commits) -> None:
        self._graph_layout = GraphLayout(commits)
        self._redraw()

    def select_commit(self, sha: str) -> None:
        previous = self._rows.get(self.selected_sha)
        self.selected_sha = sha
        if previous is not None:
            previous.update_state()
        current = self._rows.get(sha)
        if current is not None:
            current.update_state()
        self.commit_selected.emit(sha)

    # ------------------------------------------------------------------
    def _redraw(self) -> None:
        self._scene.clear()
        self._rows.clear()
        if not self._graph_layout:
            return

        layout = self._graph_layout
        graph_x = REF_COL_WIDTH + 12
        self.graph_col_width = (layout.lane_count + 1) * LANE_WIDTH + 12
        msg_x = graph_x + self.graph_col_width
        date_x = msg_x + MSG_COL_WIDTH + 12
        total_width = date_x + DATE_COL_WIDTH

        # 0. fonds de ligne (cliquables, survol/sélection)
        for node in layout.nodes:
            row = CommitRowItem(node, self, total_width)
            self._scene.addItem(row)
            self._rows[node.commit.sha] = row

        # 1. lignes commit -> parents
        for node in layout.nodes:
            x0 = graph_x + node.lane * LANE_WIDTH
            y0 = node.row * ROW_HEIGHT + ROW_HEIGHT / 2
            pen = QPen(QColor(node.color), 2)
            pen.setCapStyle(Qt.RoundCap)
            for parent_lane, parent_row in node.parent_lanes:
                x1 = graph_x + parent_lane * LANE_WIDTH
                y1 = parent_row * ROW_HEIGHT + ROW_HEIGHT / 2
                line = QGraphicsLineItem(x0, y0, x1, y1)
                line.setPen(pen)
                line.setZValue(1)
                self._scene.addItem(line)

        # 2. noeuds + colonnes texte
        metrics = QFontMetricsF(self._ui_font)
        for node in layout.nodes:
            y_center = node.row * ROW_HEIGHT + ROW_HEIGHT / 2

            item = CommitNodeItem(node, self)
            item.setPos(graph_x + node.lane * LANE_WIDTH, y_center)
            self._scene.addItem(item)

            self._draw_refs(node, y_center)

            is_merge = len(node.commit.parents) > 1
            message = metrics.elidedText(node.commit.message, Qt.ElideRight, MSG_COL_WIDTH)
            self._draw_text(
                message,
                self._ui_font,
                theme.TEXT_MUTED if is_merge else theme.TEXT,
                msg_x,
                y_center,
            )

            date_text = f"{node.commit.date:%d/%m/%Y @ %H:%M}"
            self._draw_text(date_text, self._ui_font, theme.TEXT_MUTED, date_x, y_center)

        total_height = len(layout.nodes) * ROW_HEIGHT + ROW_HEIGHT / 2
        self._content_width = total_width
        self._scene.setSceneRect(QRectF(0, 0, total_width, total_height))
        self._stretch_rows()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._stretch_rows()

    def _stretch_rows(self) -> None:
        """Étire les fonds de ligne jusqu'au bord droit de la vue quand le
        contenu est plus étroit que le viewport (façon table pleine largeur)."""
        if not self._rows:
            return
        width = max(self._content_width, float(self.viewport().width()))
        for row in self._rows.values():
            rect = row.rect()
            rect.setWidth(width)
            row.setRect(rect)
        scene_rect = self._scene.sceneRect()
        scene_rect.setWidth(width)
        self._scene.setSceneRect(scene_rect)

    def _draw_refs(self, node: GraphNode, y_center: float) -> None:
        """Pastilles branche/tag dans la colonne de gauche ; au-delà de
        MAX_VISIBLE_REFS, une pastille "+N" résume le reste."""
        refs = node.commit.refs
        if not refs:
            return
        visible = refs[:MAX_VISIBLE_REFS]
        overflow = len(refs) - len(visible)

        x = 6.0
        for ref in visible:
            x = self._draw_chip(ref, node.color, x, y_center, max_width=REF_COL_WIDTH - 40) + 4
        if overflow > 0:
            self._draw_chip(f"+{overflow}", node.color, x, y_center, max_width=40)

    def _draw_chip(
        self, text: str, color: str, x: float, y_center: float, max_width: float
    ) -> float:
        metrics = QFontMetricsF(self._chip_font)
        label_text = metrics.elidedText(text, Qt.ElideRight, max_width - 2 * CHIP_PADDING)
        width = metrics.horizontalAdvance(label_text) + 2 * CHIP_PADDING
        height = metrics.height() + 4

        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y_center - height / 2, width, height), 4, 4)
        chip = QGraphicsPathItem(path)
        background = QColor(color)
        background.setAlpha(38)
        chip.setBrush(QBrush(background))
        chip.setPen(QPen(QColor(color), 1))
        chip.setZValue(4)
        self._scene.addItem(chip)

        label = QGraphicsSimpleTextItem(label_text)
        label.setFont(self._chip_font)
        label.setBrush(QBrush(QColor(color)))
        label.setPos(x + CHIP_PADDING, y_center - metrics.height() / 2)
        label.setZValue(5)
        self._scene.addItem(label)
        return x + width

    def _draw_text(self, text: str, font: QFont, color: str, x: float, y_center: float) -> None:
        item = QGraphicsSimpleTextItem(text)
        item.setFont(font)
        item.setBrush(QBrush(QColor(color)))
        item.setPos(x, y_center - QFontMetricsF(font).height() / 2)
        item.setZValue(5)
        self._scene.addItem(item)


class GraphPanel(QWidget):
    """En-tête de colonnes fixe + vue du graphe."""

    commit_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(
            f"background-color: {theme.PANEL_BG}; border-bottom: 1px solid {theme.BORDER};"
        )
        # colonnes alignées sur les positions x de la scène (spacing 0,
        # largeurs identiques à celles utilisées dans GraphView._redraw)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 4, 0, 4)
        header_layout.setSpacing(0)

        def col_label(text: str) -> QLabel:
            label = QLabel(text.upper())
            label.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 8pt; font-weight: bold;"
                "background: transparent; border: none; padding-left: 6px;"
            )
            return label

        self._ref_header = col_label("Branche / Tag")
        self._ref_header.setFixedWidth(REF_COL_WIDTH + 12)
        header_layout.addWidget(self._ref_header)

        self._graph_header = col_label("Graphe")
        self._graph_header.setFixedWidth(120)
        header_layout.addWidget(self._graph_header)

        message_header = col_label("Message de commit")
        message_header.setFixedWidth(MSG_COL_WIDTH + 12)
        header_layout.addWidget(message_header)

        header_layout.addWidget(col_label("Date / Heure"))
        header_layout.addStretch(1)

        layout.addWidget(header)

        self.view = GraphView()
        self.view.commit_selected.connect(self.commit_selected)
        layout.addWidget(self.view)

    def set_commits(self, commits) -> None:
        self.view.set_commits(commits)
        self._graph_header.setFixedWidth(self.view.graph_col_width)
