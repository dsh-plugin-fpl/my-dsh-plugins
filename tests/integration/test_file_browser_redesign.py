"""Real six-product file management and editor selection, on isolated accounts."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS = ["visual-workshop", "video-editor", "presentation-workshop", "thought-workshop", "galgame-workshop", "audio-annotation"]


@pytest.mark.twp("file-browser.rebuild")
@pytest.mark.parametrize("product", PRODUCTS)
def test_file_browser_rebuild(product, request):
    result = subprocess.run(
        ["node", str(ROOT / "scripts/verify-file-browser.mjs"), product],
        cwd=ROOT, capture_output=True, text=True, timeout=240, check=False,
    )
    results = json.loads((ROOT / ".local/file-browser-rebuild/browser-results.json").read_text())
    entry = next(item for item in results if item["product"] == product)
    try:
        evidence = request.getfixturevalue("twp_evidence")
    except pytest.FixtureLookupError:
        evidence = None
    if evidence:
        for step in entry.get("steps", []):
            evidence.step(step["title"], product)
        directory = Path(entry["evidence"])
        evidence.attach(ROOT / ".local/file-browser-rebuild/browser-results.json", mime="application/json")
        for path in directory.glob("*.png"):
            evidence.attach(path, mime="image/png")
        if (directory / "trace.zip").exists():
            evidence.attach(directory / "trace.zip", mime="application/zip")
    assert result.returncode == 0 and entry["passed"], result.stderr[-6000:] or entry.get("error")
