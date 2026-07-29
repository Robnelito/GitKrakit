"""
preferences_dialog.py
Boîte de préférences : active ou désactive les agents ACP (Codex, Claude)
avec un interrupteur. Les changements sont appliqués et persistés
immédiatement, puis signalés à la fenêtre principale.
"""
from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from gitkrakit import preferences, theme
from gitkrakit.core.acp_commit import ACP_PROVIDERS
from gitkrakit.ui.icons import app_icon


def _mix(start: QColor, end: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        round(start.red() + (end.red() - start.red()) * ratio),
        round(start.green() + (end.green() - start.green()) * ratio),
        round(start.blue() + (end.blue() - start.blue()) * ratio),
    )


class ToggleSwitch(QAbstractButton):
    """Interrupteur on/off peint avec la palette du thème."""

    TRACK_WIDTH = 46
    TRACK_HEIGHT = 24
    KNOB_MARGIN = 3

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._offset = 1.0 if checked else 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
        # Connecté après l'état initial pour éviter une animation au démarrage.
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(self.TRACK_WIDTH, self.TRACK_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = float(value)
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track_rect = QRectF(0.5, 0.5, self.TRACK_WIDTH - 1, self.TRACK_HEIGHT - 1)
        radius = track_rect.height() / 2
        # Piste éteinte en BORDER, pas en SURFACE : la ligne de préférence est
        # déjà en SURFACE et l'interrupteur s'y fondrait.
        track = _mix(QColor(theme.BORDER), QColor(theme.ACCENT), self._offset)
        border = _mix(QColor(theme.BORDER), QColor(theme.ACCENT), self._offset)
        knob = QColor(theme.HIGHLIGHT)
        if not self.isEnabled():
            track.setAlpha(110)
            border.setAlpha(110)
            knob.setAlpha(150)

        painter.setPen(QPen(border, 1))
        painter.setBrush(track)
        painter.drawRoundedRect(track_rect, radius, radius)

        diameter = self.TRACK_HEIGHT - 2 * self.KNOB_MARGIN
        travel = self.TRACK_WIDTH - 2 * self.KNOB_MARGIN - diameter
        knob_rect = QRectF(
            self.KNOB_MARGIN + self._offset * travel,
            self.KNOB_MARGIN,
            diameter,
            diameter,
        )
        # Contour repris de la piste : le pouce reste lisible en thème clair,
        # où le blanc seul se confondrait avec la piste éteinte.
        painter.setPen(QPen(border, 1))
        painter.setBrush(knob)
        painter.drawEllipse(knob_rect.adjusted(0.5, 0.5, -0.5, -0.5))

        if self.hasFocus():
            painter.setPen(QPen(QColor(theme.ACCENT), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(track_rect.adjusted(-1.5, -1.5, 1.5, 1.5), radius + 2, radius + 2)
        painter.end()


class PreferencesDialog(QDialog):
    """Préférences de GitKrakit — pour l'instant, les agents ACP."""

    acp_providers_changed = Signal(list)  # ids des agents activés

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Préférences")
        self.setWindowIcon(app_icon("settings", theme.ACCENT, 32))
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("AGENTS ACP")
        title.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(title)

        intro = QLabel(
            "Choisis les agents proposés dans le panneau Staging pour générer un "
            "message de commit. Un agent désactivé n'est jamais démarré."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        layout.addWidget(intro)

        enabled = set(preferences.enabled_acp_providers())
        self._switches: dict[str, ToggleSwitch] = {}
        for provider_id, label in preferences.acp_provider_choices():
            layout.addWidget(self._build_row(provider_id, label, provider_id in enabled))

        self._empty_warning = QLabel(
            "Aucun agent activé : le bouton « Générer via ACP » reste indisponible."
        )
        self._empty_warning.setWordWrap(True)
        self._empty_warning.setStyleSheet(
            f"color: {theme.STATUS_COLORS.get('conflict', theme.TEXT_MUTED)};"
        )
        self._empty_warning.setVisible(not enabled)
        layout.addWidget(self._empty_warning)

        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("Fermer")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _build_row(self, provider_id: str, label: str, checked: bool) -> QFrame:
        row = QFrame()
        row.setObjectName("preferenceRow")
        row.setStyleSheet(
            f"#preferenceRow {{ background-color: {theme.SURFACE};"
            f" border: 1px solid {theme.BORDER}; border-radius: 8px; }}"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 10, 12, 10)
        row_layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        name = QLabel(label)
        name.setStyleSheet(f"color: {theme.TEXT}; font-weight: 600; border: none;")
        package = QLabel(ACP_PROVIDERS[provider_id].package)
        package.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-family: {theme.MONO_FONT_FAMILY}; border: none;"
        )
        text_layout.addWidget(name)
        text_layout.addWidget(package)
        row_layout.addLayout(text_layout, stretch=1)

        switch = ToggleSwitch(checked)
        switch.setAccessibleName(f"Activer l'agent {label}")
        switch.setToolTip(f"Proposer {label} pour la génération de message de commit")
        switch.toggled.connect(self._on_switch_toggled)
        self._switches[provider_id] = switch
        row_layout.addWidget(switch, alignment=Qt.AlignVCenter)
        return row

    def _on_switch_toggled(self, _checked: bool) -> None:
        enabled = preferences.save_enabled_acp_providers(
            [provider_id for provider_id, switch in self._switches.items() if switch.isChecked()]
        )
        self._empty_warning.setVisible(not enabled)
        self.acp_providers_changed.emit(enabled)
