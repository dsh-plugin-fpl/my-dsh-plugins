"""Local recovery and the user-approved six-product UI, with real provider boundaries."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.twp("desktop-recovery.ui")
@pytest.mark.parametrize(
    "product",
    [
        "visual-workshop",
        "video-editor",
        "presentation-workshop",
        "thought-workshop",
        "galgame-workshop",
        "audio-annotation",
    ],
)
def test_updated_desktop_ui(product, request):
    result = subprocess.run(
        ["node", str(ROOT / "tests/desktop_recovery_ui.mjs"), product],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-6000:]
    output = ROOT / product / ".local/desktop-recovery-ui"
    value = json.loads((output / "result.json").read_text())
    assert (
        value["passed"]
        and value["originalCharacter"]
        and not value["errors"]
        and not value["failedAssets"]
    )
    try:
        evidence = request.getfixturevalue("twp_evidence")
    except pytest.FixtureLookupError:
        return
    evidence.step("启动独立桌面候选", "使用隔离账号与数据，包含包内 Python 和 Core")
    evidence.step(
        "检查首页、图像和添加连接菜单",
        "三区入口、原角色素材、两个连接类型及应用设置菜单可用",
    )
    evidence.attach(output / "result.json", mime="application/json")
    for name in [
        "home-light.png",
        "home-dark.png",
        "home-narrow.png",
        "loading.png",
        "connection-menu.png",
        "projects.png",
    ]:
        evidence.attach(output / name, mime="image/png")


@pytest.mark.twp("desktop-recovery.data")
def test_real_migration_receipts(request):
    control = Path.home() / "Library/Application Support/FPL/desktop-recovery-20261127"
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts/recover_desktop_data.py"),
            "--control-root",
            str(control),
            "--phase",
            "verify",
            "--execute",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads((control / "verification.json").read_text())
    assert len(report) == 6 and all(
        x["verified"] and x["missing_original"] == 0 for x in report.values()
    )
    model_file = control / "model-verification.json"
    models = json.loads(model_file.read_text())
    assert len(models) == 6 and all(
        x["restored"] and all(a["enabled"] == a["installed"] for a in x["accounts"])
        for x in models.values()
    )
    browser_file = control / "browser-verification.json"
    browser = json.loads(browser_file.read_text())
    assert len(browser) == 6 and all(
        x["files"] > 0 and x["missing"] == 0 and x["changed"] == 0
        for x in browser.values()
    )
    owners_file = control / "owner-verification.json"
    owners = json.loads(owners_file.read_text())
    assert len(owners) == 6 and all(x["reconciled"] for x in owners.values())
    products = [
        "visual-workshop",
        "video-editor",
        "presentation-workshop",
        "thought-workshop",
        "galgame-workshop",
        "audio-annotation",
    ]
    live = subprocess.run(
        ["node", str(ROOT / "tests/desktop_recovery_data.mjs"), *products],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert live.returncode == 0, live.stderr[-2000:]
    live_file = ROOT / ".local/desktop-recovery-real/results.json"
    visible = json.loads(live_file.read_text())
    assert len(visible) == 6 and all(
        x["passed"] and x["status"] == 200 and x["visible"] > 0
        for x in visible.values()
    )
    try:
        evidence = request.getfixturevalue("twp_evidence")
    except pytest.FixtureLookupError:
        return
    evidence.step(
        "核验六个真实数据目标",
        "提供方逐表检查原始主键、外键和数据库完整性，无原始记录缺失",
    )
    evidence.step("核验本地模型", "所有已启用模型的权重与重建环境通过提供方检查")
    evidence.attach(control / "verification.json", mime="application/json")
    evidence.attach(model_file, mime="application/json")
    evidence.step("核验原桌面缓存", "切换前逐文件校验浏览器配置与缓存，保留原端口来源")
    evidence.attach(browser_file, mime="application/json")
    evidence.step(
        "打开六个真实桌面项目列表", "原账号会话中可见已有项目；不输出项目内容或凭据"
    )
    evidence.attach(live_file, mime="application/json")
    evidence.attach(owners_file, mime="application/json")


@pytest.mark.twp("desktop-recovery.cache-upgrade")
def test_http_cache_upgrade(request):
    result = subprocess.run(
        ["node", str(ROOT / "tests/desktop_cache_upgrade.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    output = ROOT / "audio-annotation/.local/desktop-cache-upgrade/result.json"
    assert all(json.loads(output.read_text()).values())
    try:
        evidence = request.getfixturevalue("twp_evidence")
    except pytest.FixtureLookupError:
        return
    evidence.step(
        "重现旧占位图 HTTP 缓存", "使用保留的旧候选和隔离状态保存占位图与本地数据"
    )
    evidence.step(
        "升级同一状态目录", "新候选加载原素材，localStorage 标记和原账号身份保持"
    )
    evidence.attach(output, mime="application/json")
