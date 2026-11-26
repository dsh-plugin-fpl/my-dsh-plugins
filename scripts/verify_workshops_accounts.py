"""Seven real processes exercised only through public CLI/HTTP/WS and Core's documented fixture."""

import asyncio, io, json, os, socket, subprocess, time, wave
from contextlib import AsyncExitStack
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
import httpx

BASE = Path(os.environ.get("WORKSHOPS_WORKSPACE", Path(__file__).resolve().parents[1]))
CORE = Path(os.environ.get("WORKSHOPS_CORE_REPO", BASE / "fpl-core"))
APPS = [
    [
        "presentation_workshop",
        "presentation",
        "Presentation",
        "演示工坊",
        "fpl_presentation",
        9362,
    ],
    ["thought_workshop", "thought", "Thought", "思绪工坊", "fpl_thought", 9363],
    ["galgame_workshop", "galgame", "Galgame", "Galgame 工坊", "fpl_galgame", 9364],
    [
        "audio_annotation",
        "annotation",
        "Annotation",
        "录音标注工坊",
        "fpl_annotation",
        9365,
    ],
    ["visual_workshop", "visual", "Visual", "视觉创作工坊", "fpl_visual", 9360],
    ["video_editor", "video", "Video", "视频剪辑工坊", "fpl_video", 9361],
]
TASK = Path(os.environ.get("WORKSHOPS_TEST_BASE", BASE / ".local/workshops-accounts"))
subprocess.run(
    ["git", "check-ignore", str(TASK)], cwd=BASE, check=True, stdout=subprocess.DEVNULL
)
TASK.mkdir(exist_ok=True, parents=True)


def private_json(path, value):
    with path.open("x") as file:
        json.dump(value, file, ensure_ascii=False)
    path.chmod(0o600)


async def command(args, cwd):
    process = await asyncio.create_subprocess_exec(
        *map(str, args),
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(Path(cwd) / "python")},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    output, error = await process.communicate()
    if process.returncode:
        raise RuntimeError("Fixture CLI failed: " + error.decode()[-1800:])


async def process(args, cwd, log, stack):
    file = log.open("w")
    log.chmod(0o600)
    process = await asyncio.create_subprocess_exec(
        *map(str, args), cwd=cwd, env={**os.environ, "PYTHONPATH": str(Path(cwd) / "python")}, stdout=file, stderr=asyncio.subprocess.STDOUT
    )

    async def stop():
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 15)
        finally:
            file.close()

    stack.push_async_callback(stop)


async def wait_ready(port, path="/ready"):
    async with httpx.AsyncClient(trust_env=False) as client:
        for _ in range(200):
            try:
                response = await client.get(f"http://127.0.0.1:{port}" + path)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.1)
    raise RuntimeError("Isolated service readiness timeout: " + str(port))


def client(port):
    return httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}",
        headers={"Origin": f"http://127.0.0.1:{port}"},
        trust_env=False,
        timeout=90,
    )


async def check(response, code=200):
    if response.status_code != code:
        raise AssertionError(
            f"{response.request.method} {response.request.url.path}: {response.status_code}: {response.text[:1200]}"
        )
    return (
        response.json()
        if response.headers.get("content-type", "").startswith("application/json")
        else response
    )


async def login(core, appclient, slug):
    challenge = await check(await appclient.post("/v1/app/login"))
    query = parse_qs(urlsplit(challenge["url"]).query)
    authorized = await core.get(
        "/v1/identity/authorize", params={k: v[0] for k, v in query.items()}
    )
    assert authorized.status_code == 303, authorized.text
    fragment = parse_qs(urlsplit(authorized.headers["location"]).fragment)
    await check(
        await appclient.post(
            "/v1/app/session",
            json={"ticket": fragment["code"][0], "state": fragment["state"][0]},
        )
    )
    appclient.headers["X-CSRF-Token"] = appclient.cookies[
        slug.replace("-", "_") + "_csrf"
    ]
    return await check(await appclient.get("/v1/auth/me"))


async def main():
    for port in [19310, *range(19362, 19368)]:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("Test port already in use: " + str(port))
    # Every run gets a new state directory. Never adopt or clear a previous run.
    root = TASK / str(time.time_ns())
    root.mkdir()
    async with AsyncExitStack() as stack:
        await process(
            [
                str(CORE / ".runtime/worker-venv/bin/python"),
                "tests/fixtures/server.py",
                "--root",
                str(root / "core"),
                "--port",
                "19310",
                "--mock-models",
                "--mock-model-delay",
                "1.0",
                "--mock-external",
                "--web-root",
                str(CORE / "web/dist"),
            ],
            CORE,
            root / "core.log",
            stack,
        )
        await wait_ready(19310, "/health")
        owner = await stack.enter_async_context(client(19310))
        signed = await check(
            await owner.post(
                "/v1/session",
                json={"ticket": (root / "core/fixture-launch.txt").read_text()},
            )
        )
        owner.headers["X-Core-CSRF"] = signed["csrf"]
        other = await check(
            await owner.post(
                "/v1/identity/accounts",
                json={
                    "username": "reader-one",
                    "display_name": "第二账号",
                    "password": "isolated-password-123",
                },
            )
        )
        second = await stack.enter_async_context(client(19310))
        value = await check(
            await second.post(
                "/v1/identity/login",
                json={"username": "reader-one", "password": "isolated-password-123"},
            )
        )
        second.headers["X-Core-CSRF"] = value["csrf"]
        await check(await second.get("/v1/identity/accounts"), 403)
        apps = []
        for index, (appname, service, entry, title, pkg, _port) in enumerate(APPS):
            slug = "dsh-" + appname.replace("_", "-")
            repo = BASE / appname.replace("_", "-")
            state = root / slug
            port = 19362 + index
            await command(
                [
                    str(repo / ".runtime/venv/bin/python"),
                    "-m",
                    pkg + ".cli",
                    "init",
                    "--state-root",
                    str(state),
                    "--port",
                    str(port),
                ],
                repo,
            )
            descriptor = root / (slug + "-launch.json")
            private_json(descriptor, await check(await owner.post("/_fixture/launch")))
            await command(
                [
                    str(repo / ".runtime/venv/bin/python"),
                    "-m",
                    pkg + ".cli",
                    "connect-core",
                    "--state-root",
                    str(state),
                    "--port",
                    str(port),
                    "--launch-file",
                    str(descriptor),
                ],
                repo,
            )
            await process(
                [
                    str(repo / ".runtime/venv/bin/python"),
                    "-m",
                    pkg + ".cli",
                    "serve",
                    "--state-root",
                    str(state),
                    "--port",
                    str(port),
                ],
                repo,
                root / (slug + ".log"),
                stack,
            )
            await wait_ready(port)
            gateway = None
            first = await stack.enter_async_context(client(port))
            another = await stack.enter_async_context(client(port))
            profile = await login(owner, first, slug)
            profile2 = await login(second, another, slug)
            assert profile["user"]["id"] != profile2["user"]["id"]
            await check(await first.get("/ready"))
            apps.append((slug, gateway, first, another))
            print(title, "Core SSO and independent readiness OK", flush=True)
            credential = json.loads((state / "plugin.json").read_text())
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}",
                headers={"Authorization": "Bearer " + credential["token"]},
                trust_env=False,
            ) as plugin:
                await check(
                    await plugin.get(
                        "/v1/"
                        + appname.replace("_", "-")
                        + ("/knowledge-bases" if service == "thought" else "/projects")
                    )
                )

        for slug, gateway, first, another in apps[4:]:
            prefix = "/v1/" + (
                "visual-workshop" if slug == "dsh-visual-workshop" else "video-editor"
            )
            body = {"title": "原工坊统一身份验收"}
            if slug == "dsh-visual-workshop":
                body["kind"] = "canvas"
            created = await check(await first.post(prefix + "/projects", json=body))
            await check(await another.get(prefix + "/projects/" + created["id"]), 404)
            print(slug, "legacy owner projection and account isolation OK", flush=True)
        # Only the provider wire is replaced; task persistence, resources and real Core WebSocket remain active.
        provider = await check(
            await owner.post(
                "/v1/model-providers",
                json={
                    "name": "Isolated provider",
                    "kind": "openai",
                    "base_url": "https://api.example.com",
                    "api_key": "fixture-only-secret",
                    "expected_catalog_revision": 0,
                },
            )
        )
        provider = provider["provider"]
        chat = await check(
            await owner.post(
                "/v1/model-providers/" + provider["id"] + "/models",
                json={
                    "slug": "fixture-chat",
                    "label": "隔离写作模型",
                    "capabilities": ["chat"],
                    "categories": [],
                    "enabled": True,
                    "expected_catalog_revision": 1,
                },
            )
        )
        chat = chat["model"]
        speech = await check(
            await owner.post(
                "/v1/model-providers/" + provider["id"] + "/models",
                json={
                    "slug": "fixture-asr",
                    "label": "隔离识别模型",
                    "capabilities": ["speech_recognition"],
                    "categories": [],
                    "enabled": True,
                    "expected_catalog_revision": 2,
                },
            )
        )
        speech = speech["model"]
        remote = await check(await owner.get("/_fixture/external"))
        # Presentation edit, native export and account isolation.
        _, presentation, first, another = apps[0]
        created = await check(
            await first.post(
                "/v1/presentation-workshop/projects",
                json={
                    "title": "独立演示验收",
                    "document": {
                        "version": 5,
                        "width": 1280,
                        "height": 720,
                        "slides": [
                            {
                                "id": "slide-one",
                                "background": "#FFFFFF",
                                "notes": "",
                                "elements": [],
                            }
                        ],
                    },
                },
            )
        )
        pid = created["id"]
        await check(await another.get("/v1/presentation-workshop/projects/" + pid), 404)
        exported = await check(
            await first.post(
                "/v1/presentation-workshop/projects/" + pid + "/export",
                json={"expected_revision": created["revision"]},
            )
        )
        assert exported.content[:2] == b"PK"
        print("Presentation native PPTX export OK", flush=True)
        # Thought private knowledge, directory and community listing.
        _, thought, first, another = apps[1]
        created = await check(
            await first.post(
                "/v1/thought-workshop/knowledge-bases", json={"title": "独立知识库验收"}
            )
        )
        kid = created["id"]
        await check(
            await another.get("/v1/thought-workshop/knowledge-bases/" + kid), 404
        )
        await check(await first.get("/v1/thought-workshop/community/publications"))
        await check(await first.get("/v1/integrations/external-connections"))
        print(
            "Thought private ownership, community and Core integrations catalog OK",
            flush=True,
        )
        models = await check(await first.get("/v1/thought-workshop/models"))
        assert chat["id"] in {model["id"] for model in models}
        home = await check(
            await first.get("/v1/thought-workshop/notes/" + created["home_note_id"])
        )
        home = await check(
            await first.put(
                "/v1/thought-workshop/notes/" + home["id"],
                json={
                    **{
                        k: home[k]
                        for k in (
                            "title",
                            "knowledge_base_id",
                            "parent_id",
                            "schema_version",
                            "tags",
                            "favorite",
                            "pinned",
                        )
                    },
                    "document": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "验证完整写作链路"}
                                ],
                            }
                        ],
                    },
                    "expected_revision": home["revision"],
                },
            )
        )
        writing_url = "/v1/thought-workshop/notes/" + home["id"] + "/assistant"
        writing_body = {
            "expected_revision": home["revision"],
            "model_id": chat["id"],
            "action": "summary",
            "selection": "验证完整写作链路",
        }
        before = {
            row["id"] for row in (await check(await owner.get("/v1/tasks")))["items"]
        }
        lines = []
        async with first.stream("POST", writing_url, json=writing_body) as written:
            assert written.status_code == 200
            inspected = False
            async for line in written.aiter_lines():
                lines.append(line)
                if '"delta"' in line and not inspected:
                    tasks = (await check(await owner.get("/v1/tasks")))["items"]
                    new = [row for row in tasks if row["id"] not in before]
                    assert len(new) == 1 and new[0]["status"] in {
                        "running",
                        "processing",
                    }, new
                    inspected = True
        events = [json.loads(line[5:]) for line in lines if line.startswith("data:")]
        assert inspected and "Core 测试回复" in "".join(
            event.get("text", "") for event in events
        ), events
        assert "complete" in "".join(lines), lines
        before = {
            row["id"] for row in (await check(await owner.get("/v1/tasks")))["items"]
        }
        async with first.stream("POST", writing_url, json=writing_body) as cancelled:
            assert cancelled.status_code == 200
            async for line in cancelled.aiter_lines():
                if '"delta"' in line:
                    break
        for _ in range(60):
            tasks = (await check(await owner.get("/v1/tasks")))["items"]
            new = [row for row in tasks if row["id"] not in before]
            if len(new) == 1 and new[0]["status"] == "cancelled":
                break
            await asyncio.sleep(0.05)
        assert len(new) == 1 and new[0]["status"] == "cancelled", new
        print(
            "Thought incremental writing and disconnect cancellation through real Core OK",
            flush=True,
        )
        conn = await check(
            await owner.post(
                "/v1/integrations/external-connections",
                json={
                    "name": "Isolated Feishu",
                    "provider": "feishu",
                    "app_id": "fixture-app",
                    "app_secret": "fixture-secret",
                    "enabled": True,
                },
            ),
            201,
        )
        prefix = "/v1/thought-workshop/notes/" + home["id"] + "/external-sync"
        bound = await check(
            await first.put(
                prefix + "/binding",
                json={
                    "connection_id": conn["id"],
                    "url": remote["url"],
                    "expected_revision": 0,
                },
            )
        )
        print("Thought Feishu binding through public Core authorization OK", flush=True)
        preview = await check(
            await first.post(
                prefix + "/preview",
                json={
                    "expected_revision": home["revision"],
                    "binding_revision": bound["revision"],
                },
            )
        )
        submission = {
            "preview_id": preview["preview_id"],
            "operation_id": str(uuid4()),
            "confirm_replace": True,
        }
        sync = await check(await first.post(prefix + "/tasks", json=submission), 202)
        replay = await check(await first.post(prefix + "/tasks", json=submission), 202)
        assert sync["id"] == replay["id"]
        for _ in range(180):
            sync = await check(await first.get(prefix + "/tasks/" + sync["id"]))
            if sync["status"] in {"succeeded", "failed", "needs_review", "conflict"}:
                break
            await asyncio.sleep(0.2)
        assert sync["status"] == "succeeded", sync
        assert (await check(await owner.get("/_fixture/external")))["writes"] == [
            "append",
            "delete",
        ]
        print("Thought Feishu full durable write, replay and closure OK", flush=True)
        published = await check(
            await first.put(
                "/v1/thought-workshop/community/libraries/" + kid + "/publication",
                json={
                    "expected_revision": 0,
                    "title": "逐篇授权验收",
                    "active": True,
                    "read_only": False,
                    "articles": [
                        {
                            "note_id": home["id"],
                            "expected_revision": 0,
                            "visibility": "members",
                            "members": [{"username": "reader-one", "role": "read"}],
                        }
                    ],
                },
            )
        )
        publication = published["publication"]["id"]
        community = "/v1/thought-workshop/community/publications/" + publication
        await check(await another.get(community + "/notes/" + home["id"]))
        await check(await another.get("/v1/thought-workshop/notes/" + home["id"]), 404)
        setting = published["articles"][0]
        await check(
            await first.put(
                community + "/permissions",
                json={
                    "articles": [
                        {
                            "note_id": home["id"],
                            "expected_revision": setting["revision"],
                            "visibility": "members",
                            "members": [],
                        }
                    ]
                },
            )
        )
        await check(await another.get(community + "/notes/" + home["id"]), 404)
        package = await check(
            await first.get("/v1/thought-workshop/community/official-import/preview")
        )
        await check(
            await another.get("/v1/thought-workshop/community/official-import/preview"),
            403,
        )
        imported = await check(
            await first.post(
                "/v1/thought-workshop/community/official-import",
                json={
                    "request_id": str(uuid4()),
                    "package_version": package["package_version"],
                },
            )
        )
        assert len(imported["knowledge_base_ids"]) == package["library_count"]
        print(
            "Thought per-article membership, revoke and explicit official import OK",
            flush=True,
        )
        # Galgame story initialization and ownership.
        _, galgame, first, another = apps[2]
        created = await check(
            await first.post(
                "/v1/galgame-workshop/projects", json={"title": "独立分支验收"}
            )
        )
        gid = created["id"]
        await check(await first.get("/v1/galgame-workshop/projects/" + gid + "/story"))
        await check(
            await another.get("/v1/galgame-workshop/projects/" + gid + "/story"), 404
        )
        await check(await first.get("/v1/model-test/transcription-options"))
        print("Galgame story and account isolation OK", flush=True)
        # Annotation imports real WAV bytes through its own Assets component.
        _, annotation, first, another = apps[3]
        data = io.BytesIO()
        with wave.open(data, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(bytes(16000))
        asset = await check(
            await first.post(
                "/v1/files",
                files={"upload": ("recording.wav", data.getvalue(), "audio/wav")},
            )
        )
        created = await check(
            await first.post(
                "/v1/audio-annotation/projects",
                json={"title": "独立标注验收", "asset_id": asset["id"]},
            )
        )
        aid = created["id"]
        await check(
            await first.get("/v1/audio-annotation/projects/" + aid + "/document")
        )
        await check(
            await another.get("/v1/audio-annotation/projects/" + aid + "/document"), 404
        )
        await check(await first.get("/v1/model-test/transcription-options"))
        print("Annotation real WAV import and private document OK", flush=True)
        recognized = await check(
            await first.post(
                "/v1/audio-annotation/projects/" + aid + "/segment-transcriptions",
                data={
                    "model_id": speech["id"],
                    "segment_id": "segment-one",
                    "start_ms": "0",
                    "end_ms": "1000",
                    "language_tag": "zh",
                },
                files={"upload": ("segment.wav", data.getvalue(), "audio/wav")},
            )
        )
        assert recognized["text"] == "隔离模型验收结果", recognized
        print("Annotation real resource upload and Core ASR task OK", flush=True)
        galgame_client = apps[2][2]
        asr_prefix = "/v1/galgame-workshop/projects/" + gid + "/assets"
        voice = await check(
            await galgame_client.post(
                asr_prefix,
                data={"category": "voice"},
                files={"upload": ("voice.wav", data.getvalue(), "audio/wav")},
            )
        )
        settings = await check(await galgame_client.get(asr_prefix + "/asr/settings"))
        settings = await check(
            await galgame_client.patch(
                asr_prefix + "/asr/settings",
                json={
                    "expectedRevision": settings["revision"],
                    "modelId": speech["id"],
                    "defaultLanguage": "zh",
                },
            )
        )
        assert settings["modelReady"] is True, settings
        submitted = await check(
            await galgame_client.post(
                asr_prefix + "/asr/transcriptions", json={"assetIds": [voice["id"]]}
            )
        )
        assert len(submitted["items"]) == 1, submitted
        for _ in range(180):
            tasks = await check(
                await galgame_client.get(asr_prefix + "/asr/transcriptions")
            )
            task = next(
                row
                for row in tasks["items"]
                if row["id"] == submitted["items"][0]["id"]
            )
            if task["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.2)
        assert (
            task["status"] == "completed" and task["resultText"] == "隔离模型验收结果"
        ), task
        print(
            "Galgame WAV, live model settings and durable Core ASR receipt OK",
            flush=True,
        )

        # The actual annotation gateway crosses to Galgame through Core-issued account grants.
        first, another = apps[3][2:]
        linked = await check(await first.get("/v1/galgame-workshop/projects"))
        assert gid in {item["id"] for item in linked["items"]}
        await check(
            await another.get("/v1/galgame-workshop/projects/" + gid + "/story"), 404
        )
        print(
            "Core-issued cross-app read, byte forwarding and account isolation OK",
            flush=True,
        )
        visual, video = apps[4][2], apps[5][2]
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
        media = root / "source.mp4"
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
            task = next(row for row in response.json()["items"] if row["id"] == task_id)
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
        print(
            "Video FFmpeg segments and Core-authorized immutable transfer OK",
            flush=True,
        )

        # Browser and tarball hooks receive only private, disposable fixture state.
        def cookies(client):
            return [
                {
                    "name": item.name,
                    "value": item.value,
                    "domain": "127.0.0.1",
                    "path": item.path,
                    "httpOnly": item.name.endswith("_session"),
                    "sameSite": "Lax",
                }
                for item in client.cookies.jar
            ]

        browser_apps = []
        project_paths = [
            f"/apps/presentation-workshop/projects/{pid}",
            f"/apps/thought-workshop/knowledge-bases/{kid}/documents/{home['id']}",
            f"/apps/galgame-workshop/projects/{gid}/editor",
            f"/apps/audio-annotation/projects/{aid}",
            f"/apps/visual-workshop/projects/{target_id}/canvas",
            f"/apps/video-editor/projects/{project_id}/editor",
        ]
        for index, (slug, _, first, _) in enumerate(apps):
            browser_apps.append(
                {
                    "slug": slug,
                    "port": 19362 + index,
                    "route": "/apps/" + slug[4:],
                    "editor": project_paths[index],
                    "cookies": cookies(owner) + cookies(first),
                }
            )
        private_json(
            root / "browser-state.json",
            {"core_cookies": cookies(owner), "apps": browser_apps},
        )
        for variable in ["WORKSHOPS_UI_SCRIPT", "WORKSHOPS_HARNESS_SCRIPT"]:
            if os.environ.get(variable):
                child = await asyncio.create_subprocess_exec(
                    "node",
                    os.environ[variable],
                    cwd=BASE,
                    env={
                        **os.environ,
                        "WORKSHOPS_TEST_ROOT": str(root),
                        "WORKSHOPS_CORE_REPO": str(CORE),
                    },
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out, err = await child.communicate()
                if child.returncode:
                    raise RuntimeError(variable + ": " + (out + err).decode()[-4000:])
                print(out.decode().strip(), flush=True)
        report = {"status": "passed", "apps": [x[0] for x in apps], "root": str(root)}
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        print("PASS", root, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
