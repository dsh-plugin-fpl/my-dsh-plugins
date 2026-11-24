"""Exercise packed plugins through two real Harness releases in disposable profiles."""
import argparse
import asyncio
import json
import os
import re
import io
import base64
import shutil
import time
import wave
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local/plugin-managed-setup"


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False))
    tmp.chmod(0o600)
    tmp.replace(path)


class Host:
    def __init__(self, row):
        self.row = row
        self.base, self.profile, self.control = (Path(row[key]) for key in ("base", "profile", "control"))
        self.run_root = self.base / ".runtime/runs" / str(uuid4())
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.steps = []

    async def start(self):
        for name in ("command.json", "result.json", "ready.json", "fixture-error.json"):
            (self.control / name).unlink(missing_ok=True)
        for path in self.control.glob("*.png"):
            path.unlink()
        env = {**os.environ, "DSH_HOME": str(self.base), "FPL_ACCEPTANCE_CONTROL": str(self.control),
               "FPL_ACCEPTANCE_HOST": self.row["version"], "DSH_FPL_RUNTIME_ROOT": str(self.run_root / "managed"),
               "DSH_FPL_DATA_ROOT": str(self.run_root / "data"),
               "DSH_FPL_STORAGE_CONFIG": str(self.run_root / "storage.json"),
               "DSH_FPL_TRANSFER_ROOT": str(self.run_root / "transfers")}
        if self.row["version"] == "0.2.2-rc.5":
            # Prove uv bootstrap and FFmpeg guidance without changing global tools.
            self.bin = self.run_root / "test-bin"
            self.bin.mkdir(parents=True, exist_ok=True)
            for tool in ("ffmpeg", "ffprobe"):
                (self.bin / tool).unlink(missing_ok=True)
            (self.bin / "node").unlink(missing_ok=True)
            (self.bin / "node").symlink_to(shutil.which("node"))
            env["PATH"] = str(self.bin) + ":/usr/bin:/bin"
        self.log = (self.control / "host.log").open("w")
        (self.control / "host.log").chmod(0o600)
        self.process = await asyncio.create_subprocess_exec(self.row.get("node", "node"), self.row.get("cli", str(self.profile / "node_modules/@deepseek-ai/dsh/lib/bin.js")),
            "--profile", "acceptance", "--no-open", "--port", str(self.row["port"]),
            cwd=self.profile, env=env, stdout=self.log, stderr=asyncio.subprocess.STDOUT)
        for _ in range(600):
            if self.process.returncode is not None:
                raise AssertionError("Harness exited; see private host.log")
            if (self.control / "ready.json").exists():
                if len(await self.command("schemas")) == 56:
                    return
            await asyncio.sleep(.1)
        raise AssertionError("Native tools did not register")

    async def stop(self):
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 30)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.log.close()

    async def command(self, kind, **payload):
        identity = str(uuid4())
        private_json(self.control / "command.json", {"id": identity, "kind": kind, **payload})
        for _ in range(1800):
            try:
                value = json.loads((self.control / "result.json").read_text())
                if value["id"] == identity:
                    if not value["ok"]:
                        error = value["error"]
                        raise AssertionError(str(error.get("code")) + ": " + error["message"])
                    return value["value"]
            except FileNotFoundError:
                pass
            if self.process.returncode is not None:
                raise AssertionError("Harness exited during command")
            await asyncio.sleep(.1)
        raise AssertionError("Harness control timeout")

    async def invoke(self, method, **params):
        return await self.command("invoke", request={"method": method, "params": params})

    async def tool(self, name, **args):
        result = await self.command("tool", name=name, args=args)
        if result.get("isError"):
            raise AssertionError(name + ": " + str(result))
        return result.get("value", result)

    def passed(self, text):
        self.steps.append({"title": text, "status": "passed"})
        print(self.row["version"] + " · " + text, flush=True)

    async def install(self, identity):
        await self.invoke("setup.install", id=identity)
        for _ in range(1500):
            rows = await self.invoke("setup.status")
            item = next(row for row in rows if row["id"] == identity)
            if item["phase"] == "failed":
                raise AssertionError(identity + ": " + str(item.get("error")))
            if item["phase"] != "installing":
                assert item["phase"] in ("ready", "awaiting_authorization"), item
                self.passed("Installed and started " + identity)
                return
            await asyncio.sleep(.4)
        raise AssertionError("Installation timeout: " + identity)

    async def native_workflows(self):
        created = await self.tool("fpl_presentation_create_project", body={"title": "Native presentation", "document": {
            "version": 5, "width": 1280, "height": 720,
            "slides": [{"id": "slide-one", "background": "#FFFFFF", "notes": "", "elements": []}]}})
        path = {"project_id": created["id"]}
        await self.tool("fpl_presentation_edit", path=path, body={"expected_revision": created["revision"], "request_id": str(uuid4()),
            "operations": [{"action": "update", "entity": "slide", "id": "slide-one", "value": {"notes": "Native edit"}}]})
        current = await self.tool("fpl_presentation_get_project", path=path)
        exported = await self.tool("fpl_presentation_export", path=path, body={"expected_revision": current["revision"]})
        assert exported["resource"]["byte_size"] > 100
        self.passed("Native presentation create/edit/PPTX resource export")

        book = await self.tool("fpl_thought_create_knowledge_base", body={"title": "Native knowledge"})
        note = await self.tool("fpl_thought_get_note", path={"note_id": book["home_note_id"]})
        await self.tool("fpl_thought_edit_note", path={"note_id": note["id"]}, body={"expected_revision": note["revision"], "request_id": str(uuid4()),
            "operations": [{"action": "insert", "path": [0], "value": {"type": "paragraph", "content": [{"type": "text", "text": "Native note"}]}}]})
        note = await self.tool("fpl_thought_get_note", path={"note_id": note["id"]})
        assert (await self.tool("fpl_thought_export_note", path={"note_id": note["id"]}, query={"expected_revision": note["revision"], "format": "md"}))["resource"]["id"]
        self.passed("Native knowledge create/edit/Markdown resource export")

        created = await self.tool("fpl_visual_create_project", body={"title": "Native canvas", "kind": "canvas"})
        path = {"project_id": created["id"]}
        canvas = await self.tool("fpl_visual_get_canvas", path=path)
        edit = {"expected_revision": canvas["revision"], "request_id": str(uuid4()), "operations": [{"action": "insert", "entity": "node", "id": "native-text",
            "value": {"kind": "text", "title": "Native", "text": "Native canvas", "position": {"x": 10, "y": 20}}}]}
        first = await self.tool("fpl_visual_edit_canvas", path=path, body=edit)
        assert await self.tool("fpl_visual_edit_canvas", path=path, body=edit) == first
        canvas = await self.tool("fpl_visual_get_canvas", path=path)
        assert canvas["revision"] == 1 and canvas["nodes"][0]["text"] == "Native canvas"
        conflict = await self.command("tool", name="fpl_visual_edit_canvas", args={"path": path, "body": {**edit, "request_id": str(uuid4())}})
        assert conflict["isError"]
        self.passed("Native canvas CAS edits, idempotent replay and stale-version rejection")

        created = await self.tool("fpl_galgame_create_project", body={"title": "Native story"})
        path = {"project_id": created["id"]}
        story = await self.tool("fpl_galgame_get_story", path=path)
        chapter = story["document"]["chapters"][0]
        await self.tool("fpl_galgame_edit_story", path=path, body={"expected_revision": story["revision"], "request_id": str(uuid4()),
            "operations": [{"action": "update", "entity": "chapter", "id": chapter["id"], "value": {"title": "Native chapter"}}]})
        assert (await self.tool("fpl_galgame_get_story", path=path))["document"]["chapters"][0]["title"] == "Native chapter"
        self.passed("Native story creation and durable chapter edit")
        fragment = chapter["fragments"][0]
        await self.tool("fpl_galgame_edit_story", path=path, body={"expected_revision": story["revision"] + 1, "request_id": str(uuid4()),
            "operations": [{"action": "insert", "entity": "block", "chapter_id": chapter["id"], "parent_id": fragment["id"], "id": "native-wait", "value": {"type": "wait", "durationMs": 200}}]})
        export_body = {"expectedStoryRevision": story["revision"] + 2, "scope": "fragments", "fragmentIds": [fragment["id"]], "preset": "720p30"}
        preview = await self.tool("fpl_galgame_export_preview", path=path, body=export_body)
        assert preview["ready"], preview
        task = await self.tool("fpl_galgame_export_video", path=path, body={**export_body, "requestId": str(uuid4()), "previewFingerprint": preview["previewFingerprint"]})
        for _ in range(400):
            task = await self.tool("fpl_galgame_export_status", path={**path, "export_id": task["id"]})
            if task["status"] in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(.2)
        assert task["status"] == "completed", task
        assert (await self.tool("fpl_galgame_download_export", path={**path, "export_id": task["id"]}))["resource"]["byte_size"] > 100
        self.passed("Native story preflight, real FFmpeg export, task polling and video resource")

        data = io.BytesIO()
        with wave.open(data, "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000); stream.writeframes(b"\0\0" * 16000)
        wav = base64.b64encode(data.getvalue()).decode()
        resource = await self.command("resource", data=wav, metadata={"name": "native-sample.wav", "mime_type": "audio/wav", "application_id": "audio-annotation"})
        asset = await self.tool("fpl_audio_upload_audio", files={"upload": resource["id"]})
        created = await self.tool("fpl_audio_create_project", body={"title": "Native annotation", "asset_id": asset["id"]})
        path = {"project_id": created["id"]}
        document = await self.tool("fpl_audio_get_document", path=path)
        await self.tool("fpl_audio_edit_document", path=path, body={"expected_revision": document["revision"], "request_id": str(uuid4()),
            "operations": [{"action": "insert", "entity": "speaker", "id": "native-speaker", "value": {"name": "Native speaker", "color": "#FF0000"}}]})
        document = await self.tool("fpl_audio_get_document", path=path)
        assert (await self.tool("fpl_audio_export", path=path, query={"expected_revision": document["revision"], "format": "json"}))["resource"]["id"]
        self.passed("Native WAV resource upload, annotation edit and JSON attachment export")

        created = await self.tool("fpl_video_create_project", body={"title": "Native timeline"})
        path = {"project_id": created["id"]}
        resource = await self.command("resource", data=wav, metadata={"name": "native-sample.wav", "mime_type": "audio/wav", "application_id": "video-editor"})
        asset = await self.tool("fpl_video_upload_media", path=path, files={"upload": resource["id"]})
        timeline = await self.tool("fpl_video_get_timeline", path=path)
        await self.tool("fpl_video_edit_timeline", path=path, body={"expectedRevision": timeline["revision"], "requestId": str(uuid4()),
            "operations": [{"type": "addTrack", "track": {"id": "native-track", "kind": "audio", "name": "Native audio", "order": 10}},
                {"type": "addClip", "clip": {"id": "native-color", "name": "Native color", "trackId": "visual-1", "kind": "color", "color": "#123456", "timelineStartUs": 0, "durationUs": 200000}}]})
        assert (await self.tool("fpl_video_get_media", path={"asset_id": asset["id"]}))["resource"]["byte_size"] == len(data.getvalue())
        self.passed("Native video media upload, timeline edit and binary resource return")
        preview = await self.tool("fpl_video_render_preflight", path=path, body={"expectedRevision": timeline["revision"] + 1, "preset": "720p30"})
        assert preview["ready"], preview
        task = await self.tool("fpl_video_render", path=path, body={"expectedRevision": preview["revision"], "preset": "720p30", "requestId": str(uuid4()), "previewFingerprint": preview["fingerprint"]})
        for _ in range(400):
            task = await self.tool("fpl_video_render_status", path={**path, "task_id": task["id"]})
            if task["status"] in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(.2)
        assert task["status"] == "completed", task
        assert (await self.tool("fpl_video_get_media", path={"asset_id": task["outputAssetId"]}))["resource"]["byte_size"] > 100
        self.passed("Native timeline preflight, real FFmpeg render and persisted video output")

    async def assert_stopped(self, rows):
        for row in rows:
            for _ in range(100):
                try:
                    _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", urlsplit(row["endpoint"]).port), 1)
                    writer.close(); await writer.wait_closed()
                except (OSError, TimeoutError):
                    break
                await asyncio.sleep(.1)
            else:
                raise AssertionError("Managed port is still listening: " + row["id"])

    async def run(self):
        try:
            await self.start()
            specs = await self.command("schemas")
            self.passed("Registered native tools in the real Host (" + str(len(specs)) + ")")
            rows = await self.invoke("setup.status")
            assert len(rows) == 7
            assert all(row["phase"] == "missing" for row in rows), "Acceptance must start from a fresh runtime"
            if self.row["version"] == "0.2.2-rc.5":
                assert not any(row["ffmpeg"] for row in rows)
                self.passed("Missing FFmpeg is reported without blocking installation")
            self.passed("Installation control is available before business services")
            # Serial installation deliberately makes first-time Python setup reviewable.
            for identity in ["core", *[row["id"] for row in rows if row["id"] != "core"]]:
                await self.install(identity)
            if self.row["version"] == "0.2.2-rc.5":
                assert (self.run_root / "managed/tools/uv-0.12.18-arm64/uv").is_file()
                for tool in ("ffmpeg", "ffprobe"):
                    (self.bin / tool).symlink_to(shutil.which(tool))
                self.passed("Pinned uv bootstrapped into the private runtime")
            launch = await self.invoke("setup.open")
            ticket = parse_qs(urlsplit(launch["url"]).fragment)["ticket"][0]
            endpoint = next(row["endpoint"] for row in rows if row["id"] == "core")
            async with httpx.AsyncClient(base_url=endpoint, headers={"Origin": endpoint.rstrip("/")}, trust_env=False, timeout=30) as client:
                response = await client.post("/v1/session", json={"ticket": ticket})
                assert response.status_code == 200
                client.headers["X-Core-CSRF"] = response.json()["csrf"]
                ids = [row["id"] for row in rows if row["id"] != "core"]
                authorization = await self.invoke("setup.authorize.begin", ids=ids)
                assert (await self.invoke("setup.authorize.finish"))["status"] == "pending"
                response = await client.post("/v1/setup/authorizations/" + authorization["id"] + "/approve")
                assert response.status_code == 200, response.text
                assert "token" not in response.text
                result = await self.invoke("setup.authorize.finish")
                assert result["status"] == "ready"
                self.passed("Browser-approved proof bound all six services to the current account")
                private_json(self.control / "browser.json", {"core_origin": endpoint, "authorization_url": authorization["url"], "cookies": [
                    {"name": cookie.name, "value": cookie.value, "url": endpoint,
                     "httpOnly": cookie.name.endswith("session"), "sameSite": "Strict"} for cookie in client.cookies.jar]})
                for prefix in ("visual", "video", "presentation", "thought", "galgame", "audio"):
                    name = "fpl_" + prefix + ("_list_knowledge_bases" if prefix == "thought" else "_list_projects")
                    assert isinstance(await self.tool(name), (dict, list))
                self.passed("All six native read tools executed through Host validation and public HTTP")
                await self.native_workflows()
                rows = await self.invoke("setup.status")
                assert all(row["phase"] == "ready" for row in rows), rows
                self.passed("All seven services report ready after pairing")
                ui = await asyncio.create_subprocess_exec(shutil.which("node"), str(ROOT / "scripts/verify-managed-ui.mjs"), str(self.control),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                output, error = await ui.communicate()
                assert ui.returncode == 0, "Setup UI: " + error.decode()[-2000:]
                self.passed("Real Host installation settings and Core authorization UI at three widths")
                before = await self.tool("fpl_thought_list_knowledge_bases")
                await self.invoke("setup.install", id="dsh-thought-workshop")
                await self.invoke("setup.cancel", id="dsh-thought-workshop")
                for _ in range(200):
                    item = next(row for row in await self.invoke("setup.status") if row["id"] == "dsh-thought-workshop")
                    if item["phase"] != "installing":
                        break
                    await asyncio.sleep(.1)
                assert item.get("error", {}).get("code") == "installation_cancelled", item
                assert await self.tool("fpl_thought_list_knowledge_bases") == before
                self.passed("Cancelled repair preserves the running service and account data")
                registration = json.loads((self.run_root / "managed/records/dsh-thought-workshop.json").read_text())
                environment = Path(registration["directory"]) / ".runtime/venv"
                (environment / "bin/python").unlink()
                await self.install("dsh-thought-workshop")
                assert (environment / "bin/python").exists()
                assert await self.tool("fpl_thought_list_knowledge_bases") == before
                self.passed("Repair rebuilt a broken Python environment without transferring or losing data")
                registration = json.loads((self.run_root / "managed/records/core.json").read_text())
                core_environment = Path(registration["directory"]) / ".runtime/worker-venv"
                (core_environment / "bin/python").unlink()
                await self.install("core")
                assert (core_environment / "bin/python").exists()
                assert await self.tool("fpl_thought_list_knowledge_bases") == before
                self.passed("Core repair also succeeds when its virtual-environment Python is missing")
            await self.invoke("setup.stop", id="core")
            await self.assert_stopped(rows)
            self.passed("Stopping Core stops its six managed dependants")
            await self.invoke("setup.start", id="core")
            for row in rows:
                if row["id"] != "core":
                    await self.invoke("setup.start", id=row["id"])
            for _ in range(100):
                try:
                    after = await self.tool("fpl_thought_list_knowledge_bases")
                    break
                except AssertionError:
                    await asyncio.sleep(.1)
            assert after == before
            await self.invoke("setup.stop", id="core")
            await self.assert_stopped(rows)
            self.passed("Restart retained ownership, credentials, projects and repeated coordinated stop")
        finally:
            await self.stop()
            private_json(self.control / "report.json", {"host": self.row["version"], "steps": self.steps})


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host")
    args = parser.parse_args()
    matrix = json.loads((EVIDENCE / "harness-matrix.json").read_text())
    for row in matrix:
        if not args.host or row["version"] == args.host:
            await Host(row).run()


if __name__ == "__main__":
    asyncio.run(main())
