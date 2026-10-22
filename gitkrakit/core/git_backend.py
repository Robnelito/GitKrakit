"""
git_backend.py
Couche d'abstraction au-dessus de GitPython. Toute la logique Git de
GitKrakit passe par cette classe : la fenêtre principale et le rendu du
graphe n'appellent jamais GitPython directement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Optional

import git
from git import Repo, InvalidGitRepositoryError, NoSuchPathError
from git.remote import PushInfo


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


def _synchronized(method):
    """Serialize access to the GitPython ``Repo`` instance.

    GitPython does not guarantee that one repository object can safely be
    used from several threads.  The UI performs remote operations in a
    worker thread, so every public backend entry point shares this lock.
    ``RLock`` is intentional: a backend method may use another synchronized
    property such as ``working_dir``.
    """

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class GitBackend:
    """Wrapper GitPython. Une instance = un dépôt ouvert."""

    def __init__(self, repo_path: Optional[str] = None):
        self._lock = RLock()
        self.repo: Optional[Repo] = None
        if repo_path:
            self.open(repo_path)

    # ------------------------------------------------------------------
    # Ouverture / infos générales
    # ------------------------------------------------------------------
    @_synchronized
    def open(self, repo_path: str) -> None:
        try:
            new_repo = Repo(repo_path, search_parent_directories=True)
        except (InvalidGitRepositoryError, NoSuchPathError) as exc:
            raise GitBackendError(f"'{repo_path}' n'est pas un dépôt Git valide.") from exc
        previous_repo = self.repo
        self.repo = new_repo
        if previous_repo is not None:
            previous_repo.close()

    @_synchronized
    def close(self) -> None:
        """Release GitPython resources, notably Windows process handles."""
        if self.repo is not None:
            self.repo.close()
            self.repo = None

    @property
    @_synchronized
    def is_open(self) -> bool:
        return self.repo is not None

    @property
    @_synchronized
    def working_dir(self) -> str:
        self._require_repo()
        return self.repo.working_tree_dir or ""

    @property
    @_synchronized
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
    @_synchronized
    def local_branches(self) -> list[str]:
        self._require_repo()
        return [h.name for h in self.repo.heads]

    @_synchronized
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

    @_synchronized
    def tags(self) -> list[str]:
        self._require_repo()
        return [t.name for t in self.repo.tags]

    @_synchronized
    def branch_ahead_behind(self) -> dict[str, tuple[int, int]]:
        """Pour chaque branche locale ayant une branche amont (tracking),
        retourne {nom: (ahead, behind)} par rapport à cette branche amont.
        Ne déclenche aucun accès réseau : compare l'état local au dernier
        `fetch` connu (refs/remotes/...), d'où l'intérêt du fetch auto."""
        self._require_repo()
        result: dict[str, tuple[int, int]] = {}
        for head in self.repo.heads:
            tracking = head.tracking_branch()
            if tracking is None:
                continue
            try:
                ahead = int(self.repo.git.rev_list("--count", f"{tracking.name}..{head.name}"))
                behind = int(self.repo.git.rev_list("--count", f"{head.name}..{tracking.name}"))
            except git.GitCommandError:
                continue
            if ahead or behind:
                result[head.name] = (ahead, behind)
        return result

    @_synchronized
    def create_branch(self, name: str, start_point: Optional[str] = None) -> None:
        self._require_repo()
        try:
            self.repo.create_head(name, start_point or self.repo.head.commit)
        except Exception as exc:
            raise GitBackendError(f"Impossible de créer la branche '{name}': {exc}") from exc

    @_synchronized
    def checkout(self, branch_name: str) -> None:
        self._require_repo()
        try:
            self.repo.git.checkout(branch_name)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec du checkout '{branch_name}': {exc}") from exc

    @_synchronized
    def merge_branch(self, source: str) -> str:
        """Fusionne `source` dans la branche courante."""
        self._require_repo()
        target = self.repo.active_branch.name
        if source == target:
            raise GitBackendError("Impossible de fusionner une branche dans elle-même.")
        try:
            self.repo.git.merge("--no-ff", "-m", f"Merge branch '{source}' into {target}", source)
        except git.GitCommandError as exc:
            raise GitBackendError(
                f"Conflit ou échec du merge de '{source}' dans '{target}': {exc}\n"
                "Résous les conflits puis commit avant de recommencer."
            ) from exc
        return f"'{source}' fusionnée dans '{target}'"

    @_synchronized
    def revert_commit(self, sha: str) -> str:
        """Crée un commit annulant `sha` (un merge est annulé par rapport à son 1er parent)."""
        self._require_repo()
        try:
            commit = self.repo.commit(sha)
        except (ValueError, git.BadName) as exc:
            raise GitBackendError(f"Commit introuvable '{sha}': {exc}") from exc
        if not commit.parents:
            raise GitBackendError("Impossible de revert le commit initial du dépôt.")
        args = ["--no-edit"]
        if len(commit.parents) > 1:
            args += ["-m", "1"]
        try:
            self.repo.git.revert(*args, sha)
        except git.GitCommandError as exc:
            raise GitBackendError(
                f"Conflit ou échec du revert de '{sha[:7]}': {exc}\n"
                "Résous les conflits puis commit, ou annule avec « git revert --abort »."
            ) from exc
        return f"Commit '{sha[:7]}' revert"

    @_synchronized
    def delete_branch(self, branch_name: str, force: bool = False) -> None:
        self._require_repo()
        try:
            self.repo.delete_head(branch_name, force=force)
        except Exception as exc:
            raise GitBackendError(f"Impossible de supprimer la branche '{branch_name}': {exc}") from exc

    # ------------------------------------------------------------------
    # Historique (pour le graphe)
    # ------------------------------------------------------------------
    @_synchronized
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

    @_synchronized
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

    @_synchronized
    def stage(self, paths: list[str]) -> None:
        """Indexe les chemins donnés, y compris les fichiers supprimés
        (index.add() de GitPython échoue sur un fichier absent du disque,
        d'où le passage par `git add -A`)."""
        self._require_repo()
        try:
            self.repo.git.add("-A", "--", *paths)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec de l'indexation: {exc}") from exc

    @_synchronized
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

    @_synchronized
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

    @_synchronized
    def stash(self) -> str:
        self._require_repo()
        try:
            return self.repo.git.stash("push") or "Stash OK"
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec du stash: {exc}") from exc

    @_synchronized
    def stash_pop(self) -> str:
        self._require_repo()
        try:
            return self.repo.git.stash("pop")
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec du stash pop: {exc}") from exc

    @_synchronized
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

    @_synchronized
    def diff_for_commit_file(self, sha: str, path: str) -> str:
        """Diff d'un fichier tel que modifié par un commit donné."""
        self._require_repo()
        try:
            return self.repo.git.show("--format=", sha, "--", path)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Diff indisponible pour {path}: {exc}") from exc

    @_synchronized
    def commit(self, message: str) -> None:
        self._require_repo()
        if not message.strip():
            raise GitBackendError("Le message de commit ne peut pas être vide.")
        try:
            self.repo.index.commit(message)
        except Exception as exc:
            raise GitBackendError(f"Échec du commit: {exc}") from exc

    @_synchronized
    def staged_diff(self) -> str:
        """Return the complete staged patch used for commit-message generation."""
        self._require_repo()
        try:
            return self.repo.git.diff("--cached", "--no-ext-diff", "--unified=3")
        except git.GitCommandError as exc:
            raise GitBackendError(f"Impossible de lire le diff indexé: {exc}") from exc

    # ------------------------------------------------------------------
    # Remote : fetch / pull / push
    # ------------------------------------------------------------------
    @_synchronized
    def fetch(self, remote_name: str = "origin") -> str:
        self._require_repo()
        try:
            remote = self.repo.remote(remote_name)
            infos = remote.fetch()
            return f"Fetch OK ({len(infos)} ref(s) mise(s) à jour)"
        except Exception as exc:
            raise GitBackendError(f"Échec du fetch: {exc}") from exc

    @_synchronized
    def pull(self, remote_name: str = "origin") -> str:
        self._require_repo()
        try:
            remote = self.repo.remote(remote_name)
            infos = remote.pull()
            return f"Pull OK ({len(infos)} ref(s))"
        except Exception as exc:
            raise GitBackendError(f"Échec du pull: {exc}") from exc

    @_synchronized
    def push(self, remote_name: str = "origin") -> str:
        self._require_repo()
        try:
            remote = self.repo.remote(remote_name)
            infos = remote.push()
            error_flags = (
                PushInfo.ERROR
                | PushInfo.REJECTED
                | PushInfo.REMOTE_REJECTED
                | PushInfo.REMOTE_FAILURE
            )
            failures = [info.summary.strip() for info in infos if info.flags & error_flags]
            if failures:
                raise GitBackendError("Échec du push: " + "; ".join(failures))
            return f"Push OK ({len(infos)} ref(s))"
        except GitBackendError:
            raise
        except Exception as exc:
            raise GitBackendError(f"Échec du push: {exc}") from exc

    @_synchronized
    def run_raw(self, command_args: list[str]) -> str:
        """Exécute une commande git brute (pour le mini-terminal intégré)."""
        self._require_repo()
        try:
            return self.repo.git.execute(["git"] + command_args)
        except git.GitCommandError as exc:
            raise GitBackendError(str(exc)) from exc
