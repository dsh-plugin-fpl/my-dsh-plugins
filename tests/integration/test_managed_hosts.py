import asyncio
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
module = importlib.util.spec_from_file_location("managed_acceptance", ROOT / "scripts/verify_managed_plugins.py")
runner = importlib.util.module_from_spec(module)
module.loader.exec_module(runner)


def exercise(version, twp_evidence):
    matrix = json.loads((ROOT / ".local/plugin-managed-setup/harness-matrix.json").read_text())
    host = runner.Host(next(row for row in matrix if row["version"] == version))
    try:
        asyncio.run(host.run())
    finally:
        for step in host.steps:
            twp_evidence.step(step["title"], status=step["status"])
        report = host.control / "report.json"
        if report.exists():
            twp_evidence.attach(report, mime="application/json")
        for screenshot in host.control.glob("*.png"):
            twp_evidence.attach(screenshot, mime="image/png")


@pytest.mark.twp("managed-setup.current")
def test_current_host(twp_evidence):
    exercise("0.2.2-rc.1", twp_evidence)


@pytest.mark.twp("managed-setup.next")
def test_next_host(twp_evidence):
    exercise("0.2.2-rc.5", twp_evidence)
