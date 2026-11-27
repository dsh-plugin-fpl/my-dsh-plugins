"""Explicit local desktop recovery. Provider CLIs own database conversion and checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = [
    ("visual-workshop", "fpl_visual", 9366),
    ("video-editor", "fpl_video", 9361),
    ("presentation-workshop", "fpl_presentation", 9362),
    ("thought-workshop", "fpl_thought", 9363),
    ("galgame-workshop", "fpl_galgame", 9364),
    ("audio-annotation", "fpl_annotation", 9365),
]


PROFILES = [
    "Partitions",
    "Local State",
    "Preferences",
    "Cache",
    "GPUCache",
    "GraphiteDawnCache",
    "GPUPersistentCache",
    "IndexedDB",
    "Local Storage",
    "Session Storage",
    "WebStorage",
    "Sessions",
    "Service Worker",
]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".incoming")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.chmod(0o600)
    temporary.replace(path)


def provider(repo, module, *args):
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / repo / "python") + ":" + str(ROOT / "fpl-core/python"),
    }
    result = subprocess.run(
        [
            str(ROOT / repo / ".runtime/venv/bin/python"),
            "-m",
            module + ".cli",
            *map(str, args),
        ],
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(
            repo + " public maintenance failed: " + result.stderr[-1200:]
        )
    return json.loads(result.stdout)


def clone(source, target):
    if target.exists():
        raise ValueError("Destination already exists: " + str(target))
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    subprocess.run(
        ["/bin/cp", "-cRp", str(source), str(target)], check=True, capture_output=True
    )


def published(states, identity, stage, live, backup):
    state = states.get(identity, {})
    return state.get("status") == "switched" or (
        state.get("status") == "switching"
        and not stage.exists()
        and backup.is_dir()
        and (live / ".desktop-migration.json").is_file()
    )


def verify(control, base):
    switches = (
        json.loads((control / "cutovers.json").read_text())
        if (control / "cutovers.json").exists()
        else {}
    )
    output = {}
    for repo, module, _ in PRODUCTS:
        identity = "dsh-" + repo
        live = base / "FPL" / identity
        stage = control / "converted" / identity
        target = (
            live
            if published(
                switches, identity, stage, live, control / "live-before" / identity
            )
            else stage
        )
        if not (target / ".desktop-migration.json").is_file():
            raise ValueError("Provider conversion is not complete: " + repo)
        result = provider(
            repo,
            module,
            "storage-verify",
            "--state-root",
            target,
            "--storage-original-root",
            control / "originals" / identity,
        )
        save(control / (identity + "-verification.json"), result)
        output[identity] = {
            "verified": result["verified"],
            "tables": sum(len(x) for x in result["components"].values()),
            "missing_original": sum(
                t["missing_original"]
                for tables in result["components"].values()
                for t in tables.values()
            ),
        }
    save(control / "verification.json", output)
    return output


def verify_browser_profile(control, identity, before, target):
    report = {"files": 0, "missing": 0, "changed": 0}
    for name in PROFILES:
        source = before / name
        files = (
            [source]
            if source.is_file()
            else source.rglob("*")
            if source.is_dir()
            else []
        )
        for path in files:
            if not path.is_file() or path.is_symlink():
                continue
            report["files"] += 1
            copied = target / path.relative_to(before)
            if not copied.is_file():
                report["missing"] += 1
            elif (
                hashlib.sha256(path.read_bytes()).digest()
                != hashlib.sha256(copied.read_bytes()).digest()
            ):
                report["changed"] += 1
    if report["missing"] or report["changed"]:
        raise ValueError("Browser profile verification failed: " + identity)
    receipt = control / "browser-verification.json"
    reports = json.loads(receipt.read_text()) if receipt.exists() else {}
    reports[identity] = report
    save(receipt, reports)
    return report


def reconcile_owner(control, repo, module, target):
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / repo / "python") + ":" + str(ROOT / "fpl-core/python"),
    }
    result = subprocess.run(
        [
            str(ROOT / repo / ".runtime/venv/bin/python"),
            "-m",
            module + ".desktop_migration",
            "reconcile-owner",
            "--source-state",
            str(control / "originals" / ("dsh-" + repo)),
            "--target",
            str(target),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Provider identity reconciliation failed: " + repo)
    return json.loads(result.stdout)


def reconcile_all(control, base):
    output = {}
    for repo, module, _ in PRODUCTS:
        output[repo] = reconcile_owner(
            control, repo, module, base / "FPL" / ("dsh-" + repo)
        )
    save(control / "owner-verification.json", output)
    return output


def cutover(control, base):
    verify(control, base)
    checkpoint = control / "cutovers.json"
    states = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    for repo, module, _ in PRODUCTS:
        identity = "dsh-" + repo
        if states.get(identity, {}).get("status") == "switched":
            continue
        live = base / "FPL" / identity
        stage = control / "converted" / identity
        backup = control / "live-before" / identity
        if published(states, identity, stage, live, backup):
            # Verification above covers an interrupted checkpoint after the rename.
            states[identity]["status"] = "switched"
            save(checkpoint, states)
            continue
        if not stage.is_dir():
            raise ValueError("Staging directory missing: " + repo)
        if live.exists():
            result = provider(
                repo,
                module,
                "storage-verify",
                "--state-root",
                live,
                "--storage-original-root",
                control / "desktop-before" / identity,
            )
            if any(
                row["before"] != row["after"]
                for tables in result["components"].values()
                for row in tables.values()
            ):
                raise ValueError(
                    "New desktop records require provider merge; no cutover performed: "
                    + repo
                )
        reconcile_owner(control, repo, module, stage)
        before = control / "desktop-before" / identity
        for name in PROFILES:
            if (before / name).exists() and not (stage / name).exists():
                clone(before / name, stage / name)
        verify_browser_profile(control, identity, before, stage)
        prior = json.loads((before / "identity.json").read_text())
        address = urlsplit(prior.get("application_origin") or prior["origin"])
        if address.hostname == "127.0.0.1" and address.port:
            save(
                stage / "desktop-preferences.json", {"version": 1, "port": address.port}
            )
        states[identity] = {
            "status": "switching",
            "target": str(live),
            "backup": str(backup),
            "converted": str(stage),
        }
        save(checkpoint, states)
        backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / repo / "python")
            + ":"
            + str(ROOT / "fpl-core/python"),
        }
        result = subprocess.run(
            [
                str(ROOT / repo / ".runtime/venv/bin/python"),
                "-m",
                module + ".desktop_migration",
                "activate",
                "--staging",
                str(stage),
                "--target",
                str(live),
                "--backup",
                str(backup),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                repo + " provider refused cutover: " + result.stderr[-1000:]
            )
        states[identity]["status"] = "switched"
        save(checkpoint, states)
        print(json.dumps({"product": repo, "cutover": "completed"}), flush=True)
    return verify(control, base)


def restore_models(control, base):
    reports = (
        json.loads((control / "model-verification.json").read_text())
        if (control / "model-verification.json").exists()
        else {}
    )
    for repo, _, _ in PRODUCTS:
        identity = "dsh-" + repo
        live = base / "FPL" / identity
        states = json.loads((control / "cutovers.json").read_text())
        if (
            states.get(identity, {}).get("status") != "switched"
            or not (live / ".desktop-migration.json").is_file()
        ):
            raise ValueError(
                "Publish the verified product before model restoration: " + repo
            )
        root = live / "embedded-core"
        code = (
            "from pathlib import Path; import json; from fpl_core.migration import restore_models; print(json.dumps(restore_models(Path("
            + repr(str(root))
            + "),cache_source=Path("
            + repr(str(control / "originals/core"))
            + "))))"
        )
        env = {**os.environ, "PYTHONPATH": str(ROOT / "fpl-core/python")}
        log = control / (repo + "-models.log")
        print(json.dumps({"product": repo, "models": "restoring"}), flush=True)
        with log.open("a") as stream:
            log.chmod(0o600)
            result = subprocess.run(
                [str(ROOT / repo / ".runtime/venv/bin/python"), "-c", code],
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if result.returncode:
            raise RuntimeError(
                "Model restore did not complete: "
                + repo
                + "; inspect private model log"
            )
        # The public operation writes a summary as its final line.
        lines = log.read_text().splitlines()
        report = json.loads(lines[-1])
        reports[identity] = report
        save(control / "model-verification.json", reports)
        print(
            json.dumps(
                {
                    "product": repo,
                    "models": "verified",
                    "enabled": sum(x["enabled"] for x in report["accounts"]),
                }
            ),
            flush=True,
        )
    return reports


def main():
    global PRODUCTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument(
        "--phase",
        choices=["status", "verify", "cutover", "models", "bindings"],
        default="status",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--product", choices=[x[0] for x in PRODUCTS])
    args = parser.parse_args()
    if args.product:
        PRODUCTS = [x for x in PRODUCTS if x[0] == args.product]
    control = args.control_root.expanduser().resolve()
    base = Path.home() / "Library/Application Support"
    if not (control / "snapshot-receipts.json").is_file():
        raise ValueError("Complete snapshot receipts are required")
    if args.phase == "status":
        print(
            json.dumps(
                {
                    "snapshots": len(
                        json.loads((control / "snapshot-receipts.json").read_text())
                    ),
                    "published": json.loads((control / "cutovers.json").read_text())
                    if (control / "cutovers.json").exists()
                    else {},
                    "converted": [
                        p.name
                        for p in (control / "converted").glob("dsh-*")
                        if (p / ".desktop-migration.json").is_file()
                    ],
                },
                indent=2,
            )
        )
        return
    if not args.execute:
        parser.error("Use --execute for the explicitly selected maintenance phase")
    result = {
        "verify": verify,
        "cutover": cutover,
        "models": restore_models,
        "bindings": reconcile_all,
    }[args.phase](control, base)
    print(json.dumps({"phase": args.phase, "completed": True, "products": len(result)}))


if __name__ == "__main__":
    main()
