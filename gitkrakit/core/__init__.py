"""Couche métier : accès Git et mise en page du graphe (aucune dépendance Qt)."""

from gitkrakit.core.diff_parser import DiffRow, parse_unified_diff
from gitkrakit.core.git_backend import (
    CommitInfo,
    FileStatus,
    GitBackend,
    GitBackendError,
)
from gitkrakit.core.gitflow import GitFlow, GitFlowConfig, GitFlowStatus
from gitkrakit.core.graph_model import GraphLayout, GraphNode

__all__ = [
    "CommitInfo",
    "DiffRow",
    "FileStatus",
    "GitBackend",
    "GitBackendError",
    "GitFlow",
    "GitFlowConfig",
    "GitFlowStatus",
    "GraphLayout",
    "GraphNode",
    "parse_unified_diff",
]
