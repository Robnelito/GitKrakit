"""
graph_view.py
Rendu graphique du graphe de commits (QGraphicsView) : un cercle par
commit, des lignes reliant chaque commit à ses parents, colorées par lane,
plus le message/auteur/date affichés à droite du cercle. Cliquer sur un
commit émet un signal avec son sha pour que la fenêtre principale
affiche les détails (fichiers modifiés, diff).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QBrush, QPen, QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsTextItem,
)

from graph_model import GraphLayout, GraphNode

ROW_HEIGHT = 34
LANE_WIDTH = 22
NODE_RADIUS = 5
LEFT_MARGIN = 20
TEXT_OFFSET = 14


class CommitNodeItem(QGraphicsEllipseItem):
    def __init__(self, node: GraphNode, view: "GraphView"):
        r = NODE_RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.node = node
        self._view = view
        self.setBrush(QBrush(QColor(node.color)))
        self.setPen(QPen(QColor("#0d1117"), 1))
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self._view.commit_selected.emit(self.node.commit.sha)
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor("#ffffff"), 2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor("#0d1117"), 1))
        super().hoverLeaveEvent(event)


class GraphView(QGraphicsView):
    commit_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor("#0d1117")))
        self.layout: GraphLayout | None = None

    def set_commits(self, commits) -> None:
        self.layout = GraphLayout(commits)
        self._redraw()

    def _redraw(self) -> None:
        self._scene.clear()
        if not self.layout:
            return

        font = QFont("Monospace", 9)
        text_x = LEFT_MARGIN + (self.layout.lane_count + 1) * LANE_WIDTH

        # 1. lignes commit -> parents
        for node in self.layout.nodes:
            x0 = LEFT_MARGIN + node.lane * LANE_WIDTH
            y0 = node.row * ROW_HEIGHT + ROW_HEIGHT / 2
            for parent_lane, parent_row in node.parent_lanes:
                x1 = LEFT_MARGIN + parent_lane * LANE_WIDTH
                y1 = parent_row * ROW_HEIGHT + ROW_HEIGHT / 2
                line = QGraphicsLineItem(x0, y0, x1, y1)
                line.setPen(QPen(QColor(node.color), 2))
                line.setZValue(1)
                self._scene.addItem(line)

        # 2. noeuds + texte
        for node in self.layout.nodes:
            x = LEFT_MARGIN + node.lane * LANE_WIDTH
            y = node.row * ROW_HEIGHT + ROW_HEIGHT / 2
            item = CommitNodeItem(node, self)
            item.setPos(x, y)
            self._scene.addItem(item)

            refs_str = ""
            if node.commit.refs:
                refs_str = "  [" + ", ".join(node.commit.refs) + "]"
            label = (
                f"{node.commit.short_sha}  {node.commit.message}{refs_str}"
                f"   — {node.commit.author}, {node.commit.date:%Y-%m-%d %H:%M}"
            )
            text = QGraphicsTextItem(label)
            text.setDefaultTextColor(QColor("#c9d1d9"))
            text.setFont(font)
            text.setPos(text_x, node.row * ROW_HEIGHT)
            self._scene.addItem(text)

        total_width = text_x + 600
        total_height = len(self.layout.nodes) * ROW_HEIGHT + ROW_HEIGHT
        self._scene.setSceneRect(QRectF(0, 0, total_width, total_height))
