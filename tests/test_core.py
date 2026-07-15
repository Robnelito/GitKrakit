from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from git import Repo

from gitkrakit.core import CommitInfo, GitBackend, GraphLayout, parse_unified_diff, split_command
from gitkrakit.core.acp_commit import (
    AcpCommitError,
    build_commit_prompt,
    normalize_commit_message,
)
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


if __name__ == "__main__":
    unittest.main()
