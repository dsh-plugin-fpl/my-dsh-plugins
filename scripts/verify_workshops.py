"""Exercise independent application processes only through CLI and public HTTP."""

import asyncio
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

BASE = Path(__file__).resolve().parents[1]
TASK = BASE / ".local/workshops-integration" / str(time.time_ns())
subprocess.run(
    ["git", "check-ignore", str(TASK)], cwd=BASE, check=True, stdout=subprocess.DEVNULL
)
TASK.mkdir(parents=True)

APPS = [
    ("dsh-visual-workshop", "fpl_visual", 19360),
    ("dsh-video-editor", "fpl_video", 19361),
]


def cli(index, command, *args):
    slug, pkg, port = APPS[index]
    repo = BASE / slug
    state = TASK / slug
    result = subprocess.run(
        [
            str(repo / ".runtime/venv/bin/python"),
            "-m",
            pkg + ".cli",
            command,
            "--state-root",
            str(state),
            "--port",
            str(port),
            *map(str, args),
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-2500:])
    return result


async def client(index):
    slug, _pkg, port = APPS[index]
    output = TASK / (slug + "-launch.json")
    cli(index, "open", "--no-open", "--output", output)
    token = parse_qs(urlsplit(json.loads(output.read_text())["url"]).fragment)[
        "ticket"
    ][0]
    api = httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}",
        headers={"Origin": f"http://127.0.0.1:{port}"},
        trust_env=False,
        timeout=60,
    )
    response = await api.post("/v1/app/session", json={"ticket": token})
    assert response.status_code == 200, response.text
    api.headers["X-CSRF-Token"] = api.cookies[slug.replace("-", "_") + "_csrf"]
    return api


async def main():
    for port in (19310, 19360, 19361, 19362):
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(
                    f"Isolated test port {port} is already occupied; no service was stopped."
                )
    processes = []
    logs = []
    try:
        core_root = TASK / "core-catalog-v031"
        core_log = (TASK / "core.log").open("w")
        logs.append(core_log)
        core_repo = BASE / "dsh-core"
        core = subprocess.Popen(
            [
                str(core_repo / ".runtime/worker-venv/bin/python"),
                "tests/fixtures/server.py",
                "--root",
                str(core_root),
                "--port",
                "19310",
                "--mock-models",
            ],
            cwd=core_repo,
            stdout=core_log,
            stderr=subprocess.STDOUT,
        )
        processes.append(core)
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:19310",
            trust_env=False,
            headers={"Origin": "http://127.0.0.1:19310"},
        ) as core_api:
            for _ in range(100):
                try:
                    if (await core_api.get("/health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.2)
            ticket = (core_root / "fixture-launch.txt").read_text()
            login = await core_api.post("/v1/session", json={"ticket": ticket})
            assert login.status_code == 200, login.text
            core_api.headers["X-Core-CSRF"] = login.json()["csrf"]
            core_cookies = dict(core_api.cookies)
            providers = (await core_api.get("/v1/model-providers")).json()
            if not providers["providers"]:
                provider = await core_api.post(
                    "/v1/model-providers",
                    json={
                        "name": "迁移验收隔离模型",
                        "kind": "volcengine_image",
                        "base_url": "https://api.example.com",
                        "api_key": "isolated-test-not-a-real-secret",
                        "expected_catalog_revision": 0,
                    },
                )
                assert provider.status_code == 200, provider.text
                provider = provider.json()["provider"]
                model = await core_api.post(
                    "/v1/model-providers/" + provider["id"] + "/models",
                    json={
                        "slug": "doubao-seedream-4-5-251128",
                        "label": "隔离图片模型",
                        "capabilities": ["image_generation"],
                        "categories": [],
                        "enabled": True,
                        "expected_catalog_revision": 1,
                    },
                )
                assert model.status_code == 200, model.text
            pair = await core_api.post(
                "/v1/bridges", json={"name": "视觉创作独立服务验收"}
            )
            assert pair.status_code == 200, pair.text
            pair_file = TASK / "visual-core-pair.json"
            pair_file.write_text(json.dumps(pair.json()))
            pair_file.chmod(0o600)
        for i, (slug, pkg, port) in enumerate(APPS):
            cli(i, "init")
            log = (TASK / (slug + ".log")).open("w")
            logs.append(log)
            process = subprocess.Popen(
                [
                    str(BASE / slug / ".runtime/venv/bin/python"),
                    "-m",
                    pkg + ".cli",
                    "serve",
                    "--state-root",
                    str(TASK / slug),
                    "--port",
                    str(port),
                ],
                cwd=BASE / slug,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            processes.append(process)
        async with httpx.AsyncClient(trust_env=False) as probe:
            for slug, pkg, port in APPS:
                for _ in range(100):
                    try:
                        response = await probe.get(f"http://127.0.0.1:{port}/ready")
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.2)
                else:
                    raise RuntimeError("service_not_ready: " + slug)
        cli(
            0,
            "connect-core",
            "--pair-file",
            pair_file,
            "--core-origin",
            "http://127.0.0.1:19310",
        )
        invitation = TASK / "visual-pairing.json"
        cli(0, "pair-invitation", "--output", invitation)
        cli(1, "link-app", "--launch-file", invitation)
        visual, video = await client(0), await client(1)
        try:
            target = await visual.post(
                "/v1/visual-workshop/projects",
                json={"title": "跨工坊目标画布", "kind": "canvas"},
            )
            assert target.status_code == 200, target.text
            target_id = target.json()["id"]
            project = await video.post(
                "/v1/video-editor/projects", json={"title": "真实片段交接"}
            )
            assert project.status_code == 200, project.text
            project_id = project.json()["id"]
            prefix = "/v1/video-editor/projects/" + project_id
            media = TASK / "source.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=red:s=64x64:r=30:d=0.5",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-threads",
                    "1",
                    str(media),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            response = await video.post(
                prefix + "/assets",
                files={"upload": ("source.mp4", media.read_bytes(), "video/mp4")},
            )
            assert response.status_code == 200, response.text
            asset_id = response.json()["id"]
            for _ in range(100):
                assets = (await video.get(prefix + "/assets")).json()["items"]
                asset = next(a for a in assets if a["id"] == asset_id)
                if asset["processingStatus"] == "ready":
                    break
                if asset["processingStatus"] == "failed":
                    raise RuntimeError(str(asset))
                await asyncio.sleep(0.2)
            else:
                raise RuntimeError("asset_processing_timeout")
            response = await video.post(
                prefix + "/timeline/operations",
                json={
                    "expectedRevision": 0,
                    "requestId": "segment-test-seed",
                    "operations": [
                        {
                            "type": "addClip",
                            "clip": {
                                "id": "clip-1",
                                "name": "红色视频",
                                "trackId": "visual-1",
                                "kind": "video",
                                "assetId": asset_id,
                                "timelineStartUs": 0,
                                "sourceInUs": 0,
                                "durationUs": 200000,
                                "playbackRate": 1,
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 200, response.text
            response = await video.post(
                prefix + "/segment-exports",
                json={
                    "expectedRevision": 1,
                    "requestId": "segment-test-export",
                    "target": {"projectId": target_id},
                    "segments": [
                        {
                            "clipId": "clip-1",
                            "name": "红色片段",
                            "resolution": "source",
                            "fps": "source",
                            "audioMode": "mute",
                        }
                    ],
                },
            )
            assert response.status_code == 200, response.text
            task_id = response.json()["id"]
            for _ in range(150):
                response = await video.get(prefix + "/segment-exports")
                assert response.status_code == 200, response.text
                task = next(
                    row for row in response.json()["items"] if row["id"] == task_id
                )
                if task["status"] == "completed":
                    break
                if task["status"] in {"failed", "cancelled"}:
                    raise RuntimeError(str(task))
                await asyncio.sleep(0.2)
            else:
                raise RuntimeError("segment_handoff_timeout: " + str(task))
            canvas = await visual.get(
                "/v1/visual-workshop/projects/" + target_id + "/canvas"
            )
            assert canvas.status_code == 200, canvas.text
            nodes = canvas.json()["nodes"]
            assert len(nodes) == 1, nodes
            assert nodes[0]["kind"] == "video", nodes
            content = await visual.get("/v1/files/" + nodes[0]["asset_id"] + "/content")
            assert content.status_code == 200, content.text[:1000]
            assert b"ftyp" in content.content[:16]
            for _ in range(100):
                options = await visual.get("/v1/visual-workshop/generation-options")
                if options.status_code == 200 and options.json()["models"]:
                    break
                await asyncio.sleep(0.2)
            else:
                raise RuntimeError("Core_model_catalog_unavailable: " + options.text)
            response = await visual.post(
                "/v1/visual-workshop/projects/" + target_id + "/generation-tasks",
                json={
                    "kind": "image",
                    "model_id": options.json()["models"][0]["id"],
                    "prompt": "独立服务生成验收",
                    "size": options.json()["models"][0]["sizes"][0],
                },
            )
            assert response.status_code == 200, response.text
            for _ in range(150):
                generated = (
                    await visual.get(
                        "/v1/visual-workshop/projects/" + target_id + "/canvas"
                    )
                ).json()
                if any(node["kind"] == "image" for node in generated["nodes"]):
                    break
                await asyncio.sleep(0.2)
            else:
                source_tasks = (
                    await visual.get("/v1/visual-workshop/generation-tasks")
                ).json()
                async with httpx.AsyncClient(
                    base_url="http://127.0.0.1:19310",
                    trust_env=False,
                    cookies=core_cookies,
                ) as debug:
                    core_tasks = (await debug.get("/v1/tasks")).json()
                raise RuntimeError(
                    "Core_generation_not_published: "
                    + json.dumps(
                        {"visual": source_tasks, "core": core_tasks}, ensure_ascii=False
                    )
                )
            report = {
                "real_Core_bridge_generation": True,
                "project_creation": True,
                "actual_ffmpeg_video_import": True,
                "paired_target_revision": True,
                "segment_handoff": True,
                "target_media_readable": True,
                "target_canvas_revision": canvas.json()["revision"],
            }
            environment = {
                **os.environ,
                "WORKSHOPS_WORKSPACE": str(BASE),
                "WORKSHOPS_TEST_ROOT": str(TASK),
            }
            harness = await asyncio.create_subprocess_exec(
                "node",
                str(BASE / "scripts/verify-workshops-harness.mjs"),
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            async with httpx.AsyncClient(
                base_url="http://127.0.0.1:19310", trust_env=False, cookies=core_cookies
            ) as dashboard:
                for _ in range(600):
                    entries = (await dashboard.get("/v1/applications")).json()["items"]
                    apps = [
                        row
                        for row in entries
                        if row.get("package_name")
                        in {
                            "@dsh-plugin-fpl/dsh-visual-workshop",
                            "@dsh-plugin-fpl/dsh-video-editor",
                        }
                        and row["status"] == "ready"
                    ]
                    if len(apps) == 2:
                        break
                    if harness.returncode is not None:
                        raise RuntimeError(
                            (await harness.stderr.read()).decode()[-2000:]
                        )
                    await asyncio.sleep(0.2)
                else:
                    raise RuntimeError("Harness applications registration timed out")
                for entry in apps:
                    assert (await dashboard.get(entry["url"])).status_code == 200
                    assert (await dashboard.get(entry["icon_url"])).status_code == 200
            stdout, stderr = await harness.communicate()
            if harness.returncode:
                raise RuntimeError(stderr.decode()[-2000:])
            report["packaged_Harness_registration"] = True
            report["services_survive_Harness_stop"] = True
            for index, (slug, pkg, port) in enumerate(APPS):
                cli(
                    index,
                    "open",
                    "--no-open",
                    "--output",
                    TASK / (slug + "-browser.json"),
                )
            ui = await asyncio.create_subprocess_exec(
                "node",
                str(BASE / "scripts/verify-workshops-ui.mjs"),
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await ui.communicate()
            if ui.returncode:
                raise RuntimeError(stderr.decode()[-4000:])
            report["browser_UI_light_dark_wide_narrow"] = True
            (TASK / "result.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report))
        finally:
            await visual.aclose()
            await video.aclose()
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()


print("Evidence:", TASK)
asyncio.run(main())
