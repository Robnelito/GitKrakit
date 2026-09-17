"""
manager.py
Espaces de travail : des groupes nommés de dépôts (façon GitKraken
Workspaces), plus la liste des dépôts ouverts récemment. Le tout est
persisté en JSON dans ~/.gitkrakit/workspaces.json — aucune dépendance Qt
ici, la couche UI (WorkspacePanel) s'appuie sur cette classe.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

MAX_RECENT = 10

DEFAULT_CONFIG_PATH = Path.home() / ".gitkrakit" / "workspaces.json"


class WorkspaceError(Exception):
    """Erreur de gestion des espaces de travail, à afficher telle quelle dans l'UI."""


@dataclass
class Workspace:
    name: str
    repos: list[str] = field(default_factory=list)


class WorkspaceManager:
    """Charge, modifie et sauvegarde les espaces de travail.

    Chaque méthode de modification sauvegarde immédiatement sur disque,
    l'appelant n'a jamais à appeler save() lui-même.
    """

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.workspaces: list[Workspace] = []
        self.recent: list[str] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # fichier corrompu ou illisible : on repart de zéro sans écraser
            # le fichier tant qu'aucune modification n'est faite
            return
        self.workspaces = [
            Workspace(name=w.get("name", "?"), repos=list(w.get("repos", [])))
            for w in data.get("workspaces", [])
        ]
        self.recent = list(data.get("recent", []))[:MAX_RECENT]

    def _save(self) -> None:
        data = {
            "workspaces": [{"name": w.name, "repos": w.repos} for w in self.workspaces],
            "recent": self.recent,
        }
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            raise WorkspaceError(f"Impossible de sauvegarder les espaces de travail: {exc}") from exc

    # ------------------------------------------------------------------
    # Espaces de travail
    # ------------------------------------------------------------------
    def get(self, name: str) -> Workspace | None:
        return next((w for w in self.workspaces if w.name == name), None)

    def create_workspace(self, name: str) -> Workspace:
        name = name.strip()
        if not name:
            raise WorkspaceError("Le nom de l'espace de travail ne peut pas être vide.")
        if self.get(name) is not None:
            raise WorkspaceError(f"L'espace de travail '{name}' existe déjà.")
        workspace = Workspace(name=name)
        self.workspaces.append(workspace)
        self._save()
        return workspace

    def rename_workspace(self, old_name: str, new_name: str) -> None:
        workspace = self.get(old_name)
        if workspace is None:
            raise WorkspaceError(f"Espace de travail '{old_name}' introuvable.")
        new_name = new_name.strip()
        if not new_name:
            raise WorkspaceError("Le nom de l'espace de travail ne peut pas être vide.")
        if new_name != old_name and self.get(new_name) is not None:
            raise WorkspaceError(f"L'espace de travail '{new_name}' existe déjà.")
        workspace.name = new_name
        self._save()

    def delete_workspace(self, name: str) -> None:
        workspace = self.get(name)
        if workspace is None:
            raise WorkspaceError(f"Espace de travail '{name}' introuvable.")
        self.workspaces.remove(workspace)
        self._save()

    # ------------------------------------------------------------------
    # Dépôts d'un espace
    # ------------------------------------------------------------------
    def add_repo(self, workspace_name: str, repo_path: str) -> None:
        workspace = self.get(workspace_name)
        if workspace is None:
            raise WorkspaceError(f"Espace de travail '{workspace_name}' introuvable.")
        repo_path = str(Path(repo_path))
        if repo_path in workspace.repos:
            raise WorkspaceError(f"Ce dépôt est déjà dans '{workspace_name}'.")
        workspace.repos.append(repo_path)
        self._save()

    def remove_repo(self, workspace_name: str, repo_path: str) -> None:
        workspace = self.get(workspace_name)
        if workspace is None:
            raise WorkspaceError(f"Espace de travail '{workspace_name}' introuvable.")
        if repo_path in workspace.repos:
            workspace.repos.remove(repo_path)
            self._save()

    # ------------------------------------------------------------------
    # Dépôts récents
    # ------------------------------------------------------------------
    def touch_recent(self, repo_path: str) -> None:
        """Place le dépôt en tête des récents (dédoublonné, plafonné)."""
        repo_path = str(Path(repo_path))
        if repo_path in self.recent:
            self.recent.remove(repo_path)
        self.recent.insert(0, repo_path)
        del self.recent[MAX_RECENT:]
        self._save()

    def remove_recent(self, repo_path: str) -> None:
        """Retire le dépôt de la liste des récents."""
        repo_path = str(Path(repo_path))
        if repo_path in self.recent:
            self.recent.remove(repo_path)
            self._save()
