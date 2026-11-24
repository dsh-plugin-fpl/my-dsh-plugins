import concurrent.futures
import json
import os
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".local/plugin-managed-setup"


@pytest.mark.twp("protocol-regression.all")
def test_provider_regressions(twp_evidence):
    def check(repo):
        core = repo.name == "dsh-core"
        commands = [[str(repo / (".runtime/worker-venv/bin/python" if core else ".runtime/venv/bin/python")), "-m", "pytest",
            *( ["-c", "python/pyproject.toml", "python/tests"] if core else ["tests"] ), "-q"],
            ["node", "--test", *[str(p.relative_to(repo)) for p in (repo / "tests").glob("*.test.mjs")]]]
        codes = []
        for kind, command in zip(["python", "node"], commands):
            log = OUT / (repo.name + "-" + kind + ".log")
            with log.open("w") as stream:
                result = subprocess.run(command, cwd=repo, env={**os.environ, "PYTHONPATH": str(repo / "python")},
                    stdout=stream, stderr=subprocess.STDOUT, timeout=300)
            codes.append(result.returncode)
        return {"plugin": repo.name, "python": codes[0], "node": codes[1]}
    workspace = subprocess.run(["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_workspace.py", "-q"], cwd=ROOT, capture_output=True, text=True)
    assert workspace.returncode == 0, workspace.stdout + workspace.stderr
    twp_evidence.step("Workspace management: 12 isolated Git regression tests")
    candidates = ROOT / ".runtime/plugin-managed-setup/candidates"
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(check, sorted(candidates.glob("dsh-*"))))
    output = OUT / "regression-summary.json"
    output.write_text(json.dumps(rows, indent=2))
    twp_evidence.attach(output, mime="application/json")
    for log in sorted(OUT.glob("dsh-*-python.log")) + sorted(OUT.glob("dsh-*-node.log")):
        twp_evidence.attach(log, mime="text/plain")
    for row in rows:
        twp_evidence.step(row["plugin"] + " Python and Node regressions", status="passed" if not row["python"] and not row["node"] else "failed")
    assert all(row["python"] == row["node"] == 0 for row in rows), rows
    core = candidates / "dsh-core"
    result = subprocess.run(["node", "node_modules/typescript/bin/tsc", "--noEmit", "--strict", "--skipLibCheck", "--target", "es2023",
        "--module", "nodenext", "--moduleResolution", "nodenext", "examples/consumer.ts"], cwd=core, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    twp_evidence.step("Published Core API consumer compiles independently")
