"""Panneaux de la fenêtre principale : vues Qt sans logique Git."""

from gitkrakit.ui.panels.branches_panel import BranchesPanel
from gitkrakit.ui.panels.details_panel import DetailsPanel
from gitkrakit.ui.panels.staging_panel import StagingPanel
from gitkrakit.ui.panels.terminal_dock import TerminalDock
from gitkrakit.ui.panels.workspace_panel import WorkspacePanel

__all__ = [
    "BranchesPanel",
    "DetailsPanel",
    "StagingPanel",
    "TerminalDock",
    "WorkspacePanel",
]
