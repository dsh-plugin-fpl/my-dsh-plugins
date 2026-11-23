"""Deterministic CLI acceptance tests using local-only disposable Git repos."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
BASE = SOURCE / ".local/workspace-tests"


def run(repo, *args, env=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args], env=env,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["git", "-C", str(SOURCE), "check-ignore", "--quiet",
                        str(BASE)], check=True)
        BASE.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=BASE)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update({
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull, "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "file", "GIT_AUTHOR_NAME": "Workspace Test",
            "GIT_COMMITTER_NAME": "Workspace Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": os.devnull,
            "GIT_CONFIG_KEY_1": "commit.gpgsign", "GIT_CONFIG_VALUE_1": "false",
        })
        self.plugin = self.base / "plugin-source"
        self.init(self.plugin)
        for name, content in (("README.md", "# Plugin\n"), ("AGENTS.md", "Rules\n"),
                              (".gitignore", ".local/\n")):
            (self.plugin / name).write_text(content)
        self.commit(self.plugin)
        self.root = self.base / "workspace"
        self.init(self.root)
        for name in ("README.md", "AGENTS.md", ".gitignore"):
            shutil.copy2(SOURCE / name, self.root / name)
        for name in ("docs", "scripts"):
            shutil.copytree(SOURCE / name, self.root / name)
        (self.root / "tests/integration").mkdir(parents=True)
        shutil.copy2(SOURCE / "tests/integration/README.md",
                     self.root / "tests/integration/README.md")
        self.g(self.root, "submodule", "add", str(self.plugin), "dsh-core")
        self.commit(self.root)

    def g(self, repo, *args):
        return run(repo, *args, env=self.env)

    def init(self, repo):
        repo.mkdir()
        self.g(repo, "init", "-b", "main")

    def commit(self, repo):
        self.g(repo, "add", "--all")
        self.g(repo, "commit", "-m", "fixture")
        return self.g(repo, "rev-parse", "HEAD")

    def cli(self, command, expected=0, root=None):
        root = root or self.root
        result = subprocess.run(
            [sys.executable, "-B", str(root / "scripts/workspace.py"), command],
            cwd=self.base, env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def snapshot(self, repo):
        return (self.g(repo, "rev-parse", "HEAD"),
                self.g(repo, "status", "--porcelain=v1"),
                self.g(repo, "symbolic-ref", "--short", "HEAD"))

    def test_clean_check_and_bootstrap_preserve_existing_branch(self):
        before = self.snapshot(self.root / "dsh-core")
        self.assertIn("Check OK", self.cli("check"))
        self.cli("bootstrap")
        self.cli("bootstrap")
        self.assertEqual(before, self.snapshot(self.root / "dsh-core"))

    def test_missing_module_then_repeatable_bootstrap(self):
        clone = self.base / "clone"
        self.g(self.base, "clone", str(self.root), str(clone))
        self.assertIn("UNINITIALIZED", self.cli("status", root=clone))
        self.cli("check", expected=1, root=clone)
        self.cli("bootstrap", root=clone)
        self.cli("check", root=clone)
        self.cli("bootstrap", root=clone)
        self.assertEqual(self.g(self.root / "dsh-core", "rev-parse", "HEAD"),
                         self.g(clone / "dsh-core", "rev-parse", "HEAD"))

    def test_dirty_module_is_never_overwritten(self):
        plugin = self.root / "dsh-core"
        target = plugin / "README.md"
        target.write_text("user changes\n")
        (plugin / "untracked.txt").write_text("keep me\n")
        before = self.snapshot(plugin)
        self.cli("bootstrap", expected=1)
        self.assertEqual(before, self.snapshot(plugin))
        self.assertEqual(target.read_text(), "user changes\n")
        self.assertTrue((plugin / "untracked.txt").exists())
        self.assertIn("WARN", self.cli("check"))

    def test_drift_does_not_advance_to_latest_or_switch_branch(self):
        plugin = self.root / "dsh-core"
        (plugin / "README.md").write_text("new version\n")
        self.commit(plugin)
        before = self.snapshot(plugin)
        self.assertIn("DIFFERENT", self.cli("status"))
        self.cli("bootstrap", expected=1)
        self.cli("check", expected=1)
        self.assertEqual(before, self.snapshot(plugin))

    def test_preflight_checks_all_modules_before_mutating_any(self):
        self.g(self.root, "submodule", "add", str(self.plugin), "dsh-second")
        self.commit(self.root)
        self.g(self.root, "submodule", "deinit", "--force", "--", "dsh-core")
        (self.root / "dsh-second/README.md").write_text("keep\n")
        self.cli("bootstrap", expected=1)
        self.assertFalse((self.root / "dsh-core/.git").exists())
        self.assertEqual((self.root / "dsh-second/README.md").read_text(), "keep\n")

    def test_nonempty_missing_module_directory_is_preserved(self):
        self.g(self.root, "submodule", "deinit", "--force", "--", "dsh-core")
        target = self.root / "dsh-core/keep.txt"
        target.write_text("keep\n")
        self.cli("bootstrap", expected=1)
        self.assertEqual(target.read_text(), "keep\n")

    def test_status_without_upstream_is_read_only(self):
        before = self.snapshot(self.root)
        result = self.cli("status")
        self.assertIn("upstream=none", result)
        self.assertIn("MATCH", result)
        self.assertEqual(before, self.snapshot(self.root))

    def test_status_with_cached_upstream_counts(self):
        clone = self.base / "clone"
        self.g(self.base, "clone", "--recurse-submodules", str(self.root), str(clone))
        self.assertIn("ahead=0 behind=0", self.cli("status", root=clone))
        (clone / "extra.txt").write_text("one\n")
        self.commit(clone)
        self.assertIn("ahead=1 behind=0", self.cli("status", root=clone))

    def test_second_module_is_discovered_without_script_changes(self):
        self.g(self.root, "submodule", "add", str(self.plugin), "dsh-second")
        self.commit(self.root)
        self.assertIn("dsh-second:", self.cli("status"))
        self.assertIn("2 个直接子模块", self.cli("check"))

    def test_broken_links_and_missing_plugin_guidance_fail(self):
        target = self.root / "docs/architecture.md"
        target.write_text(target.read_text() + "\n[missing](missing.md)\n")
        self.assertIn("失效本地链接", self.cli("check", expected=1))
        target.write_text((SOURCE / "docs/architecture.md").read_text())
        (self.root / "dsh-core/AGENTS.md").unlink()
        self.assertIn("插件缺少基本文件", self.cli("check", expected=1))

    def test_unregistered_gitlink_and_unsafe_path_fail(self):
        config = self.root / ".gitmodules"
        original = config.read_text()
        config.write_text("")
        self.assertIn("未在 .gitmodules 登记", self.cli("check", expected=1))
        config.write_text(original.replace("path = dsh-core", "path = ../outside"))
        self.assertIn("根目录直接子目录", self.cli("bootstrap", expected=1))

    def test_interrupted_initialization_can_be_retried(self):
        self.g(self.root, "submodule", "deinit", "--force", "--", "dsh-core")
        # Missing local remote: no network, no data deletion, retry after restoring it.
        metadata = self.root / ".git/modules/dsh-core"
        saved = self.root / ".git/modules/saved-core"
        metadata.rename(saved)
        self.g(self.root, "config", "submodule.dsh-core.url", str(self.base / "absent"))
        self.cli("bootstrap", expected=1)
        saved.rename(metadata)
        self.g(self.root, "config", "submodule.dsh-core.url", str(self.plugin))
        self.cli("bootstrap")
        self.cli("check")


if __name__ == "__main__":
    unittest.main()
