"""Stage current provider sources for isolated build/test without replacing live web assets."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".runtime/plugin-managed-setup/candidates"


def source_files(source):
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=source, text=True).splitlines()
    return {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in names if (source / name).is_file()}


def main():
    from workspace import modules
    for module in modules():
        source = module.directory
        if not (source / "package.json").is_file():
            continue
        destination = TARGET / source.name
        destination.mkdir(parents=True, exist_ok=True)
        before = source_files(source)
        files = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=source, text=True
        ).splitlines()
        previous = destination / ".candidate-files.json"
        if previous.exists():
            for stale in set(json.loads(previous.read_text())) - set(files):
                (destination / stale).unlink(missing_ok=True)
        for name in files:
            path = source / name
            if path.is_file():
                output = destination / name
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, output)
            elif (destination / name).is_file():
                # git ls-files also reports tracked deletions: never retain retired
                # provider code from an earlier candidate snapshot.
                (destination / name).unlink()
        if source_files(source) != before:
            raise RuntimeError("Source changed while staging; retry snapshot: " + source.name)
        previous.write_text(json.dumps(list(before)))
        for name in ["node_modules", "web/node_modules", ".runtime/worker-venv" if source.name == "fpl-core" else ".runtime/venv"]:
            link = destination / name
            link.parent.mkdir(parents=True, exist_ok=True)
            if not link.exists():
                link.symlink_to(source / name, target_is_directory=True)
        if source.name != "fpl-core":
            # This command explicitly stages a joint-development combination.
            # Package the staged Core snapshot, not an implicit sibling dependency.
            link = destination / ".runtime/core-source"
            if not link.is_symlink() and link.exists():
                raise RuntimeError("Refusing to replace a non-link Core source: " + str(link))
            if link.is_symlink():
                link.unlink()
            link.symlink_to(TARGET / "fpl-core", target_is_directory=True)
    print(TARGET)


if __name__ == "__main__":
    main()
