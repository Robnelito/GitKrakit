"""
graph_view.py
Rendu graphique du graphe de commits (QGraphicsView) : un cercle par
commit, des lignes reliant chaque commit à ses parents, colorées par lane,
les refs (branches/tags) en pastilles colorées, puis sha/message/auteur.
Cliquer sur un commit émet un signal avec son sha pour que la fenêtre
principale affiche les détails.
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
    QGraphicsSimpleTextItem,
)

from gitkrakit.core import GraphLayout, GraphNode
from gitkrakit import theme

ROW_HEIGHT = 34
LANE_WIDTH = 22
NODE_RADIUS = 6
LEFT_MARGIN = 24
CHIP_PADDING = 7   # marge horizontale interne des pastilles de refs
PART_SPACING = 10  # espace entre pastilles / sha / message


class CommitNodeItem(QGraphicsEllipseItem):
    def __init__(self, node: GraphNode, view: "GraphView"):
        r = NODE_RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.node = node
        self._view = view
        self.setBrush(QBrush(QColor(node.color)))
        self.setPen(QPen(QColor(theme.BACKGROUND), 2))
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self._view.commit_selected.emit(self.node.commit.sha)
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
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(theme.BACKGROUND)))
        self.layout: GraphLayout | None = None

        self._ui_font = QFont("Segoe UI", 9)
        self._mono_font = QFont("Consolas", 9)
        self._chip_font = QFont("Segoe UI", 8)

    def set_commits(self, commits) -> None:
        self.layout = GraphLayout(commits)
        self._redraw()

    def _redraw(self) -> None:
        self._scene.clear()
        if not self.layout:
            return

        text_x = LEFT_MARGIN + (self.layout.lane_count + 1) * LANE_WIDTH
        max_x = text_x

        # 1. lignes commit -> parents (sous les noeuds)
        for node in self.layout.nodes:
            x0 = LEFT_MARGIN + node.lane * LANE_WIDTH
            y0 = node.row * ROW_HEIGHT + ROW_HEIGHT / 2
            pen = QPen(QColor(node.color), 2)
            pen.setCapStyle(Qt.RoundCap)
            for parent_lane, parent_row in node.parent_lanes:
                x1 = LEFT_MARGIN + parent_lane * LANE_WIDTH
                y1 = parent_row * ROW_HEIGHT + ROW_HEIGHT / 2
                line = QGraphicsLineItem(x0, y0, x1, y1)
                line.setPen(pen)
                line.setZValue(1)
                self._scene.addItem(line)

        # 2. noeuds + texte de la ligne
        for node in self.layout.nodes:
            x = LEFT_MARGIN + node.lane * LANE_WIDTH
            y_center = node.row * ROW_HEIGHT + ROW_HEIGHT / 2

            item = CommitNodeItem(node, self)
            item.setPos(x, y_center)
            self._scene.addItem(item)

            end_x = self._draw_row_text(node, text_x, y_center)
            max_x = max(max_x, end_x)

        total_height = len(self.layout.nodes) * ROW_HEIGHT + ROW_HEIGHT
        self._scene.setSceneRect(QRectF(0, 0, max_x + 40, total_height))

    def _draw_row_text(self, node: GraphNode, x: float, y_center: float) -> float:
        """Dessine pastilles de refs, sha, message et auteur/date.
        Retourne la position x atteinte (pour dimensionner la scène)."""
        commit = node.commit

        for ref in commit.refs:
            x = self._draw_ref_chip(ref, node.color, x, y_center) + PART_SPACING - 4

        x = self._draw_text(commit.short_sha, self._mono_font, theme.TEXT_MUTED, x, y_center)
        x += PART_SPACING
        x = self._draw_text(commit.message, self._ui_font, theme.TEXT, x, y_center)
        x += PART_SPACING
        meta = f"— {commit.author}, {commit.date:%Y-%m-%d %H:%M}"
        x = self._draw_text(meta, self._ui_font, theme.TEXT_MUTED, x, y_center)
        return x

    def _draw_text(self, text: str, font: QFont, color: str, x: float, y_center: float) -> float:
        item = QGraphicsSimpleTextItem(text)
        item.setFont(font)
        item.setBrush(QBrush(QColor(color)))
        item.setPos(x, y_center - QFontMetricsF(font).height() / 2)
        item.setZValue(5)
        self._scene.addItem(item)
        return x + QFontMetricsF(font).horizontalAdvance(text)

    def _draw_ref_chip(self, ref: str, color: str, x: float, y_center: float) -> float:
        metrics = QFontMetricsF(self._chip_font)
        width = metrics.horizontalAdvance(ref) + 2 * CHIP_PADDING
        height = metrics.height() + 4

        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y_center - height / 2, width, height), height / 2, height / 2)
        chip = QGraphicsPathItem(path)
        background = QColor(color)
        background.setAlpha(38)
        chip.setBrush(QBrush(background))
        chip.setPen(QPen(QColor(color), 1))
        chip.setZValue(4)
        self._scene.addItem(chip)

        label = QGraphicsSimpleTextItem(ref)
        label.setFont(self._chip_font)
        label.setBrush(QBrush(QColor(color)))
        label.setPos(x + CHIP_PADDING, y_center - metrics.height() / 2)
        label.setZValue(5)
        self._scene.addItem(label)
        return x + width
