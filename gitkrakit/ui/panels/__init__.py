"""Panneaux de la fenêtre principale : vues Qt sans logique Git."""

from gitkrakit.ui.panels.details_panel import DetailsPanel
from gitkrakit.ui.panels.sidebar_panel import SidebarPanel
from gitkrakit.ui.panels.staging_panel import StagingPanel
from gitkrakit.ui.panels.terminal_dock import TerminalDock

__all__ = [
    "DetailsPanel",
    "SidebarPanel",
    "StagingPanel",
    "TerminalDock",
]
