"""Non-blocking PyUpdater integration and its compact notification banner."""
from __future__ import annotations

import sys
import threading
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, QSize, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton

from gitkrakit import __version__, theme
from gitkrakit.client_config import ClientConfig
from gitkrakit.ui.icons import app_icon


def progress_percent(info: Mapping[str, Any]) -> int:
    """Normalize PyUpdater progress dictionaries to a clamped percentage."""
    raw = info.get("percent_complete")
    if raw is None:
        try:
            total = float(info.get("total") or 0)
            raw = (float(info.get("downloaded") or 0) / total) * 100 if total else 0
        except (TypeError, ValueError, ZeroDivisionError):
            raw = 0
    try:
        return max(0, min(100, int(float(raw))))
    except (TypeError, ValueError):
        return 0


class UpdaterController(QObject):
    """Run PyUpdater network and download work outside Qt's UI thread."""

    update_available = Signal(str)
    no_update = Signal(bool)  # manual check
    check_failed = Signal(bool)  # manual check
    unavailable = Signal(bool)  # manual check
    download_progress = Signal(int)
    download_failed = Signal(str)
    install_ready = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._checking = False
        self._downloading = False
        self._app_update: Any | None = None

    @staticmethod
    def is_installed_app() -> bool:
        return bool(getattr(sys, "frozen", False))

    def check(self, *, manual: bool = False) -> bool:
        if self._checking or self._downloading:
            return False
        if not self.is_installed_app():
            self.unavailable.emit(manual)
            return True

        self._checking = True
        threading.Thread(
            target=self._check_worker,
            args=(manual,),
            name="GitKrakit update check",
            daemon=True,
        ).start()
        return True

    def _check_worker(self, manual: bool) -> None:
        try:
            from pyupdater.client import Client

            client = Client(ClientConfig(), progress_hooks=[self._on_progress])
            client.refresh()
            app_update = client.update_check(ClientConfig.APP_NAME, __version__)
            self._app_update = app_update
            if app_update is None:
                self.no_update.emit(manual)
                return
            version = str(getattr(app_update, "version", "")).strip()
            self.update_available.emit(version)
        except ImportError:
            self.unavailable.emit(manual)
        except Exception:
            # A routine background network or manifest failure is intentionally quiet.
            self.check_failed.emit(manual)
        finally:
            self._checking = False

    @Slot()
    def download(self) -> None:
        if self._downloading or self._app_update is None:
            return
        self._downloading = True
        threading.Thread(
            target=self._download_worker,
            name="GitKrakit update download",
            daemon=True,
        ).start()

    def _download_worker(self) -> None:
        app_update = self._app_update
        try:
            app_update.download()
            if not app_update.is_downloaded():
                raise RuntimeError("Le téléchargement n'a pas pu être vérifié.")
            self.install_ready.emit()
        except Exception as exc:
            try:
                app_update.cleanup()
            except Exception:
                pass
            message = str(exc).strip() or "Le téléchargement a été interrompu."
            self.download_failed.emit(message)
        finally:
            self._downloading = False

    def _on_progress(self, info: Mapping[str, Any]) -> None:
        self.download_progress.emit(progress_percent(info))

    @Slot()
    def install_and_restart(self) -> None:
        if self._app_update is None or not self._app_update.is_downloaded():
            self.download_failed.emit("Le paquet téléchargé n'est plus disponible.")
            return
        try:
            self._app_update.extract_restart()
        except Exception as exc:
            message = str(exc).strip() or "L'installation de la mise à jour a échoué."
            self.download_failed.emit(message)


class UpdateBanner(QFrame):
    """Inline update prompt; avoids blocking the user with a modal dialog."""

    update_requested = Signal()
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("updateBanner")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 12, 8)
        layout.setSpacing(10)

        self.label = QLabel()
        self.label.setWordWrap(True)
        layout.addWidget(self.label, stretch=1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(150, 8)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.primary_button = QPushButton(app_icon("fetch"), "Mettre à jour")
        self.primary_button.setObjectName("primaryButton")
        self.primary_button.setIconSize(QSize(17, 17))
        self.primary_button.clicked.connect(self.update_requested)
        layout.addWidget(self.primary_button)

        self.later_button = QPushButton("Plus tard")
        self.later_button.clicked.connect(self._dismiss)
        layout.addWidget(self.later_button)

        self.apply_theme()
        self.hide()

    def apply_theme(self) -> None:
        self.setStyleSheet(
            f"QFrame#updateBanner {{ background: {theme.ACCENT_SOFT}; "
            f"border-bottom: 1px solid {theme.ACCENT}; }}"
        )
        self.label.setStyleSheet(f"color: {theme.TEXT}; background: transparent;")
        self.primary_button.setIcon(app_icon("fetch"))

    def show_available(self, version: str) -> None:
        suffix = f" {version}" if version else ""
        self.label.setText(f"Une mise à jour{suffix} est disponible.")
        self.primary_button.setText("Mettre à jour")
        self.primary_button.setEnabled(True)
        self.later_button.setEnabled(True)
        self.progress.hide()
        self.show()

    def show_downloading(self) -> None:
        self.label.setText("Téléchargement et vérification de la mise à jour…")
        self.primary_button.setText("Téléchargement…")
        self.primary_button.setEnabled(False)
        self.later_button.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()

    def set_progress(self, percent: int) -> None:
        self.progress.setValue(percent)

    def show_retry(self) -> None:
        self.label.setText("Le téléchargement a été interrompu. Vous pouvez réessayer.")
        self.primary_button.setText("Réessayer")
        self.primary_button.setEnabled(True)
        self.later_button.setEnabled(True)
        self.progress.hide()
        self.show()

    def show_installing(self) -> None:
        self.label.setText("Mise à jour vérifiée. Redémarrage de GitKrakit…")
        self.primary_button.setText("Installation…")
        self.primary_button.setEnabled(False)
        self.later_button.setEnabled(False)
        self.progress.setValue(100)
        self.progress.show()

    @Slot()
    def _dismiss(self) -> None:
        self.hide()
        self.dismissed.emit()
