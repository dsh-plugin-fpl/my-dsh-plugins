#!/usr/bin/env python3
"""Manage pinned, direct Git submodules without third-party dependencies."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = (
    "README.md", "AGENTS.md", ".gitignore", "docs/architecture.md",
    "docs/development.md", "docs/adding-plugins.md", "docs/decisions.md",
    "docs/templates/plugin-agents.md", "tests/integration/README.md",
)


class WorkspaceError(Exception):
    """An actionable workspace or Git error."""


def git(repo: Path, *args: str, allow_failure: bool = False):
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if result.returncode and not allow_failure:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WorkspaceError(f"{repo.name}: git {args[0]} failed: {detail}")
    return result


@dataclass(frozen=True)
class Module:
    name: str
    path: str
    url: str
    pin: str

    @property
    def directory(self) -> Path:
        return ROOT / self.path


def modules() -> list[Module]:
    top = git(ROOT, "rev-parse", "--show-toplevel").stdout.strip()
    if Path(top).resolve() != ROOT:
        raise WorkspaceError("脚本必须位于总仓库的 scripts 目录。")
    entries = {}
    for record in git(ROOT, "ls-files", "--stage", "-z").stdout.split("\0"):
        if not record:
            continue
        header, path = record.split("\t", 1)
        mode, sha, stage = header.split()
        if stage != "0":
            raise WorkspaceError(f"索引有未解决的合并冲突：{path}")
        if mode == "160000":
            entries[path] = sha
    config = ROOT / ".gitmodules"
    if not config.is_file():
        raise WorkspaceError("缺少 .gitmodules；请先登记至少一个插件。")
    result = git(
        ROOT, "config", "--null", "--file", str(config),
        "--get-regexp", r"^submodule\..*\.(path|url)$", allow_failure=True,
    )
    if result.returncode not in (0, 1):
        raise WorkspaceError(f"无法解析 .gitmodules：{result.stderr.strip()}")
    configs = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        key, value = record.split("\n", 1)
        section, field = key.rsplit(".", 1)
        values = configs.setdefault(section, {})
        if field in values:
            raise WorkspaceError(f".gitmodules 重复字段：{key}")
        values[field] = value
    found = []
    seen = set()
    for section, values in configs.items():
        path, url = values.get("path", ""), values.get("url", "")
        parts = PurePosixPath(path).parts
        if (not path or len(parts) != 1 or path.startswith((".", "-"))
                or "\\" in path or any(c in path for c in "\n\r\t")
                or PurePosixPath(path).is_absolute()):
            raise WorkspaceError(f"子模块必须是根目录直接子目录：{path!r}")
        directory = ROOT / path
        if directory.is_symlink() or directory.resolve().parent != ROOT:
            raise WorkspaceError(f"子模块路径不可为符号链接或越界：{path}")
        if not url:
            raise WorkspaceError(f"子模块缺少 URL：{path}")
        if path in seen:
            raise WorkspaceError(f"子模块路径重复：{path}")
        if path not in entries:
            raise WorkspaceError(f"登记缺少索引 gitlink：{path}；请显式 git add 子模块目录。")
        seen.add(path)
        found.append(Module(section[len("submodule."):], path, url, entries[path]))
    if set(entries) != seen:
        raise WorkspaceError(f"gitlink 未在 .gitmodules 登记：{', '.join(sorted(set(entries) - seen))}")
    if not found:
        raise WorkspaceError(".gitmodules 没有登记直接子模块。")
    return sorted(found, key=lambda item: item.path)


def initialized(module: Module) -> bool:
    directory = module.directory
    if not (directory / ".git").exists():
        return False
    result = git(directory, "rev-parse", "--show-toplevel", allow_failure=True)
    if result.returncode or Path(result.stdout.strip()).resolve() != directory.resolve():
        raise WorkspaceError(f"子模块目录不是独立 Git 工作树：{module.path}")
    return True


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "--verify", "HEAD").stdout.strip()


def dirty(repo: Path) -> str:
    return git(repo, "status", "--porcelain=v1", "--untracked-files=all",
               "--ignore-submodules=none").stdout.strip()


def describe(repo: Path, label: str, pin: str | None = None) -> None:
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", allow_failure=True)
    sha = head(repo)
    changes = dirty(repo)
    print(f"{label}: branch={branch.stdout.strip() or 'DETACHED'} HEAD={sha[:12]} "
          f"{'DIRTY' if changes else 'clean'}")
    if pin is not None:
        print(f"  pinned={pin[:12]} {'MATCH' if pin == sha else 'DIFFERENT'}")
    upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
                   "@{upstream}", allow_failure=True)
    if upstream.returncode:
        print("  upstream=none（远端发布状态未验证）")
    else:
        name = upstream.stdout.strip()
        counts = git(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
        ahead, behind = counts.stdout.split()
        print(f"  upstream={name} ahead={ahead} behind={behind}（本地缓存；未 fetch）")
    if changes:
        for line in changes.splitlines():
            print(f"  {line}")


def status(items: list[Module]) -> None:
    describe(ROOT, "workspace")
    for module in items:
        if initialized(module):
            describe(module.directory, module.path, module.pin)
        else:
            print(f"{module.path}: UNINITIALIZED pinned={module.pin[:12]}")


def preflight(items: list[Module]) -> None:
    errors = []
    for module in items:
        if initialized(module):
            if dirty(module.directory):
                errors.append(f"{module.path} 有修改；先提交或自行保存，bootstrap 不覆盖。")
            if head(module.directory) != module.pin:
                errors.append(f"{module.path} 版本偏移；先核对分支与固定版本，bootstrap 不切换。")
        elif module.directory.exists():
            if not module.directory.is_dir() or any(module.directory.iterdir()):
                errors.append(f"{module.path} 未初始化但目录非空；请先检查，bootstrap 不覆盖。")
    if errors:
        raise WorkspaceError("\n".join(errors))


def bootstrap(items: list[Module]) -> None:
    # Complete the preflight for every module before initializing any module.
    preflight(items)
    for module in items:
        if not initialized(module):
            git(ROOT, "submodule", "update", "--init", "--checkout", "--", module.path)
            if not initialized(module) or head(module.directory) != module.pin:
                raise WorkspaceError(f"{module.path} 未能检出固定版本；保留现场后可重试。")
            print(f"Initialized {module.path} at {module.pin[:12]}")
    print("Bootstrap OK（固定版本；未更新已有分支）")


def check_documents(items: list[Module]) -> list[str]:
    errors = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append(f"缺少文档或忽略规则：{name}")
    for module in items:
        for name in ("README.md", "AGENTS.md", ".gitignore"):
            if not (module.directory / name).is_file():
                errors.append(f"插件缺少基本文件：{module.path}/{name}")
    # Only workspace-owned documentation; never traverse a plugin or .local.
    documents = [ROOT / "README.md", ROOT / "AGENTS.md"]
    documents.extend((ROOT / "docs").rglob("*.md"))
    documents.append(ROOT / "tests/integration/README.md")
    for source in documents:
        if not source.is_file():
            continue
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", source.read_text(encoding="utf-8")):
            target = target.strip().removeprefix("<").removesuffix(">")
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            destination = source.parent / unquote(url.path)
            if not destination.exists():
                errors.append(f"失效本地链接：{source.relative_to(ROOT)} -> {target}")
    return errors


def check(items: list[Module]) -> None:
    errors = check_documents(items)
    for module in items:
        if not initialized(module):
            errors.append(f"未初始化：{module.path}；运行 bootstrap。")
        elif head(module.directory) != module.pin:
            errors.append(f"固定版本不匹配：{module.path}")
    if errors:
        raise WorkspaceError("\n".join(errors))
    if dirty(ROOT):
        print("WARN: 工作区有未提交修改；结构检查不会修改它们。")
    print(f"Check OK: {len(items)} 个直接子模块；登记、固定版本与文档有效。")
    print("仅结构检查；未验证远端可达性或插件业务。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bootstrap", "status", "check"))
    args = parser.parse_args()
    try:
        items = modules()
        {"bootstrap": bootstrap, "status": status, "check": check}[args.command](items)
    except (WorkspaceError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
