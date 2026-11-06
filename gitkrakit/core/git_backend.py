"""
git_backend.py
Couche d'abstraction au-dessus de GitPython. Toute la logique Git de
GitKrakit passe par cette classe : la fenêtre principale et le rendu du
graphe n'appellent jamais GitPython directement.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
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


@dataclass
class RefsSnapshot:
    """Branches, tags et état de synchronisation lus en une seule commande."""
    local: list[str] = field(default_factory=list)
    remote: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    ahead_behind: dict[str, tuple[int, int]] = field(default_factory=dict)
    ref_map: dict[str, list[str]] = field(default_factory=dict)  # sha -> refs

    def signature(self) -> tuple:
        """Empreinte comparable : change dès qu'une ref bouge ou apparaît."""
        return (
            tuple(self.local),
            tuple(self.remote),
            tuple(self.tags),
            tuple(sorted(self.ahead_behind.items())),
            tuple(sorted((sha, tuple(refs)) for sha, refs in self.ref_map.items())),
        )


class GitBackendError(Exception):
    """Erreur remontée par le backend, à afficher telle quelle dans l'UI."""


_AHEAD_RE = re.compile(r"ahead (\d+)")
_BEHIND_RE = re.compile(r"behind (\d+)")
BACKGROUND_FETCH_TIMEOUT = 300  # secondes


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
        self._background_process: Optional[subprocess.Popen] = None
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
    def is_open(self) -> bool:
        # Lecture d'une simple référence : volontairement sans verrou, pour que
        # le thread UI ne se bloque jamais derrière un pull/push en cours.
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
    def refs_snapshot(self) -> RefsSnapshot:
        """Lit branches, tags, refs par commit et ahead/behind en UN seul
        processus `git for-each-ref` (au lieu de deux `rev-list` par branche).

        Ne déclenche aucun accès réseau : compare l'état local au dernier
        `fetch` connu (refs/remotes/...), d'où l'intérêt du fetch auto."""
        self._require_repo()
        fmt = "%(refname)%00%(objectname)%00%(*objectname)%00%(upstream:track)"
        try:
            output = self.repo.git.for_each_ref(
                f"--format={fmt}", "refs/heads", "refs/remotes", "refs/tags"
            )
        except git.GitCommandError as exc:
            raise GitBackendError(f"Impossible de lire les références: {exc}") from exc

        snap = RefsSnapshot()
        heads: dict[str, list[str]] = {}
        tags: dict[str, list[str]] = {}
        remotes: dict[str, list[str]] = {}
        for line in output.splitlines():
            fields = line.split("\x00")
            if len(fields) < 4:
                continue
            refname, sha, peeled, track = fields[:4]
            target = peeled or sha  # tag annoté : le commit pointé, pas le tag
            if refname.startswith("refs/heads/"):
                name = refname[len("refs/heads/"):]
                snap.local.append(name)
                heads.setdefault(sha, []).append(name)
                if track:
                    counts = self._parse_track(track)
                    if counts is None:  # format inattendu : repli sûr, branche par branche
                        counts = self._ahead_behind_slow(name)
                    if counts and any(counts):
                        snap.ahead_behind[name] = counts
            elif refname.startswith("refs/remotes/"):
                name = refname[len("refs/remotes/"):]
                snap.remote.append(name)
                remotes.setdefault(sha, []).append(name)
            elif refname.startswith("refs/tags/"):
                name = refname[len("refs/tags/"):]
                snap.tags.append(name)
                tags.setdefault(target, []).append(f"tag:{name}")

        for group in (heads, tags, remotes):  # ordre d'affichage historique
            for sha, names in group.items():
                snap.ref_map.setdefault(sha, []).extend(names)
        return snap

    @staticmethod
    def _parse_track(track: str) -> Optional[tuple[int, int]]:
        """`[ahead 2, behind 1]` -> (2, 1). None si le format n'est pas reconnu ;
        (0, 0) pour un amont disparu (`[gone]`)."""
        if "gone" in track:
            return (0, 0)
        ahead = _AHEAD_RE.search(track)
        behind = _BEHIND_RE.search(track)
        if ahead is None and behind is None:
            return None
        return (
            int(ahead.group(1)) if ahead else 0,
            int(behind.group(1)) if behind else 0,
        )

    def _ahead_behind_slow(self, branch: str) -> Optional[tuple[int, int]]:
        try:
            head = self.repo.heads[branch]
            tracking = head.tracking_branch()
            if tracking is None:
                return None
            ahead = int(self.repo.git.rev_list("--count", f"{tracking.name}..{head.name}"))
            behind = int(self.repo.git.rev_list("--count", f"{head.name}..{tracking.name}"))
            return (ahead, behind)
        except (git.GitCommandError, IndexError, ValueError):
            return None

    @_synchronized
    def branch_ahead_behind(self) -> dict[str, tuple[int, int]]:
        """Pour chaque branche locale ayant une branche amont (tracking),
        retourne {nom: (ahead, behind)} par rapport à cette branche amont."""
        return self.refs_snapshot().ahead_behind

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
    def commit_log(
        self,
        max_count: int = 300,
        ref_map: Optional[dict[str, list[str]]] = None,
    ) -> list[CommitInfo]:
        """Retourne les commits en ordre topologique (parent après enfant),
        avec les refs (branches/tags) qui pointent dessus.

        Un seul processus `git log` pour tout l'historique affiché ; `ref_map`
        permet de réutiliser un `refs_snapshot()` déjà lu."""
        self._require_repo()
        if ref_map is None:
            ref_map = self.refs_snapshot().ref_map

        fmt = "%H%x00%P%x00%an%x00%ae%x00%ct%x00%s%x1e"
        try:
            output = self.repo.git.log(
                "--all", "--topo-order", f"--max-count={max_count}", f"--format={fmt}"
            )
        except git.GitCommandError:
            # dépôt sans commit
            return []

        commits: list[CommitInfo] = []
        for record in output.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            fields = record.split("\x00")
            if len(fields) < 6:
                continue
            sha, parents, author, email, timestamp, subject = fields[:6]
            commits.append(
                CommitInfo(
                    sha=sha,
                    short_sha=sha[:7],
                    message=subject.strip(),
                    author=author,
                    author_email=email,
                    date=datetime.fromtimestamp(int(timestamp)),
                    parents=parents.split(),
                    refs=ref_map.get(sha, []),
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
        # vrai diff unifié (avec en-tête de hunk, sans quoi il serait ignoré)
        # où tout le contenu est en ajout
        full_path = Path(self.working_dir) / path
        if staged or not full_path.is_file():
            return diff
        try:
            untracked = self.repo.git.ls_files("--others", "--exclude-standard", "--", path)
        except git.GitCommandError:
            return diff
        if not untracked.strip():
            return diff
        try:
            raw = full_path.read_bytes()
        except OSError:
            return ""
        if b"\x00" in raw[:8192]:
            return f"Binary files /dev/null and b/{path} differ"
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if not lines:
            return ""
        body = "\n".join(f"+{line}" for line in lines)
        return f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}"

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

    def fetch_background(self, remote_name: str = "origin") -> str:
        """Fetch lancé comme processus `git` indépendant, SANS tenir le verrou
        du dépôt : le reste de l'application reste utilisable pendant le
        transfert réseau (le fetch via GitPython sérialiserait toute l'UI)."""
        with self._lock:
            self._require_repo()
            try:
                self.repo.remote(remote_name)
            except ValueError as exc:
                raise GitBackendError(f"Remote introuvable : '{remote_name}'.") from exc
            cwd = self.repo.working_tree_dir or self.repo.git_dir

        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        executable = getattr(git.Git, "GIT_PYTHON_GIT_EXECUTABLE", None) or "git"
        try:
            process = subprocess.Popen(
                [executable, "fetch", remote_name],
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=flags,
            )
        except OSError as exc:
            raise GitBackendError(f"Échec du fetch: {exc}") from exc
        self._background_process = process
        try:
            _out, err = process.communicate(timeout=BACKGROUND_FETCH_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise GitBackendError("Échec du fetch: délai dépassé.") from None
        finally:
            self._background_process = None
        text = err.decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise GitBackendError(f"Échec du fetch: {text.strip() or process.returncode}")
        updated = sum(1 for line in text.splitlines() if "->" in line)
        return f"Fetch OK ({updated} ref(s) mise(s) à jour)"

    def cancel_background_fetch(self) -> None:
        """Interrompt le fetch en arrière-plan (fermeture de l'application)."""
        process = self._background_process
        if process is not None and process.poll() is None:
            process.terminate()

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
