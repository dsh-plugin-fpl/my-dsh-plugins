import json
import os
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".local/plugin-managed-setup"


@pytest.mark.twp("independent-workflows.all")
def test_independent_workflows(twp_evidence):
    log = OUT / "workflows.log"
    env = {**os.environ, "WORKSHOPS_WORKSPACE": str(ROOT / ".runtime/plugin-managed-setup/candidates"),
        "WORKSHOPS_TEST_BASE": str(OUT / "workflows"), "WORKSHOPS_UI_SCRIPT": str(ROOT / "scripts/verify-workshops-accounts-ui.mjs")}
    with log.open("w") as stream:
        result = subprocess.run([str(ROOT / "fpl-core/.runtime/worker-venv/bin/python"), str(ROOT / "scripts/verify_workshops_accounts.py")],
            cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=500)
    twp_evidence.attach(log, mime="text/plain")
    assert result.returncode == 0, log.read_text()[-3000:]
    text = log.read_text()
    for line in text.splitlines():
        if line.endswith("OK") or line == "SEVEN_SERVICE_UI_PASSED":
            twp_evidence.step(line)
    directory = Path(next(line[5:] for line in text.splitlines() if line.startswith("PASS ")))
    ui = directory / "ui-result.json"
    rows = json.loads(ui.read_text())
    assert len(rows) == 7 and all(not row["errors"] and not row["failed"] for row in rows)
    twp_evidence.attach(ui, mime="application/json")
    for path in sorted(directory.glob("*-editor-*.png")):
        twp_evidence.attach(path, mime="image/png")
