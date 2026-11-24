import hashlib
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ROOT / ".runtime/plugin-managed-setup/candidates"
OUT = ROOT / ".local/plugin-managed-setup"


@pytest.mark.twp("distribution.payloads")
def test_seven_self_contained_payloads(twp_evidence):
    rows, core = [], None
    for repo in sorted(CANDIDATES.glob("dsh-*")):
        meta = json.loads((repo / "package.json").read_text())
        archive = repo / ".runtime/packages" / (meta["name"].replace("@", "").replace("/", "-") + "-" + meta["version"] + ".tgz")
        with tarfile.open(archive) as package:
            names = package.getnames()
            assert not any(name.endswith("service-installation.json") for name in names)
            prefix = "package/" + ("lib" if repo.name == "dsh-core" else "src") + "/runtime/"
            manifest = json.load(package.extractfile(prefix + "service.json"))
            payload = package.extractfile(prefix + "service.zip").read()
            assert hashlib.sha256(payload).hexdigest() == manifest["sha256"]
            assert len(payload) == manifest["byte_size"]
            assert manifest["platforms"] == ["darwin-arm64", "darwin-x64"]
            assert manifest["python"] == "3.13.15"
            assert meta["engines"]["dsh"] == "0.2.2-rc.1 || 0.2.2-rc.5"
            with zipfile.ZipFile(io.BytesIO(payload)) as service:
                assert set(service.namelist()) == set(manifest["files"])
                assert sum(service.getinfo(name).file_size for name in service.namelist()) == manifest["expanded_size"]
                for name in service.namelist():
                    assert ".." not in Path(name).parts and not name.startswith("/")
                    assert not any(part in {".local", "node_modules", "__pycache__", "worker-venv", "venv"} for part in Path(name).parts)
                    assert hashlib.sha256(service.read(name)).hexdigest() == manifest["files"][name]
                assert "python/" + manifest["module"] + "/cli.py" in service.namelist()
                assert ("web/dist/index.html" if repo.name == "dsh-core" else ".runtime/web/index.html") in service.namelist()
                assert ("python/uv.lock" if repo.name == "dsh-core" else "uv.lock") in service.namelist()
                if repo.name == "dsh-core":
                    assert all("/brand/" not in name or name.endswith("/brand/icon.webp") for name in service.namelist())
            if repo.name == "dsh-core":
                core = (archive, meta)
        rows.append({"package": meta["name"], "version": meta["version"], "tarball_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "payload_sha256": manifest["sha256"], "payload_bytes": len(payload),
            "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT / repo.name, text=True).strip(),
            "candidate_source_sha256": hashlib.sha256(b"".join(name.encode() + b"\0" + hashlib.sha256((repo / name).read_bytes()).digest()
                for name in sorted(json.loads((repo / ".candidate-files.json").read_text())) if (repo / name).is_file())).hexdigest()})
        twp_evidence.step(repo.name + " payload, platform, lock and compiled UI verified")
    assert len(rows) == 7
    # Import the actual packed Core with only its mandatory dependency links.
    consumer = ROOT / ".runtime/plugin-managed-setup/optional-peer-consumer"
    modules = consumer / "node_modules"
    destination = modules / "@dsh-plugin-fpl/dsh-core"
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(core[0]) as package:
        for item in package.getmembers():
            relative = Path(item.name).relative_to("package")
            assert ".." not in relative.parts and item.isfile()
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.extractfile(item).read())
    dependencies = {**core[1]["dependencies"], **core[1]["peerDependencies"]}
    for name in dependencies:
        if core[1].get("peerDependenciesMeta", {}).get(name, {}).get("optional"):
            continue
        target = modules / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.symlink_to(ROOT / "dsh-core/node_modules" / name, target_is_directory=True)
    assert not (modules / "@deepseek-ai/dsh-host-plugin-inventory").exists()
    result = subprocess.run(["node", "--input-type=module", "-e", "await import('@dsh-plugin-fpl/dsh-core'); console.log('core imported')"],
        cwd=consumer, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    twp_evidence.step("Packed Core imports with both optional providers absent")
    report = OUT / "payloads.json"
    report.write_text(json.dumps(rows, indent=2))
    twp_evidence.attach(report, mime="application/json")
