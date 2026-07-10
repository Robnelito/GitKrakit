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
    _STATUS_LABELS = {
        "M": "modified",
        "A": "added",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "U": "conflict",
        "T": "typechange",
    }

    def status(self) -> tuple[list[FileStatus], list[FileStatus]]:
        """Retourne (staged, unstaged), via `git status --porcelain`.

        Le format porcelain donne deux colonnes par ligne : X = état dans
        l'index, Y = état dans le répertoire de travail. C'est la seule
        source fiable qui couvre aussi les suppressions et les renommages.
        """
        self._require_repo()
        staged: list[FileStatus] = []
        unstaged: list[FileStatus] = []

        try:
            output = self.repo.git.status("--porcelain")
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec du status: {exc}") from exc

        for line in output.splitlines():
            if len(line) < 4:
                continue
            x, y, rest = line[0], line[1], line[3:]
            # renommage : "R  ancien -> nouveau" — on garde le nouveau chemin
            path = rest.split(" -> ", 1)[-1].strip().strip('"')
            if x == "?" or y == "?":
                unstaged.append(FileStatus(path=path, status="untracked"))
                continue
            if x != " ":
                staged.append(FileStatus(path=path, status=self._STATUS_LABELS.get(x, x)))
            if y != " ":
                unstaged.append(FileStatus(path=path, status=self._STATUS_LABELS.get(y, y)))

        return staged, unstaged

    def stage(self, paths: list[str]) -> None:
        """Indexe les chemins donnés, y compris les fichiers supprimés
        (index.add() de GitPython échoue sur un fichier absent du disque,
        d'où le passage par `git add -A`)."""
        self._require_repo()
        try:
            self.repo.git.add("-A", "--", *paths)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec de l'indexation: {exc}") from exc

    def unstage(self, paths: list[str]) -> None:
        self._require_repo()
        try:
            if self.repo.head.is_valid():
                self.repo.git.reset("HEAD", "--", *paths)
            else:
                # dépôt sans commit : pas de HEAD, on retire du cache
                self.repo.git.rm("--cached", "--", *paths)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec de la désindexation: {exc}") from exc

    def commit_files(self, sha: str) -> list[FileStatus]:
        """Fichiers modifiés par un commit (pour le panneau de détails)."""
        self._require_repo()
        try:
            output = self.repo.git.show("--name-status", "--format=", sha)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Impossible de lire le commit {sha[:7]}: {exc}") from exc

        files: list[FileStatus] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            code = parts[0][:1]  # "R100" -> "R"
            path = parts[-1]
            files.append(FileStatus(path=path, status=self._STATUS_LABELS.get(code, code)))
        return files

    def stash(self) -> str:
        self._require_repo()
        try:
            return self.repo.git.stash("push") or "Stash OK"
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec du stash: {exc}") from exc

    def stash_pop(self) -> str:
        self._require_repo()
        try:
            return self.repo.git.stash("pop")
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec du stash pop: {exc}") from exc

    def diff_for_file(self, path: str, staged: bool = False) -> str:
        self._require_repo()
        try:
            if staged:
                diff = self.repo.git.diff("--cached", "--", path)
            else:
                diff = self.repo.git.diff("--", path)
        except git.GitCommandError as exc:
            return f"(diff indisponible: {exc})"

        if diff:
            return diff

        # fichier non suivi : git diff ne montre rien, on synthétise un
        # pseudo-diff avec tout le contenu en ajout
        full_path = Path(self.working_dir) / path
        if not staged and path in self.repo.untracked_files and full_path.is_file():
            try:
                lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                return ""
            return f"--- /dev/null\n+++ b/{path}\n" + "\n".join(f"+{l}" for l in lines)
        return diff

    def diff_for_commit_file(self, sha: str, path: str) -> str:
        """Diff d'un fichier tel que modifié par un commit donné."""
        self._require_repo()
        try:
            return self.repo.git.show("--format=", sha, "--", path)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Diff indisponible pour {path}: {exc}") from exc

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
