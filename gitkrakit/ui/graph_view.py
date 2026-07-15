"""
graph_view.py
Rendu du graphe de commits façon GitKraken : chaque commit occupe une
ligne pleine largeur découpée en colonnes — pastilles branche/tag,
lanes du graphe, message (élidé), date. Toute la ligne est cliquable et
surlignée au survol ; la ligne sélectionnée reste en surbrillance.

Les colonnes Branche/Tag, Graphe et Message sont redimensionnables : on
fait glisser les séparateurs de l'en-tête (comme les colonnes d'un
tableau). GraphView lit ces largeurs sur GraphPanel pour dessiner les
lignes exactement sous les bonnes colonnes.

GraphPanel = en-tête de colonnes redimensionnable + GraphView (QGraphicsView).
"""
from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
    Signal,
)
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
    QFrame,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gitkrakit.core import GraphLayout, GraphNode
from gitkrakit import theme

ROW_HEIGHT = 30
LANE_WIDTH = 18
GRAPH_LEFT_PADDING = 14
GRAPH_RIGHT_PADDING = 10
NODE_RADIUS = 4.5
MERGE_NODE_RADIUS = 5

# largeurs de colonnes par défaut (l'utilisateur peut les redimensionner
# via les poignées de l'en-tête ; voir GraphPanel)
DEFAULT_REF_COL_WIDTH = 160
DEFAULT_GRAPH_COL_WIDTH = 120
DEFAULT_MSG_COL_WIDTH = 480
DATE_COL_WIDTH = 150  # colonne finale, non redimensionnable (queue de ligne)

MIN_REF_COL_WIDTH = 70
MIN_GRAPH_COL_WIDTH = 50
MIN_MSG_COL_WIDTH = 150

HANDLE_WIDTH = 1  # largeur des poignées de redimensionnement de l'en-tête
SCROLLBAR_RESERVE = 10
CHIP_PADDING = 6
MAX_VISIBLE_REFS = 2  # au-delà : pastille "+N"


class CommitRowItem(QGraphicsRectItem):
    """Fond pleine largeur d'une ligne : teinte lane, survol, sélection."""

    def __init__(self, node: GraphNode, view: "GraphView", width: float):
        super().__init__(0, node.row * ROW_HEIGHT, width, ROW_HEIGHT)
        self.node = node
        self._view = view
        self._hovered = False

        # Neutral zebra striping keeps long histories readable without
        # competing with lane colors.
        base = QColor(theme.PANEL_BG)
        base.setAlpha(34 if node.row % 2 else 0)
        self._base_brush = QBrush(base)

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
        if len(node.commit.parents) > 1:
            self.setBrush(QBrush(QColor(theme.BACKGROUND)))
            self._normal_pen = QPen(QColor(node.color), 2.2)
        else:
            self.setBrush(QBrush(QColor(node.color)))
            self._normal_pen = QPen(QColor(theme.BACKGROUND), 1.5)
        self._normal_pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(self._normal_pen)
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{node.commit.short_sha} — {node.commit.message}")

    def mousePressEvent(self, event):
        self._view.select_commit(self.node.commit.sha)
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor(theme.HIGHLIGHT), 2.2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(self._normal_pen)
        super().hoverLeaveEvent(event)


class GraphView(QGraphicsView):
    commit_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        # sans ça, Qt centre la scène quand elle est plus petite que la vue
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(theme.BACKGROUND)))

        self._graph_layout: GraphLayout | None = None
        self._rows: dict[str, CommitRowItem] = {}
        self._content_width = 0.0
        self.selected_sha: str | None = None

        self._scroll_target = 0
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(140)
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)

        # largeurs de colonnes ; modifiables via set_column_widths()
        self.col_ref = DEFAULT_REF_COL_WIDTH
        self.col_graph = DEFAULT_GRAPH_COL_WIDTH
        self.col_msg = DEFAULT_MSG_COL_WIDTH
        self.graph_auto_size = True  # False dès que l'utilisateur redimensionne

        self._ui_font = QFont("Segoe UI", 9)
        self._chip_font = QFont("Segoe UI", 8)

    def set_column_widths(
        self,
        ref: float | None = None,
        graph: float | None = None,
        msg: float | None = None,
        graph_manual: bool = True,
    ) -> None:
        """Applique de nouvelles largeurs de colonnes (glissées depuis
        l'en-tête) et redessine. `graph` marque la colonne graphe comme
        fixée par l'utilisateur (elle n'est plus recalculée automatiquement
        selon le nombre de lanes)."""
        if ref is not None:
            self.col_ref = ref
        if graph is not None:
            self.col_graph = graph
            if graph_manual:
                self.graph_auto_size = False
        if msg is not None:
            self.col_msg = msg
        self._redraw()

    def set_commits(self, commits) -> None:
        # préserver la position de défilement (rafraîchissement auto)
        v_scroll = self.verticalScrollBar().value()
        h_scroll = self.horizontalScrollBar().value()
        self._graph_layout = GraphLayout(commits)
        if self.graph_auto_size:
            self.col_graph = max(
                MIN_GRAPH_COL_WIDTH,
                GRAPH_LEFT_PADDING
                + self._graph_layout.lane_count * LANE_WIDTH
                + GRAPH_RIGHT_PADDING,
            )
        self._redraw()
        self.verticalScrollBar().setValue(v_scroll)
        self.horizontalScrollBar().setValue(h_scroll)
        self._scroll_target = v_scroll

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
        # décalages de HANDLE_WIDTH pour rester aligné pixel pour pixel
        # avec les poignées de redimensionnement de l'en-tête (GraphPanel)
        graph_x = self.col_ref + HANDLE_WIDTH
        msg_x = graph_x + self.col_graph + HANDLE_WIDTH
        date_x = msg_x + self.col_msg
        total_width = date_x + DATE_COL_WIDTH

        # 0. fonds de ligne (cliquables, survol/sélection)
        for node in layout.nodes:
            row = CommitRowItem(node, self, total_width)
            self._scene.addItem(row)
            self._rows[node.commit.sha] = row

        # 1. Courbes commit -> parents. Lane changes happen within roughly
        # one row, then continue vertically, which avoids long diagonals.
        for node in layout.nodes:
            x0 = graph_x + GRAPH_LEFT_PADDING + node.lane * LANE_WIDTH
            y0 = node.row * ROW_HEIGHT + ROW_HEIGHT / 2
            line_color = QColor(node.color)
            line_color.setAlpha(225)
            pen = QPen(line_color, 2.2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            for parent_lane, parent_row in node.parent_lanes:
                x1 = graph_x + GRAPH_LEFT_PADDING + parent_lane * LANE_WIDTH
                y1 = parent_row * ROW_HEIGHT + ROW_HEIGHT / 2
                edge = QGraphicsPathItem(self._connection_path(x0, y0, x1, y1))
                edge.setPen(pen)
                edge.setZValue(1)
                self._scene.addItem(edge)

        # 2. noeuds + colonnes texte
        metrics = QFontMetricsF(self._ui_font)
        for node in layout.nodes:
            y_center = node.row * ROW_HEIGHT + ROW_HEIGHT / 2

            item = CommitNodeItem(node, self)
            item.setPos(graph_x + GRAPH_LEFT_PADDING + node.lane * LANE_WIDTH, y_center)
            self._scene.addItem(item)

            self._draw_refs(node, y_center)

            is_merge = len(node.commit.parents) > 1
            message = metrics.elidedText(node.commit.message, Qt.ElideRight, self.col_msg - 18)
            self._draw_text(
                message,
                self._ui_font,
                theme.TEXT_MUTED if is_merge else theme.TEXT,
                msg_x + 10,
                y_center,
            )

            date_text = f"{node.commit.date:%d/%m/%Y @ %H:%M}"
            self._draw_text(date_text, self._ui_font, theme.TEXT_MUTED, date_x + 8, y_center)

        total_height = len(layout.nodes) * ROW_HEIGHT + ROW_HEIGHT / 2
        self._content_width = total_width
        self._scene.setSceneRect(QRectF(0, 0, total_width, total_height))
        self._stretch_rows()

    @staticmethod
    def _connection_path(x0: float, y0: float, x1: float, y1: float) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(x0, y0)
        if abs(x1 - x0) < 0.1:
            path.lineTo(x1, y1)
            return path

        direction = 1.0 if y1 >= y0 else -1.0
        bend = min(abs(y1 - y0), ROW_HEIGHT * 1.15)
        bend_end = y0 + direction * bend
        path.cubicTo(
            x0,
            y0 + direction * bend * 0.52,
            x1,
            bend_end - direction * bend * 0.52,
            x1,
            bend_end,
        )
        if abs(y1 - bend_end) > 0.1:
            path.lineTo(x1, y1)
        return path

    def wheelEvent(self, event) -> None:
        """Animate discrete mouse wheels while preserving touchpad pixels."""
        pixel_delta = event.pixelDelta().y()
        if pixel_delta:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - pixel_delta)
            self._scroll_target = bar.value()
            event.accept()
            return

        angle_delta = event.angleDelta().y()
        if not angle_delta:
            super().wheelEvent(event)
            return

        bar = self.verticalScrollBar()
        if self._scroll_animation.state() == QAbstractAnimation.Stopped:
            self._scroll_target = bar.value()
        distance = (angle_delta / 120.0) * ROW_HEIGHT * 3
        self._scroll_target = int(
            max(bar.minimum(), min(bar.maximum(), self._scroll_target - distance))
        )
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(self._scroll_target)
        self._scroll_animation.start()
        event.accept()

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
        x = 8.0
        right_edge = self.col_ref - 8
        drawn = 0
        for ref in refs[:MAX_VISIBLE_REFS]:
            remaining = len(refs) - drawn - 1
            reserve = 34 if remaining else 0
            available = right_edge - x - reserve - (4 if reserve else 0)
            if available < 36:
                break
            x = self._draw_chip(ref, node.color, x, y_center, max_width=available) + 4
            drawn += 1

        overflow = len(refs) - drawn
        if overflow > 0 and right_edge - x >= 28:
            self._draw_chip(
                f"+{overflow}", node.color, x, y_center, max_width=right_edge - x
            )

    def _draw_chip(
        self, text: str, color: str, x: float, y_center: float, max_width: float
    ) -> float:
        metrics = QFontMetricsF(self._chip_font)
        label_text = metrics.elidedText(text, Qt.ElideRight, max_width - 2 * CHIP_PADDING)
        width = metrics.horizontalAdvance(label_text) + 2 * CHIP_PADDING
        height = metrics.height() + 4

        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y_center - height / 2, width, height), 5, 5)
        chip = QGraphicsPathItem(path)
        background = QColor(color)
        background.setAlpha(46)
        chip.setBrush(QBrush(background))
        outline = QColor(color)
        outline.setAlpha(190)
        chip.setPen(QPen(outline, 1))
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


def _col_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"color: {theme.TEXT_MUTED}; font-size: 8pt; font-weight: bold;"
        "background: transparent; border: none; padding-left: 6px;"
    )
    return label


class GraphPanel(QWidget):
    """En-tête de colonnes redimensionnable + vue du graphe.

    Les 3 premières colonnes (Branche/Tag, Graphe, Message) vivent dans un
    QSplitter : faire glisser une poignée redimensionne la colonne et
    répercute la nouvelle largeur sur GraphView pour que le dessin reste
    aligné. La colonne Date suit en simple label (queue de ligne, non
    redimensionnable).
    """

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
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 4, 0, 4)
        header_layout.setSpacing(0)

        self.header_splitter = QSplitter(Qt.Horizontal)
        self.header_splitter.setHandleWidth(HANDLE_WIDTH)
        self.header_splitter.setChildrenCollapsible(False)
        self.header_splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {theme.BORDER}; }}"
            f"QSplitter::handle:hover {{ background-color: {theme.ACCENT}; }}"
        )

        self._ref_header = _col_label("Branche / Tag")
        self._ref_header.setMinimumWidth(MIN_REF_COL_WIDTH)
        self.header_splitter.addWidget(self._ref_header)

        self._graph_header = _col_label("Graphe")
        self._graph_header.setMinimumWidth(MIN_GRAPH_COL_WIDTH)
        self.header_splitter.addWidget(self._graph_header)

        self._msg_header = _col_label("Message de commit")
        self._msg_header.setMinimumWidth(MIN_MSG_COL_WIDTH)
        self.header_splitter.addWidget(self._msg_header)

        self.header_splitter.setStretchFactor(0, 0)
        self.header_splitter.setStretchFactor(1, 0)
        self.header_splitter.setStretchFactor(2, 1)

        self.header_splitter.setSizes(
            [DEFAULT_REF_COL_WIDTH, DEFAULT_GRAPH_COL_WIDTH, DEFAULT_MSG_COL_WIDTH]
        )
        self.header_splitter.splitterMoved.connect(self._on_splitter_moved)
        header_layout.addWidget(self.header_splitter, stretch=1)

        date_header = _col_label("Date / Heure")
        date_header.setFixedWidth(DATE_COL_WIDTH)
        header_layout.addWidget(date_header)

        scrollbar_gutter = QWidget()
        scrollbar_gutter.setFixedWidth(SCROLLBAR_RESERVE)
        header_layout.addWidget(scrollbar_gutter)

        layout.addWidget(header)

        self.view = GraphView()
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.view.commit_selected.connect(self.commit_selected)
        self.empty_label = QLabel(
            "Ce dépôt ne contient encore aucun commit.\nCrée un premier commit depuis le panneau Staging."
        )
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; padding: 32px;")

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.empty_label)
        self.content_stack.addWidget(self.view)
        self.content_stack.setCurrentWidget(self.empty_label)
        layout.addWidget(self.content_stack)

        self._column_sync_timer = QTimer(self)
        self._column_sync_timer.setSingleShot(True)
        self._column_sync_timer.setInterval(0)
        self._column_sync_timer.timeout.connect(self._sync_view_columns)

    def set_commits(self, commits) -> None:
        self.view.set_commits(commits)
        self.content_stack.setCurrentWidget(self.view if commits else self.empty_label)
        # si la colonne graphe n'a pas été redimensionnée à la main,
        # répercute sa largeur auto-calculée (nb de lanes) sur l'en-tête
        if self.view.graph_auto_size:
            sizes = self.header_splitter.sizes()
            sizes[1] = int(self.view.col_graph)
            self.header_splitter.setSizes(sizes)
        self._sync_view_columns()

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        ref, graph, msg = self.header_splitter.sizes()
        self.view.set_column_widths(ref=ref, graph=graph, msg=msg, graph_manual=True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_column_sync_timer"):
            self._column_sync_timer.start()

    def _sync_view_columns(self) -> None:
        sizes = self.header_splitter.sizes()
        if len(sizes) != 3 or not all(sizes):
            return
        ref, graph, msg = sizes
        self.view.set_column_widths(
            ref=ref,
            graph=graph,
            msg=msg,
            graph_manual=False,
        )
