"""Install two pinned Harness distributions and only local FPL tarballs into disposable profiles."""
import json
import socket
import subprocess
from pathlib import Path
from desktop_harness_runtime import prepare as desktop_runtime

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ["0.2.2-rc.1", "0.2.2-rc.5"]


def port():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


def main():
    # Do not silently install a tarball built before an installer fix made in
    # another active turn. Candidate builds are deliberate immutable snapshots.
    for name in ["src/runtime-manager.ts", "src/runtime-bootstrap.ts", "src/lifecycle.ts", "python/dsh_core_worker/cli.py"]:
        source = ROOT / "dsh-core" / name
        candidate = ROOT / ".runtime/plugin-managed-setup/candidates/dsh-core" / name
        if source.read_bytes() != candidate.read_bytes():
            raise RuntimeError("Installer source changed; rebuild the candidate before acceptance: " + name)
    output = ROOT / ".local/plugin-managed-setup"
    desktop = desktop_runtime(ROOT, VERSIONS[0])
    configurations = []
    for version in VERSIONS:
        base = ROOT / ".runtime/plugin-managed-setup" / ("host-" + version)
        profile = base / "profiles/acceptance"
        profile.mkdir(parents=True, exist_ok=True)
        control = output / ("host-" + version)
        control.mkdir(parents=True, exist_ok=True, mode=0o700)
        scope = profile / "node_modules/@deepseek-ai"
        backup = base / ".runtime/npm-scope"
        if version == VERSIONS[0] and scope.is_symlink():
            scope.unlink()
            backup.rename(scope)
        dependencies = {"@deepseek-ai/dsh": version}
        for name in ["dsh-tools", "dsh-llm", "dsh-credentials", "dsh-typert-protocol", "dsh-mcp-client", "dsh-host-plugin-inventory"]:
            dependencies["@deepseek-ai/" + name] = version
        dependencies["@deepseek-ai/cordis"] = "4.1.0"
        dependencies["react"] = "18.3.1"
        rows, bundles = [], []
        for directory in sorted((ROOT / ".runtime/plugin-managed-setup/candidates").glob("dsh-*")):
            meta = json.loads((directory / "package.json").read_text())
            archive = directory / ".runtime/packages" / (meta["name"].replace("@", "").replace("/", "-") + "-" + meta["version"] + ".tgz")
            if not archive.is_file():
                raise FileNotFoundError(archive)
            dependencies[meta["name"]] = "file:" + str(archive)
            bundles.append(meta["name"])
            rows.append({"id": directory.name, "endpoint": "http://127.0.0.1:" + str(port())})
        dependencies["fpl-managed-acceptance"] = "file:" + str(ROOT / "tests/integration/managed-host")
        (profile / "package.json").write_text(json.dumps({"name": "fpl-managed-acceptance-profile", "private": True, "type": "module", "dependencies": dependencies,
            "dsh": {"profile": {"bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", *bundles, "fpl-managed-acceptance"]}}}, indent=2) + "\n")
        # Harness itself publishes required service definitions as peer dependencies.
        # Its exact-version peer ranges keep these on the selected Host release.
        (profile / "pnpm-workspace.yaml").write_text("autoInstallPeers: true\nnodeLinker: hoisted\n")
        (profile / "cordis.patch.yml").write_text("".join("- id: " + row["id"] + "\n  config:\n    endpoint: " + row["endpoint"] + "\n" for row in rows))
        log = output / ("install-harness-" + version + ".log")
        with log.open("w") as stream:
            subprocess.run(["pnpm", "install", "--ignore-scripts", "--store-dir", str(output / "pnpm-store")], cwd=profile, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        runtime = desktop if version == VERSIONS[0] else {"kind": "npm", "node": "node", "cli": str(profile / "node_modules/@deepseek-ai/dsh/lib/bin.js")}
        if version == VERSIONS[0]:
            backup.parent.mkdir(parents=True, exist_ok=True)
            scope.rename(backup)
            scope.symlink_to(desktop["scope"], target_is_directory=True)
        configurations.append({"version": version, "base": str(base), "profile": str(profile), "control": str(control), "port": port(), "services": rows, **runtime})
        print("Installed isolated Harness", version, flush=True)
    (output / "harness-matrix.json").write_text(json.dumps(configurations, indent=2) + "\n")


if __name__ == "__main__":
    main()
