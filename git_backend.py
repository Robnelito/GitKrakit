"""
git_backend.py
Couche d'abstraction au-dessus de GitPython. Toute la logique Git de
GitKrakit passe par cette classe : la fenêtre principale et le rendu du
graphe n'appellent jamais GitPython directement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import git
from git import Repo, InvalidGitRepositoryError, NoSuchPathError


@dataclass
class CommitInfo:
    sha: str
    short_sha: str
    message: str
    author: str
    author_email: str
    date: datetime
    parents: list[str]
    refs: list[str] = field(default_factory=list)  # noms de branches/tags pointant ici


@dataclass
class FileStatus:
    path: str
    status: str  # "modified", "added", "deleted", "untracked", "renamed"


class GitBackendError(Exception):
    """Erreur remontée par le backend, à afficher telle quelle dans l'UI."""


class GitBackend:
    """Wrapper GitPython. Une instance = un dépôt ouvert."""

    def __init__(self, repo_path: Optional[str] = None):
        self.repo: Optional[Repo] = None
        if repo_path:
            self.open(repo_path)

    # ------------------------------------------------------------------
    # Ouverture / infos générales
    # ------------------------------------------------------------------
    def open(self, repo_path: str) -> None:
        try:
            self.repo = Repo(repo_path, search_parent_directories=True)
        except (InvalidGitRepositoryError, NoSuchPathError) as exc:
            raise GitBackendError(f"'{repo_path}' n'est pas un dépôt Git valide.") from exc

    @property
    def is_open(self) -> bool:
        return self.repo is not None

    @property
    def working_dir(self) -> str:
        self._require_repo()
        return self.repo.working_tree_dir or ""

    @property
    def current_branch(self) -> str:
        self._require_repo()
        try:
            return self.repo.active_branch.name
        except TypeError:
            return f"(detached @ {self.repo.head.commit.hexsha[:7]})"

    def _require_repo(self):
        if self.repo is None:
            raise GitBackendError("Aucun dépôt ouvert.")

    # ------------------------------------------------------------------
    # Branches / tags
    # ------------------------------------------------------------------
    def local_branches(self) -> list[str]:
        self._require_repo()
        return [h.name for h in self.repo.heads]

    def remote_branches(self) -> list[str]:
        self._require_repo()
        names = []
        for remote in self.repo.remotes:
            try:
                for ref in remote.refs:
                    names.append(ref.name)
            except Exception:
                continue
        return names

    def tags(self) -> list[str]:
        self._require_repo()
        return [t.name for t in self.repo.tags]

    def create_branch(self, name: str, start_point: Optional[str] = None) -> None:
        self._require_repo()
        try:
            self.repo.create_head(name, start_point or self.repo.head.commit)
        except Exception as exc:
            raise GitBackendError(f"Impossible de créer la branche '{name}': {exc}") from exc

    def checkout(self, branch_name: str) -> None:
        self._require_repo()
        try:
            self.repo.git.checkout(branch_name)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec du checkout '{branch_name}': {exc}") from exc

    def delete_branch(self, branch_name: str, force: bool = False) -> None:
        self._require_repo()
        try:
            self.repo.delete_head(branch_name, force=force)
        except Exception as exc:
            raise GitBackendError(f"Impossible de supprimer la branche '{branch_name}': {exc}") from exc

    # ------------------------------------------------------------------
    # Historique (pour le graphe)
    # ------------------------------------------------------------------
    def commit_log(self, max_count: int = 300) -> list[CommitInfo]:
        """Retourne les commits en ordre topologique (parent après enfant),
        avec les refs (branches/tags) qui pointent dessus."""
        self._require_repo()

        # index sha -> liste de noms de refs pointant dessus
        ref_map: dict[str, list[str]] = {}
        for h in self.repo.heads:
            ref_map.setdefault(h.commit.hexsha, []).append(h.name)
        for t in self.repo.tags:
            ref_map.setdefault(t.commit.hexsha, []).append(f"tag:{t.name}")
        for remote in self.repo.remotes:
            try:
                for ref in remote.refs:
                    ref_map.setdefault(ref.commit.hexsha, []).append(ref.name)
            except Exception:
                continue

        commits: list[CommitInfo] = []
        try:
            iter_commits = self.repo.iter_commits(
                "--all", max_count=max_count, topo_order=True
            )
        except git.GitCommandError:
            # dépôt sans commit
            return commits

        for c in iter_commits:
            commits.append(
                CommitInfo(
                    sha=c.hexsha,
                    short_sha=c.hexsha[:7],
                    message=c.message.strip().split("\n")[0],
                    author=c.author.name,
                    author_email=c.author.email,
                    date=datetime.fromtimestamp(c.committed_date),
                    parents=[p.hexsha for p in c.parents],
                    refs=ref_map.get(c.hexsha, []),
                )
            )
        return commits

    # ------------------------------------------------------------------
    # Staging / status
    # ------------------------------------------------------------------
    def status(self) -> tuple[list[FileStatus], list[FileStatus]]:
        """Retourne (staged, unstaged)."""
        self._require_repo()
        staged: list[FileStatus] = []
        unstaged: list[FileStatus] = []

        diff_staged = self.repo.index.diff("HEAD") if self.repo.head.is_valid() else []
        for d in diff_staged:
            staged.append(FileStatus(path=d.a_path or d.b_path, status=self._diff_status(d)))

        diff_unstaged = self.repo.index.diff(None)
        for d in diff_unstaged:
            unstaged.append(FileStatus(path=d.a_path or d.b_path, status=self._diff_status(d)))

        for path in self.repo.untracked_files:
            unstaged.append(FileStatus(path=path, status="untracked"))

        return staged, unstaged

    @staticmethod
    def _diff_status(d) -> str:
        mapping = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed"}
        return mapping.get(d.change_type, d.change_type)

    def stage(self, paths: list[str]) -> None:
        self._require_repo()
        self.repo.index.add(paths)

    def unstage(self, paths: list[str]) -> None:
        self._require_repo()
        self.repo.index.reset(paths=paths)

    def diff_for_file(self, path: str, staged: bool = False) -> str:
        self._require_repo()
        try:
            if staged:
                return self.repo.git.diff("--cached", "--", path)
            return self.repo.git.diff("--", path)
        except git.GitCommandError as exc:
            return f"(diff indisponible: {exc})"

    def commit(self, message: str) -> None:
        self._require_repo()
        if not message.strip():
            raise GitBackendError("Le message de commit ne peut pas être vide.")
        try:
            self.repo.index.commit(message)
        except Exception as exc:
            raise GitBackendError(f"Échec du commit: {exc}") from exc

    # ------------------------------------------------------------------
    # Remote : fetch / pull / push
    # ------------------------------------------------------------------
    def fetch(self, remote_name: str = "origin") -> str:
        self._require_repo()
        try:
            remote = self.repo.remote(remote_name)
            infos = remote.fetch()
            return f"Fetch OK ({len(infos)} ref(s) mise(s) à jour)"
        except Exception as exc:
            raise GitBackendError(f"Échec du fetch: {exc}") from exc

    def pull(self, remote_name: str = "origin") -> str:
        self._require_repo()
        try:
            remote = self.repo.remote(remote_name)
            infos = remote.pull()
            return f"Pull OK ({len(infos)} ref(s))"
        except Exception as exc:
            raise GitBackendError(f"Échec du pull: {exc}") from exc

    def push(self, remote_name: str = "origin") -> str:
        self._require_repo()
        try:
            remote = self.repo.remote(remote_name)
            infos = remote.push()
            return f"Push OK ({len(infos)} ref(s))"
        except Exception as exc:
            raise GitBackendError(f"Échec du push: {exc}") from exc

    def run_raw(self, command_args: list[str]) -> str:
        """Exécute une commande git brute (pour le mini-terminal intégré)."""
        self._require_repo()
        try:
            return self.repo.git.execute(["git"] + command_args)
        except git.GitCommandError as exc:
            raise GitBackendError(str(exc)) from exc
