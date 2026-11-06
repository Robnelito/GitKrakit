from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# Les tests de widgets n'ouvrent aucune fenêtre : à poser avant tout import Qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from git import Repo

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gitkrakit import preferences, theme
from gitkrakit.core import (
    CommitInfo,
    GitBackend,
    GitBackendError,
    GitFlow,
    GraphLayout,
    parse_unified_diff,
    split_command,
)
from gitkrakit.core.acp_commit import (
    AcpCommitError,
    build_commit_prompt,
    normalize_commit_message,
)
from gitkrakit.ui.panels import SidebarPanel
from gitkrakit.ui.panels.sidebar_panel import _expansion_key
from gitkrakit.workspace import WorkspaceError, WorkspaceManager


class CommandParserTests(unittest.TestCase):
    def test_preserves_quoted_arguments_and_windows_paths(self) -> None:
        self.assertEqual(
            split_command('commit -m "hello world" C:\\work\\file.txt'),
            ["commit", "-m", "hello world", "C:\\work\\file.txt"],
        )

    def test_reports_unclosed_quote(self) -> None:
        with self.assertRaises(ValueError):
            split_command('commit -m "unfinished')


class DiffParserTests(unittest.TestCase):
    def test_aligns_replacement_and_addition(self) -> None:
        diff = """diff --git a/demo.py b/demo.py
--- a/demo.py
+++ b/demo.py
@@ -1,2 +1,3 @@
-old
+new
 same
+extra
"""
        rows = parse_unified_diff(diff)
        self.assertEqual([row.kind for row in rows], ["hunk", "mod", "context", "add"])
        self.assertEqual((rows[1].old_no, rows[1].new_no), (1, 1))
        self.assertEqual(rows[3].new_text, "extra")


class AcpCommitTests(unittest.TestCase):
    def test_prompt_marks_the_diff_as_untrusted_and_requires_conventional_commits(self) -> None:
        prompt = build_commit_prompt("diff --git a/a.py b/a.py\n+print('ok')")
        self.assertIn("Conventional Commits 1.0.0", prompt)
        self.assertIn("untrusted code and data", prompt)
        self.assertIn("<staged_diff>", prompt)

    def test_normalizes_markdown_fence_and_validates_header(self) -> None:
        self.assertEqual(
            normalize_commit_message("```text\nfeat(acp): generate commit messages\n```"),
            "feat(acp): generate commit messages",
        )
        with self.assertRaises(AcpCommitError):
            normalize_commit_message("Here is your commit message: feat: add ACP")


class GraphLayoutTests(unittest.TestCase):
    @staticmethod
    def _commit(sha: str, parents: list[str]) -> CommitInfo:
        return CommitInfo(sha, sha[:7], sha, "Ada", "ada@example.test", datetime.now(), parents)

    def test_merge_connects_both_parents(self) -> None:
        commits = [
            self._commit("merge000", ["left000", "right00"]),
            self._commit("left000", ["root000"]),
            self._commit("right00", ["root000"]),
            self._commit("root000", []),
        ]
        layout = GraphLayout(commits)
        self.assertEqual(len(layout.nodes[0].parent_lanes), 2)
        self.assertGreaterEqual(layout.lane_count, 2)


class ThemeTests(unittest.TestCase):
    def test_resolves_explicit_and_system_modes(self) -> None:
        self.assertEqual(theme.resolve_theme_mode(theme.THEME_LIGHT, True), theme.THEME_LIGHT)
        self.assertEqual(theme.resolve_theme_mode(theme.THEME_DARK, False), theme.THEME_DARK)
        self.assertEqual(theme.resolve_theme_mode(theme.THEME_SYSTEM, True), theme.THEME_DARK)
        self.assertEqual(theme.resolve_theme_mode(theme.THEME_SYSTEM, False), theme.THEME_LIGHT)
        self.assertEqual(theme.resolve_theme_mode("invalid", False), theme.THEME_LIGHT)


class WorkspaceManagerTests(unittest.TestCase):
    def test_persists_workspaces_and_deduplicates_recents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "workspaces.json"
            manager = WorkspaceManager(config)
            manager.create_workspace("Client")
            manager.add_repo("Client", str(Path(directory) / "repo"))
            manager.touch_recent(str(Path(directory) / "repo"))
            manager.touch_recent(str(Path(directory) / "repo"))

            restored = WorkspaceManager(config)
            self.assertEqual(restored.get("Client").repos, manager.get("Client").repos)
            self.assertEqual(len(restored.recent), 1)

    def test_rejects_duplicate_workspace_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = WorkspaceManager(Path(directory) / "workspaces.json")
            manager.create_workspace("Client")
            with self.assertRaises(WorkspaceError):
                manager.create_workspace("Client")


class PreferencesTests(unittest.TestCase):
    def test_normalizes_provider_ids_to_display_order(self) -> None:
        self.assertEqual(
            preferences.normalize_provider_ids(["claude", "codex", "claude"]),
            list(preferences.ACP_PROVIDER_ORDER),
        )

    def test_drops_unknown_providers_and_empty_selections(self) -> None:
        self.assertEqual(preferences.normalize_provider_ids(["gemini"]), [])
        self.assertEqual(preferences.normalize_provider_ids(None), [])
        self.assertEqual(preferences.normalize_provider_ids("codex"), ["codex"])

    def test_reads_qsettings_string_booleans(self) -> None:
        self.assertTrue(preferences.as_bool("true"))
        self.assertFalse(preferences.as_bool("false"))
        self.assertFalse(preferences.as_bool(0))
        self.assertTrue(preferences.as_bool(None))
        self.assertFalse(preferences.as_bool(None, default=False))


class SidebarExpansionTests(unittest.TestCase):
    """Le repli des dossiers de branches doit survivre au rafraîchissement
    comme à la fermeture de l'application."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)

        # Réglages isolés : les tests ne doivent jamais écrire dans la
        # configuration réelle de l'utilisateur.
        settings_path = str(Path(self._directory.name) / "settings.ini")
        original_settings = preferences._settings
        preferences._settings = lambda: QSettings(settings_path, QSettings.IniFormat)
        self.addCleanup(setattr, preferences, "_settings", original_settings)

        self.panel = self._new_panel()

    def _new_panel(self) -> SidebarPanel:
        """Une nouvelle instance équivaut à un redémarrage de l'application."""
        manager = WorkspaceManager(Path(self._directory.name) / "workspaces.json")
        panel = SidebarPanel(manager)
        self.addCleanup(panel.deleteLater)
        return panel

    def _refresh(self, local: list[str]) -> None:
        self.panel.update_refs(
            local=local,
            remote=["origin/main", "origin/feature/a"],
            tags=["v1.0.0"],
            current_branch="main",
        )

    def _section(self, title: str):
        tree = self.panel.refs_tree
        for index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(index)
            if item.text(0) == title:
                return item
        raise AssertionError(f"section absente : {title}")

    @staticmethod
    def _child(parent, label: str):
        for index in range(parent.childCount()):
            child = parent.child(index)
            if child.text(0) == label:
                return child
        raise AssertionError(f"élément absent : {label}")

    def test_collapsed_folder_stays_collapsed_after_refresh(self) -> None:
        self._refresh(["main", "feature/a", "feature/b"])
        folder = self._child(self._section("Local"), "feature")
        self.assertTrue(folder.isExpanded())
        folder.setExpanded(False)

        self._refresh(["main", "feature/a", "feature/b", "feature/c"])
        folder = self._child(self._section("Local"), "feature")
        self.assertFalse(folder.isExpanded())
        self.assertEqual(folder.childCount(), 3)  # la nouvelle branche est bien là

    def test_collapsed_section_stays_collapsed_and_others_stay_open(self) -> None:
        self._refresh(["main", "feature/a"])
        self._section("Remote").setExpanded(False)

        self._refresh(["main", "feature/a"])
        self.assertFalse(self._section("Remote").isExpanded())
        self.assertTrue(self._section("Local").isExpanded())
        self.assertTrue(self._section("Tags").isExpanded())

    def test_reopening_a_folder_is_remembered_too(self) -> None:
        self._refresh(["main", "feature/a"])
        self._child(self._section("Local"), "feature").setExpanded(False)
        self._refresh(["main", "feature/a"])
        self._child(self._section("Local"), "feature").setExpanded(True)

        self._refresh(["main", "feature/a"])
        self.assertTrue(self._child(self._section("Local"), "feature").isExpanded())

    def test_new_folder_opens_by_default(self) -> None:
        self._refresh(["main", "feature/a"])
        self._child(self._section("Local"), "feature").setExpanded(False)

        self._refresh(["main", "feature/a", "hotfix/urgent"])
        self.assertFalse(self._child(self._section("Local"), "feature").isExpanded())
        self.assertTrue(self._child(self._section("Local"), "hotfix").isExpanded())

    def test_closed_repository_does_not_erase_the_memory(self) -> None:
        self._refresh(["main", "feature/a"])
        self._child(self._section("Local"), "feature").setExpanded(False)

        self.panel._repo_open = False  # dépôt refermé : placeholder à la place
        self.panel.refresh()
        self._refresh(["main", "feature/a"])
        self.assertFalse(self._child(self._section("Local"), "feature").isExpanded())

    def test_collapse_survives_an_application_restart(self) -> None:
        self._refresh(["main", "feature/a"])
        self._child(self._section("Local"), "feature").setExpanded(False)
        self._section("Tags").setExpanded(False)
        # Aucun rafraîchissement entre le repli et la fermeture : le choix
        # doit déjà être écrit sur disque.
        self.assertEqual(
            preferences.collapsed_sidebar_folders(),
            {_expansion_key(("Local", "feature")), _expansion_key(("Tags",))},
        )

        self.panel = self._new_panel()
        self._refresh(["main", "feature/a"])
        self.assertFalse(self._child(self._section("Local"), "feature").isExpanded())
        self.assertFalse(self._section("Tags").isExpanded())
        self.assertTrue(self._section("Local").isExpanded())

    def test_reopened_folder_is_forgotten_across_a_restart(self) -> None:
        self._refresh(["main", "feature/a"])
        self._child(self._section("Local"), "feature").setExpanded(False)
        self._child(self._section("Local"), "feature").setExpanded(True)
        self.assertEqual(preferences.collapsed_sidebar_folders(), set())

        self.panel = self._new_panel()
        self._refresh(["main", "feature/a"])
        self.assertTrue(self._child(self._section("Local"), "feature").isExpanded())


class GitBackendTests(unittest.TestCase):
    def test_stage_commit_status_and_log_in_temporary_repo(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        directory = temporary.name
        repo = Repo.init(directory)
        backend: GitBackend | None = None
        try:
            with repo.config_writer() as config:
                config.set_value("user", "name", "Test User")
                config.set_value("user", "email", "test@example.test")

            tracked = Path(directory) / "demo.txt"
            tracked.write_text("first\n", encoding="utf-8")
            backend = GitBackend(directory)

            staged, unstaged = backend.status()
            self.assertFalse(staged)
            self.assertEqual([(item.path, item.status) for item in unstaged], [("demo.txt", "untracked")])

            backend.stage(["demo.txt"])
            self.assertIn("+first", backend.staged_diff())
            backend.commit("Initial commit")
            self.assertEqual(backend.commit_log()[0].message, "Initial commit")

            tracked.write_text("second\n", encoding="utf-8")
            staged, unstaged = backend.status()
            self.assertFalse(staged)
            self.assertEqual(unstaged[0].status, "modified")
        finally:
            if backend is not None:
                backend.close()
            repo.close()
            temporary.cleanup()

    def test_revert_commit_restores_previous_content(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        directory = temporary.name
        repo = Repo.init(directory)
        backend: GitBackend | None = None
        try:
            with repo.config_writer() as config:
                config.set_value("user", "name", "Test User")
                config.set_value("user", "email", "test@example.test")

            tracked = Path(directory) / "demo.txt"
            backend = GitBackend(directory)
            tracked.write_text("first\n", encoding="utf-8")
            backend.stage(["demo.txt"])
            backend.commit("Initial commit")
            tracked.write_text("second\n", encoding="utf-8")
            backend.stage(["demo.txt"])
            backend.commit("Second commit")

            log = backend.commit_log()
            with self.assertRaises(GitBackendError):
                backend.revert_commit(log[-1].sha)  # commit initial : rien à annuler

            backend.revert_commit(log[0].sha)
            self.assertEqual(tracked.read_text(encoding="utf-8"), "first\n")
            self.assertIn("Revert", backend.commit_log()[0].message)
        finally:
            if backend is not None:
                backend.close()
            repo.close()
            temporary.cleanup()


def _init_repo(directory: str) -> Repo:
    repo = Repo.init(directory)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.test")
    return repo


def _commit_file(repo: Repo, name: str, content: str, message: str) -> None:
    (Path(repo.working_tree_dir) / name).write_text(content, encoding="utf-8")
    repo.git.add(name)
    repo.git.commit("-m", message)


class RefsSnapshotTests(unittest.TestCase):
    def test_snapshot_reports_ahead_behind_tags_and_ref_chips(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            origin = Repo.init(Path(root) / "origin.git", bare=True)
            work_dir = str(Path(root) / "work")
            seed = _init_repo(str(Path(root) / "seed"))
            _commit_file(seed, "a.txt", "1\n", "first")
            seed.git.branch("-M", "main")
            seed.git.remote("add", "origin", origin.git_dir)
            seed.git.push("origin", "main")
            clone = Repo.clone_from(origin.git_dir, work_dir, branch="main")
            with clone.config_writer() as config:
                config.set_value("user", "name", "Test User")
                config.set_value("user", "email", "test@example.test")
            backend = GitBackend(work_dir)
            try:
                self.assertEqual(backend.refs_snapshot().ahead_behind, {})

                _commit_file(clone, "b.txt", "2\n", "local only")
                clone.git.tag("-a", "v1", "-m", "release")
                _commit_file(seed, "c.txt", "3\n", "remote only")
                seed.git.push("origin", "main")
                backend.fetch_background()

                snapshot = backend.refs_snapshot()
                self.assertEqual(snapshot.ahead_behind, {"main": (1, 1)})
                self.assertIn("v1", snapshot.tags)
                self.assertIn("origin/main", snapshot.remote)
                # le tag annoté est rattaché au commit pointé, pas à l'objet tag
                head_refs = snapshot.ref_map[clone.head.commit.hexsha]
                self.assertIn("main", head_refs)
                self.assertIn("tag:v1", head_refs)
                self.assertEqual(snapshot.signature(), backend.refs_snapshot().signature())

                log = backend.commit_log(ref_map=snapshot.ref_map)
                self.assertEqual([c.message for c in log].count("local only"), 1)
                self.assertEqual([c.message for c in log].count("remote only"), 1)
            finally:
                backend.close()
                clone.close()
                seed.close()
                origin.close()

    def test_signature_changes_when_a_ref_moves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = _init_repo(directory)
            backend = GitBackend(directory)
            try:
                _commit_file(repo, "a.txt", "1\n", "first")
                before = backend.refs_snapshot().signature()
                _commit_file(repo, "a.txt", "2\n", "second")
                self.assertNotEqual(before, backend.refs_snapshot().signature())
            finally:
                backend.close()
                repo.close()

    def test_commit_log_on_empty_repository_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = _init_repo(directory)
            backend = GitBackend(directory)
            try:
                self.assertEqual(backend.commit_log(), [])
                self.assertEqual(backend.refs_snapshot().local, [])
            finally:
                backend.close()
                repo.close()

    def test_commit_log_keeps_unicode_and_parents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = _init_repo(directory)
            backend = GitBackend(directory)
            try:
                _commit_file(repo, "a.txt", "1\n", "premier : été")
                _commit_file(repo, "a.txt", "2\n", "second")
                log = backend.commit_log()
                self.assertEqual([c.message for c in log], ["second", "premier : été"])
                self.assertEqual(log[0].parents, [log[1].sha])
                self.assertEqual(log[1].parents, [])
                self.assertEqual(log[0].author, "Test User")
            finally:
                backend.close()
                repo.close()


class UntrackedDiffTests(unittest.TestCase):
    def test_untracked_file_diff_is_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = _init_repo(directory)
            backend = GitBackend(directory)
            try:
                _commit_file(repo, "a.txt", "1\n", "first")
                (Path(directory) / "new.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
                rows = parse_unified_diff(backend.diff_for_file("new.py"))
                self.assertEqual([r.kind for r in rows], ["hunk", "add", "add"])
                self.assertEqual(rows[2].new_text, "y = 2")
            finally:
                backend.close()
                repo.close()

    def test_untracked_binary_and_empty_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = _init_repo(directory)
            backend = GitBackend(directory)
            try:
                _commit_file(repo, "a.txt", "1\n", "first")
                (Path(directory) / "blob.bin").write_bytes(b"\x00\x01\x02")
                (Path(directory) / "empty.txt").write_text("", encoding="utf-8")
                self.assertIn("Binary files", backend.diff_for_file("blob.bin"))
                self.assertEqual(backend.diff_for_file("empty.txt"), "")
            finally:
                backend.close()
                repo.close()


class GitFlowConfigTests(unittest.TestCase):
    def test_status_reads_configuration_and_branches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = _init_repo(directory)
            backend = GitBackend(directory)
            try:
                _commit_file(repo, "a.txt", "1\n", "first")
                repo.git.branch("-M", "main")
                flow = GitFlow(backend)
                self.assertIsNone(flow.status())
                self.assertFalse(flow.is_initialized())

                flow.init("main", "develop")
                flow.feature_start("login")
                status = flow.status()
                self.assertTrue(flow.is_initialized())
                self.assertEqual((status.config.main, status.config.develop), ("main", "develop"))
                self.assertEqual(status.config.feature_prefix, "feature/")
                self.assertEqual(status.features, ["login"])
            finally:
                backend.close()
                repo.close()


class DiffPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_large_diff_is_modelled_without_per_row_widgets(self) -> None:
        from gitkrakit.ui.panels.diff_panel import DiffPanel

        panel = DiffPanel()
        body = "\n".join(f"-old {i}\n+new {i}" for i in range(2000))
        panel.show_diff("big", f"@@ -1,2000 +1,2000 @@\n{body}", "a.py")
        self.assertEqual(panel.model.rowCount(), 2001)  # 1 hunk + 2000 lignes remplacées
        self.assertEqual(panel.summary_label.text(), "+2000  −2000")
        self.assertIsNone(panel.table.indexWidget(panel.model.index(5, 1)))
        self.assertIn("old 0", panel.model.index(1, 1).data())
        panel.apply_theme()  # ne doit ni lever ni vider le diff
        self.assertEqual(panel.model.rowCount(), 2001)

    def test_empty_and_binary_diffs_show_a_message(self) -> None:
        from gitkrakit.ui.panels.diff_panel import DiffPanel

        panel = DiffPanel()
        panel.show_diff("x", "", "a.py")
        self.assertEqual(panel.model.index(0, 0).data(), "(aucune différence)")
        panel.show_diff("x", "Binary files /dev/null and b/a.bin differ", "a.bin")
        self.assertEqual(panel.model.index(0, 0).data(), "(fichier binaire)")


class GraphViewRedrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _commits(count: int) -> list[CommitInfo]:
        return [
            CommitInfo(
                f"{i:040x}", f"{i:07x}", f"commit {i}", "Ada", "ada@example.test",
                datetime.now(), [f"{i + 1:040x}"] if i < count - 1 else [],
            )
            for i in range(count)
        ]

    @staticmethod
    def _count_redraws(view) -> list[int]:
        calls: list[int] = []
        original = view._redraw_scene

        def counted() -> None:
            calls.append(1)
            original()

        view._redraw_scene = counted
        return calls

    def test_unchanged_commits_do_not_rebuild_the_scene(self) -> None:
        from gitkrakit.ui.graph_view import GraphPanel

        panel = GraphPanel()
        panel.resize(1000, 600)
        redraws = self._count_redraws(panel.view)

        panel.set_commits(self._commits(20))
        settled = len(redraws)
        self.assertGreaterEqual(settled, 1)
        panel.set_commits(self._commits(20))  # mêmes shas/refs
        self.assertEqual(len(redraws), settled)

        changed = self._commits(20)
        changed[0].refs.append("main")
        panel.set_commits(changed)
        self.assertGreater(len(redraws), settled)

    def test_setting_identical_column_widths_does_not_redraw(self) -> None:
        from gitkrakit.ui.graph_view import GraphPanel

        panel = GraphPanel()
        panel.set_commits(self._commits(5))
        view = panel.view
        calls = self._count_redraws(view)
        view.set_column_widths(ref=view.col_ref, graph=view.col_graph, msg=view.col_msg)
        self.assertEqual(calls, [])
        view.set_column_widths(msg=view.col_msg + 10)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
