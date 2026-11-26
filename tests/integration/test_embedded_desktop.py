"""Packaged desktop smoke: real Electron and Python, isolated application state."""

import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(('product_name', 'title'), [
    pytest.param('visual-workshop', '视觉创作工坊', id='visual', marks=pytest.mark.twp('embedded-desktop.visual')),
    pytest.param('video-editor', '视频剪辑工坊', id='video', marks=pytest.mark.twp('embedded-desktop.video')),
    pytest.param('presentation-workshop', '演示工坊', id='presentation', marks=pytest.mark.twp('embedded-desktop.presentation')),
    pytest.param('thought-workshop', '思绪工坊', id='thought', marks=pytest.mark.twp('embedded-desktop.thought')),
    pytest.param('galgame-workshop', 'Galgame 工坊', id='galgame', marks=pytest.mark.twp('embedded-desktop.galgame')),
    pytest.param('audio-annotation', '录音标注工坊', id='audio', marks=pytest.mark.twp('embedded-desktop.audio')),
])
def test_packaged_desktop(product_name, title, request):
    product = ROOT / product_name
    version = json.loads((product / 'desktop/package.json').read_text())['version']
    application = product / '.runtime/desktop' / version / (title + '.app')
    assert application.is_dir(), 'Build the desktop candidate before running acceptance'
    media = application / 'Contents/Resources/media/bin'
    output = product / '.local/desktop-smoke-packaged' / version
    media_output = output / 'media.mp4'
    media_output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(media/'ffmpeg'), '-y', '-f', 'lavfi', '-i', 'color=c=red:s=32x32:r=2',
        '-t', '1', '-c:v', 'libx264', str(media_output)], check=True, capture_output=True,
        env={**os.environ, 'PATH':'/usr/bin:/bin'}, timeout=30)
    probe = subprocess.run([str(media/'ffprobe'), '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=nw=1:nk=1', str(media_output)], check=True, capture_output=True, text=True,
        env={**os.environ,'PATH':'/usr/bin:/bin'}, timeout=30)
    assert float(probe.stdout.strip()) >= 1
    smoke = subprocess.run(['node', str(product / 'tests/desktop-smoke.mjs')], cwd=ROOT,
        env={**os.environ, 'FPL_DESKTOP_APP': str(application),
            'FPL_DESKTOP_TEST_OUTPUT': str(output.relative_to(product))}, capture_output=True, text=True, timeout=120)
    assert smoke.returncode == 0, smoke.stderr[-5000:]
    result = json.loads((output / 'result.json').read_text())
    assert result['passed'] and result['mappedAccountIdsPresent']
    log = (output / 'state/desktop-backend.log').read_text()
    assert 'Application shutdown complete.' in log
    try:
        evidence = request.getfixturevalue('twp_evidence')
    except pytest.FixtureLookupError:
        return
    evidence.step('启动包内 Python 和独立窗口', '产品会话和公共能力会话均已认证')
    evidence.step('打开模型与集成页面', '页面加载且没有脚本错误')
    evidence.step('退出应用', '后端完成正常关闭')
    evidence.step('使用包内 FFmpeg 和 ffprobe', '不依赖 Homebrew PATH 完成合成视频编码与时长检查')
    evidence.step('点击项目导航', '直接进入本工坊项目列表，跳过项目中心')
    evidence.attach(output / 'result.json', mime='application/json')
    for name in ['visual.png', 'models.png', 'integrations.png', 'integrations-dark.png', 'integrations-narrow.png', 'projects.png']:
        evidence.attach(output / name, mime='image/png')
