"""
gitflow.py
Implémentation du modèle Git Flow (Vincent Driessen) au-dessus de
GitBackend : init, feature/release/hotfix start & finish.

La configuration est stockée dans le git config du dépôt avec les mêmes
clés que l'outil `git flow` officiel (gitflow.branch.master,
gitflow.prefix.feature, …) : un dépôt initialisé ici est utilisable avec
la CLI git-flow et inversement. Aucune dépendance Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import git

from gitkrakit.core.git_backend import GitBackend, GitBackendError


@dataclass
class GitFlowConfig:
    main: str = "main"
    develop: str = "develop"
    feature_prefix: str = "feature/"
    release_prefix: str = "release/"
    hotfix_prefix: str = "hotfix/"


@dataclass
class GitFlowStatus:
    """Vue d'ensemble pour la sidebar : config + branches en cours
    (noms courts, sans préfixe)."""
    config: GitFlowConfig
    features: list[str] = field(default_factory=list)
    releases: list[str] = field(default_factory=list)
    hotfixes: list[str] = field(default_factory=list)


class GitFlow:
    def __init__(self, backend: GitBackend):
        self._backend = backend

    @property
    def _repo(self) -> git.Repo:
        if self._backend.repo is None:
            raise GitBackendError("Aucun dépôt ouvert.")
        return self._backend.repo

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def _get_config(self, key: str) -> str | None:
        try:
            return self._repo.git.config("--get", key)
        except git.GitCommandError:
            return None

    def is_initialized(self) -> bool:
        return self._get_config("gitflow.branch.master") is not None

    def config(self) -> GitFlowConfig | None:
        if not self.is_initialized():
            return None
        return GitFlowConfig(
            main=self._get_config("gitflow.branch.master") or "main",
            develop=self._get_config("gitflow.branch.develop") or "develop",
            feature_prefix=self._get_config("gitflow.prefix.feature") or "feature/",
            release_prefix=self._get_config("gitflow.prefix.release") or "release/",
            hotfix_prefix=self._get_config("gitflow.prefix.hotfix") or "hotfix/",
        )

    def status(self) -> GitFlowStatus | None:
        """None si le dépôt n'est pas ouvert ou Git Flow pas initialisé."""
        if not self._backend.is_open or not self.is_initialized():
            return None
        cfg = self.config()
        assert cfg is not None
        locals_ = self._backend.local_branches()

        def short_names(prefix: str) -> list[str]:
            return [b[len(prefix):] for b in locals_ if b.startswith(prefix)]

        return GitFlowStatus(
            config=cfg,
            features=short_names(cfg.feature_prefix),
            releases=short_names(cfg.release_prefix),
            hotfixes=short_names(cfg.hotfix_prefix),
        )

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    def init(self) -> GitFlowConfig:
        """Initialise Git Flow avec les valeurs par défaut : détecte la
        branche principale (main/master), crée develop si absente et la
        checkout, écrit la config compatible git-flow CLI."""
        repo = self._repo
        if not repo.head.is_valid():
            raise GitBackendError(
                "Fais un premier commit avant d'initialiser Git Flow."
            )

        heads = [h.name for h in repo.heads]
        cfg = GitFlowConfig()
        if "main" in heads:
            cfg.main = "main"
        elif "master" in heads:
            cfg.main = "master"
        else:
            cfg.main = self._backend.current_branch

        try:
            repo.git.config("gitflow.branch.master", cfg.main)
            repo.git.config("gitflow.branch.develop", cfg.develop)
            repo.git.config("gitflow.prefix.feature", cfg.feature_prefix)
            repo.git.config("gitflow.prefix.release", cfg.release_prefix)
            repo.git.config("gitflow.prefix.hotfix", cfg.hotfix_prefix)
            repo.git.config("gitflow.prefix.support", "support/")
            repo.git.config("gitflow.prefix.versiontag", "")

            if cfg.develop not in heads:
                repo.create_head(cfg.develop, cfg.main)
            repo.git.checkout(cfg.develop)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Échec de l'initialisation Git Flow: {exc}") from exc
        return cfg

    # ------------------------------------------------------------------
    # Start / finish
    # ------------------------------------------------------------------
    def _require_config(self) -> GitFlowConfig:
        cfg = self.config()
        if cfg is None:
            raise GitBackendError("Git Flow n'est pas initialisé sur ce dépôt.")
        return cfg

    def _start(self, full_name: str, base: str) -> None:
        repo = self._repo
        if full_name in [h.name for h in repo.heads]:
            raise GitBackendError(f"La branche '{full_name}' existe déjà.")
        try:
            repo.git.checkout("-b", full_name, base)
        except git.GitCommandError as exc:
            raise GitBackendError(f"Impossible de créer '{full_name}': {exc}") from exc

    def _merge_into(self, target: str, source: str) -> None:
        repo = self._repo
        try:
            repo.git.checkout(target)
            repo.git.merge("--no-ff", "-m", f"Merge branch '{source}' into {target}", source)
        except git.GitCommandError as exc:
            raise GitBackendError(
                f"Conflit ou échec du merge de '{source}' dans '{target}': {exc}\n"
                "Résous les conflits puis commit avant de recommencer."
            ) from exc

    def feature_start(self, name: str) -> str:
        cfg = self._require_config()
        full = cfg.feature_prefix + name.strip()
        self._start(full, cfg.develop)
        return f"Feature '{full}' créée depuis {cfg.develop}"

    def feature_finish(self, name: str) -> str:
        """Merge la feature dans develop puis supprime la branche."""
        cfg = self._require_config()
        full = cfg.feature_prefix + name.strip()
        self._merge_into(cfg.develop, full)
        self._delete_branch(full)
        return f"Feature '{full}' fusionnée dans {cfg.develop}"

    def release_start(self, version: str) -> str:
        cfg = self._require_config()
        full = cfg.release_prefix + version.strip()
        self._start(full, cfg.develop)
        return f"Release '{full}' créée depuis {cfg.develop}"

    def release_finish(self, version: str) -> str:
        """Merge la release dans main (avec tag) puis dans develop,
        supprime la branche, termine sur develop."""
        return self._finish_to_main_and_develop(
            self._require_config().release_prefix, version, "Release"
        )

    def hotfix_start(self, version: str) -> str:
        cfg = self._require_config()
        full = cfg.hotfix_prefix + version.strip()
        self._start(full, cfg.main)
        return f"Hotfix '{full}' créé depuis {cfg.main}"

    def hotfix_finish(self, version: str) -> str:
        """Merge le hotfix dans main (avec tag) puis dans develop."""
        return self._finish_to_main_and_develop(
            self._require_config().hotfix_prefix, version, "Hotfix"
        )

    def _finish_to_main_and_develop(self, prefix: str, version: str, label: str) -> str:
        cfg = self._require_config()
        version = version.strip()
        full = prefix + version

        self._merge_into(cfg.main, full)
        tag_prefix = self._get_config("gitflow.prefix.versiontag") or ""
        tag_name = f"{tag_prefix}{version}"
        try:
            self._repo.git.tag("-a", tag_name, "-m", f"{label} {version}")
        except git.GitCommandError as exc:
            raise GitBackendError(f"Impossible de créer le tag '{tag_name}': {exc}") from exc

        self._merge_into(cfg.develop, full)
        self._delete_branch(full)
        return f"{label} '{version}' fusionné(e) dans {cfg.main} + {cfg.develop}, tag '{tag_name}'"

    def _delete_branch(self, full_name: str) -> None:
        try:
            self._repo.delete_head(full_name)
        except Exception as exc:
            raise GitBackendError(
                f"Branche fusionnée mais impossible de la supprimer: {exc}"
            ) from exc
