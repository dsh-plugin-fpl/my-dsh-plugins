"""Copy the installed Desktop's public Host distribution into an isolated test runtime."""
import hashlib
import json
import plistlib
import shutil
import struct
from pathlib import Path


def prepare(root, expected="0.2.2-rc.1"):
    app = Path("/Applications/DeepSeek Harness.app/Contents")
    version = plistlib.loads((app / "Info.plist").read_bytes())["CFBundleShortVersionString"]
    if version != expected:
        raise RuntimeError("Desktop version changed; expected " + expected + ", found " + version)
    resources = app / "Resources"
    archive = resources / "app.asar"
    node = resources / "runtime/primary-runtime/dependencies/node/bin/node"
    metadata = json.loads((resources / "runtime/primary-runtime/runtime.json").read_text())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    destination = root / ".runtime/plugin-managed-setup" / ("desktop-runtime-" + expected)
    marker = destination / "source.json"
    if not marker.exists() or json.loads(marker.read_text()).get("asar_sha256") != digest:
        destination.mkdir(parents=True, exist_ok=True)
        with archive.open("rb") as stream:
            _, header_size, _, string_size = struct.unpack("<IIII", stream.read(16))
            tree = json.loads(stream.read(string_size))
            offset = 8 + header_size

            def copy(directory, prefix):
                for name, item in directory["files"].items():
                    relative = prefix / name
                    if name in {".", ".."} or "/" in name or "link" in item:
                        raise RuntimeError("Unexpected Desktop archive path or link")
                    target = destination / relative
                    if "files" in item:
                        target.mkdir(parents=True, exist_ok=True)
                        copy(item, relative)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if item.get("unpacked"):
                            shutil.copy2(resources / "app.asar.unpacked" / relative, target)
                        else:
                            stream.seek(offset + int(item["offset"]))
                            data = stream.read(item["size"])
                            if len(data) != item["size"]:
                                raise RuntimeError("Incomplete Desktop archive")
                            target.write_bytes(data)
                            target.chmod(0o755 if item.get("executable") else 0o644)
            copy({"files": {"dsh": tree["files"]["dsh"]}}, Path())
        (destination / "bin").mkdir(exist_ok=True)
        shutil.copy2(node, destination / "bin/node")
        marker.write_text(json.dumps({"desktop_version": version, "asar_sha256": digest, "node_version": metadata["node"],
            "platform": metadata["platform"], "arch": metadata["arch"], "desktop_payload_digest": metadata["payloadDigest"]}, indent=2) + "\n")
    host = destination / "dsh/node_modules/@deepseek-ai/dsh/package.json"
    if json.loads(host.read_text())["version"] != expected:
        raise RuntimeError("Desktop and bundled Host versions differ")
    return {"kind": "desktop-bundled", "node": str(destination / "bin/node"),
        "cli": str(host.parent / "lib/bin.js"), "scope": str(destination / "dsh/node_modules/@deepseek-ai"),
        "provenance": str(marker)}
