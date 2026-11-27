/** Real browser and HTTP acceptance against isolated product state. No live accounts. */
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdir, mkdtemp, readFile, writeFile, open } from "node:fs/promises";
import { spawn, execFileSync } from "node:child_process";
import { createServer } from "node:net";
import assert from "node:assert/strict";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(root, ".local/file-browser-rebuild");
await mkdir(resolve(output, "fixtures"), { recursive: true });
execFileSync(resolve(root, "visual-workshop/.runtime/venv/bin/python"), [
  "-c",
  `from pathlib import Path
from PIL import Image, ImageDraw
import wave
p=Path(${JSON.stringify(resolve(output, "fixtures"))})
Image.new('RGB',(32,24),'#20a0b0').save(p/'library-image.png')
for i in range(18):
 image=Image.new('RGB',(480,270),['#dae4dc','#e3d8c9','#cbdce5','#e4d1ce','#d5d3e6','#c7dedc'][i%6])
 draw=ImageDraw.Draw(image)
 draw.ellipse((280-i%4*20,20,370-i%4*20,110),fill=['#d28c54','#b96b63','#e1af62'][i%3])
 draw.polygon([(0,200),(120,100+i%3*20),(260,200),(380,120),(480,190),(480,270),(0,270)],fill=['#628177','#6c818f','#8d7c72'][i%3])
 draw.polygon([(0,245),(220,170),(480,235),(480,270),(0,270)],fill=['#3e625b','#4e687d','#6b5b59'][i%3])
 draw.text((20,22),'STORYBOARD / %02d' % (i+1),fill='#ffffff')
 image.save(p/('scene-%02d.png' % (i+1)))
with wave.open(str(p/'library-audio.wav'),'wb') as w:
 w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\\0\\0'*32000)
`,
]);
const png = await readFile(resolve(output, "fixtures/library-image.png"));
const wav = await readFile(resolve(output, "fixtures/library-audio.wav"));
const { chromium, expect } = createRequire(
  resolve(root, "visual-workshop/web/package.json"),
)("@playwright/test");
const products = process.argv.slice(2).length
  ? process.argv.slice(2)
  : [
      "visual-workshop",
      "presentation-workshop",
      "video-editor",
      "thought-workshop",
      "galgame-workshop",
      "audio-annotation",
    ];
const modules = {
  "visual-workshop": "fpl_visual",
  "presentation-workshop": "fpl_presentation",
  "video-editor": "fpl_video",
  "thought-workshop": "fpl_thought",
  "galgame-workshop": "fpl_galgame",
  "audio-annotation": "fpl_annotation",
};
let results = [];
try {
  results = JSON.parse(
    await readFile(resolve(output, "browser-results.json"), "utf8"),
  ).filter((result) => !products.includes(result.product));
} catch {}

for (const product of products) {
  const evidence = await mkdtemp(resolve(output, product + "-"));
  const socket = createServer();
  await new Promise((r) => socket.listen(0, "127.0.0.1", r));
  const port = socket.address().port;
  await new Promise((r) => socket.close(r));
  const origin = `http://127.0.0.1:${port}`,
    secret = "unified-library-isolated-launch-secret";
  const log = await open(resolve(evidence, "backend.log"), "a");
  const service = spawn(
    resolve(root, product, ".runtime/venv/bin/python"),
    [
      "-c",
      `from pathlib import Path
import uvicorn
from ${modules[product]}.embedded import prepare
from ${modules[product]}.gateway import create_app
root=Path(${JSON.stringify(resolve(evidence, "state"))})
host=prepare(root,${port})
app=create_app(root,port=${port},run_worker=False,embedded_core=host,launch_secret=${JSON.stringify(secret)})
uvicorn.run(app,host='127.0.0.1',port=${port},log_level='error')
`,
    ],
    {
      cwd: resolve(root, product),
      env: {
        ...process.env,
        PYTHONPATH:
          resolve(root, product, "python") +
          ":" +
          resolve(root, "fpl-core/python"),
      },
      stdio: ["ignore", log.fd, log.fd],
    },
  );
  await log.close();
  let browser, page;
  try {
    browser = await chromium.launch({ channel: "chrome", headless: true });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 960 },
      reducedMotion: "reduce",
    });
    for (let i = 0; i < 150; i++) {
      if (service.exitCode !== null) throw Error("Backend exited");
      try {
        if ((await context.request.get(origin + "/ready")).ok()) break;
      } catch {}
      await new Promise((r) => setTimeout(r, 200));
    }
    await expect(
      await context.request.post(origin + "/__desktop/session", {
        headers: { Origin: origin, "x-fpl-launch": secret },
      }),
    ).toBeOK();
    const csrf = (await context.cookies()).find((c) =>
      c.name.endsWith("_csrf"),
    ).value;
    const headers = { Origin: origin, "X-CSRF-Token": csrf };
    async function post(path, data) {
      const response = await context.request.post(origin + path, {
        headers,
        data,
      });
      if (!response.ok()) throw Error(path + ": " + (await response.text()));
      return response.json();
    }
    async function get(path) {
      const response = await context.request.get(origin + path);
      if (!response.ok()) throw Error(path + ": " + (await response.text()));
      return response.json();
    }
    async function resource(name, type, buffer) {
      const data = await post("/v1/core/rpc", {
        method: "resource.put",
        params: {
          name,
          mime_type: type,
          data_base64: buffer.toString("base64"),
        },
      });
      return data.result || data;
    }
    const image = await resource("library-image.png", "image/png", png),
      audio = await resource("library-audio.wav", "audio/wav", wav),
      text = await resource(
        "library-note.txt",
        "text/plain",
        Buffer.from("preserved original"),
      );
    const nativeFiles = [];
    for (let i = 0; i < 18; i++) {
      const uploaded = await context.request.post(origin + "/v1/files", {
        headers,
        multipart: {
          upload: {
            name: `scene-${String(i + 1).padStart(2, "0")}.png`,
            mimeType: "image/png",
            buffer: await readFile(
              resolve(
                output,
                "fixtures",
                `scene-${String(i + 1).padStart(2, "0")}.png`,
              ),
            ),
          },
        },
      });
      await expect(uploaded).toBeOK();
      nativeFiles.push(await uploaded.json());
    }
    let project, note;
    if (product === "thought-workshop") {
      project = await post("/v1/thought-workshop/knowledge-bases", {
        title: "文件库验收",
        description: "",
      });
      note = await post("/v1/thought-workshop/notes", {
        knowledge_base_id: project.id,
        expected_knowledge_revision: project.revision,
        title: "附件验收",
        schema_version: 2,
        favorite: false,
        pinned: false,
        document: { type: "doc", content: [{ type: "paragraph" }] },
      });
    } else if (product === "audio-annotation") {
      const response = await context.request.post(origin + "/v1/files", {
        headers,
        multipart: {
          upload: { name: "source.wav", mimeType: "audio/wav", buffer: wav },
        },
      });
      await expect(response).toBeOK();
      project = await post("/v1/audio-annotation/projects", {
        title: "文件库验收",
        asset_id: (await response.json()).id,
      });
    } else {
      const body = { title: "文件库验收" };
      if (product === "visual-workshop") body.kind = "canvas";
      if (product === "presentation-workshop")
        body.document = {
          version: 3,
          width: 1280,
          height: 720,
          slides: [
            { id: "slide1", background: "#ffffff", notes: "", elements: [] },
          ],
        };
      project = await post(`/v1/${product}/projects`, body);
    }
    const attach = (id) =>
      post("/v1/app/project-files", {
        project_id: project.id,
        source: "core",
        source_id: id,
      });
    await attach(image.id);
    await attach(audio.id);
    await attach(text.id);
    const steps = [];
    const record = (title) =>
      steps.push({ title, at: new Date().toISOString() });
    page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await context.tracing.start({
      screenshots: true,
      snapshots: true,
      sources: true,
    });
    const browserRoot = page.locator(".shared-file-browser").first();
    await page.goto(origin + "/core/files");
    await expect(
      page.getByRole("heading", { name: "文件管理", exact: true }),
    ).toBeVisible();
    await expect(browserRoot.locator(".file-asset-item")).toHaveCount(
      21 + (product === "audio-annotation" ? 1 : 0),
    );
    await expect(page.getByText("关联目标项目", { exact: true })).toHaveCount(
      0,
    );
    await expect(
      page.getByText("管理文件夹与归档", { exact: true }),
    ).toHaveCount(0);
    await expect(browserRoot.locator(".file-items.grid")).toBeVisible();
    await expect
      .poll(
        () =>
          browserRoot
            .locator(".file-item-preview img")
            .evaluateAll(
              (images) =>
                images.filter(
                  (image) => image.complete && image.naturalWidth > 0,
                ).length,
            ),
        { timeout: 30000 },
      )
      .toBeGreaterThan(10);
    const bounds = await browserRoot
      .locator(".file-browser-controls")
      .boundingBox();
    assert(bounds.height < 140, "toolbar unexpectedly tall");
    record("打开含真实素材的文件管理，验证缩略图与旧版工具栏密度");
    await page.screenshot({ path: resolve(evidence, "files-light.png") });
    await page.getByRole("button", { name: "新建文件夹", exact: true }).click();
    let dialog = page.getByRole("dialog", { name: "新建文件夹", exact: true });
    await dialog.getByLabel("名称", { exact: true }).fill("Storyboard");
    await dialog.getByRole("button", { name: "确认", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "打开文件夹 Storyboard", exact: true }),
    ).toBeVisible();
    const folders = (await get("/v1/file-folders")).items;
    const folder = folders.find((x) => x.name === "Storyboard");
    assert(folder);
    const file = nativeFiles[0];
    const row = browserRoot.locator(
      `[data-file-key="application::${file.id}"]`,
    );
    await row.locator("summary").click();
    await row.getByRole("menuitem", { name: "重命名", exact: true }).click();
    dialog = page.getByRole("dialog", { name: "重命名", exact: true });
    await dialog.getByLabel("名称", { exact: true }).fill("Opening shot");
    await dialog.getByRole("button", { name: "确认", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(row.getByText("Opening shot", { exact: true })).toBeVisible();
    await row.locator("summary").click();
    await row.getByRole("menuitem", { name: "移动到…", exact: true }).click();
    dialog = page.getByRole("dialog", { name: "移动到文件夹", exact: true });
    await dialog
      .getByLabel("目标文件夹", { exact: true })
      .selectOption(`application::${folder.id}`);
    await dialog.getByRole("button", { name: "确认", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await page
      .getByRole("button", { name: "打开文件夹 Storyboard", exact: true })
      .click();
    await expect(
      browserRoot.getByText("Opening shot", { exact: true }),
    ).toBeVisible();
    await page.getByLabel("选择要上传的文件", { exact: true }).setInputFiles({
      name: "nested.png",
      mimeType: "image/png",
      buffer: png,
    });
    await expect(
      browserRoot.getByText("nested", { exact: true }),
    ).toBeVisible();
    await page.screenshot({ path: resolve(evidence, "folder.png") });
    record("在同一文件页新建目录、重命名、移动和上传文件");
    await page.getByRole("button", { name: "文件管理", exact: true }).click();
    const nativeRoot = (await get("/v1/files?include_svg=true")).items;
    assert(!nativeRoot.some((x) => x.id === file.id));
    await page
      .getByRole("button", { name: "预览 library-note.txt", exact: true })
      .click();
    dialog = page.getByRole("dialog", {
      name: "library-note.txt",
      exact: true,
    });
    await expect(
      dialog.getByText("preserved original", { exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await page.getByRole("button", { name: "列表视图", exact: true }).click();
    await page.reload();
    await expect(browserRoot.locator(".file-items.list")).toBeVisible();
    await page.getByRole("button", { name: "卡片视图", exact: true }).click();
    record("预览真实文件并验证视图偏好在刷新后保留");
    await page.getByRole("button", { name: "深色", exact: true }).click();
    await page.screenshot({ path: resolve(evidence, "files-dark.png") });
    await page.setViewportSize({ width: 860, height: 760 });
    await page.screenshot({ path: resolve(evidence, "files-860.png") });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
      "860px horizontal overflow",
    );
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByRole("button", { name: "浅色", exact: true }).click();
    await page.goto(origin + "/core/project-files?project=" + project.id);
    await expect(page).toHaveURL(origin + "/core/files?project=" + project.id);
    await expect(
      page.getByText("library-note.txt", { exact: true }),
    ).toBeVisible();
    const attached = browserRoot
      .locator(".file-asset-item")
      .filter({ has: page.getByText("library-note.txt", { exact: true }) });
    await attached.locator("summary").click();
    await attached
      .getByRole("menuitem", { name: "从项目移除", exact: true })
      .click();
    dialog = page.getByRole("dialog", { name: "移除文件", exact: true });
    await expect(
      dialog.getByText("只移除本项目中的引用，原始文件会保留。", {
        exact: true,
      }),
    ).toBeVisible();
    await dialog.getByRole("button", { name: "确认", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(
      page.getByText("library-note.txt", { exact: true }),
    ).toHaveCount(0);
    assert(
      (
        await context.request.get(
          origin + `/v1/core/file-library/entries/${text.id}/content`,
        )
      ).ok(),
    );
    record("验证旧链接、原附件可见和解除引用后原件保留");
    let editorPath = `/apps/${product}/projects/${project.id}`;
    if (["video-editor", "galgame-workshop"].includes(product))
      editorPath += "/editor";
    if (product === "visual-workshop") editorPath += "/canvas";
    if (product === "thought-workshop")
      editorPath = `/apps/thought-workshop/knowledge-bases/${project.id}/documents/${note.id}`;
    if (product === "audio-annotation") editorPath = "/apps/audio-annotation";
    await page.goto(origin + editorPath);
    if (product === "visual-workshop") {
      await page
        .getByRole("button", { name: "导入 / 管理素材", exact: true })
        .click();
      await page
        .getByRole("button", { name: "从文件库选用", exact: true })
        .click();
    }
    if (product === "video-editor") {
      await page
        .getByRole("button", { name: "向未分类添加素材", exact: true })
        .click();
      await page
        .getByRole("menuitem", { name: "从其他项目导入", exact: true })
        .click();
    }
    if (product === "presentation-workshop")
      await page.getByRole("button", { name: "文件库", exact: true }).click();
    if (product === "thought-workshop")
      await page
        .getByRole("button", { name: "选择素材", exact: true })
        .first()
        .click();
    if (product === "audio-annotation")
      await page.getByRole("button", { name: "新建任务", exact: true }).click();
    if (product === "galgame-workshop") {
      await page.getByRole("button", { name: "资产", exact: true }).click();
      await page
        .getByRole("button", { name: "场景", exact: true })
        .first()
        .click();
      await page
        .getByRole("button", { name: /添加场景|新建场景/ })
        .first()
        .click();
      await page
        .getByRole("button", { name: /添加.*图层|添加图片/ })
        .first()
        .click();
    }
    const picker = page.locator(".shared-file-browser.browser-picker").last();
    await expect(picker).toBeVisible();
    await picker.getByRole("tab", { name: "文件库", exact: true }).click();
    await picker
      .getByLabel("搜索文件或文件夹", { exact: true })
      .fill(
        product === "audio-annotation"
          ? "library-audio.wav"
          : product === "thought-workshop"
            ? "library-note.txt"
            : "library-image.png",
      );
    await expect(picker.locator(".file-asset-item")).toHaveCount(1);
    if (!["audio-annotation", "thought-workshop"].includes(product))
      await expect
        .poll(
          () =>
            picker
              .locator(".file-item-preview img")
              .evaluateAll((images) =>
                images.some(
                  (image) => image.complete && image.naturalWidth > 0,
                ),
              ),
          { timeout: 15000 },
        )
        .toBe(true);
    await page.screenshot({ path: resolve(evidence, "native-picker.png") });
    await picker.locator(".file-asset-item .file-item-main").click();
    await picker
      .getByRole("button", { name: "使用所选素材", exact: true })
      .click();
    if (product === "thought-workshop")
      await expect(page.locator(".thought-attachment")).toBeVisible();
    if (product === "video-editor")
      await expect
        .poll(
          async () =>
            (await get(`/v1/video-editor/projects/${project.id}/assets`)).items
              .length,
        )
        .toBeGreaterThan(0);
    if (product === "visual-workshop")
      await expect
        .poll(
          async () =>
            (await get(`/v1/files?project_id=${project.id}&include_svg=true`))
              .items.length,
        )
        .toBeGreaterThan(0);
    if (product === "galgame-workshop")
      await expect
        .poll(
          async () =>
            (await get(`/v1/galgame-workshop/projects/${project.id}/assets`))
              .items.length,
        )
        .toBeGreaterThan(0);
    if (product === "presentation-workshop")
      await expect
        .poll(
          async () =>
            (await get(`/v1/presentation-workshop/projects/${project.id}`))
              .document.slides[0].elements.length,
          { timeout: 15000 },
        )
        .toBeGreaterThan(0);
    if (product === "audio-annotation") {
      const create = page
        .getByRole("dialog", { name: "新建标注任务", exact: true })
        .getByRole("button", { name: "创建并打开", exact: true });
      await expect(create).toBeEnabled();
      await create.click();
      await expect
        .poll(
          async () => (await get("/v1/audio-annotation/projects")).items.length,
        )
        .toBe(2);
    }
    if (product === "thought-workshop")
      await expect
        .poll(
          async () =>
            JSON.stringify(
              (await get(`/v1/thought-workshop/notes/${note.id}`)).document,
            ),
          { timeout: 15000 },
        )
        .toContain('"attachment"');
    record("在工坊真实编辑入口选用文件库素材，核验业务接口或文档结果");
    await page.screenshot({ path: resolve(evidence, "native-result.png") });
    await page.reload();
    if (product === "thought-workshop")
      await expect(page.locator(".thought-attachment")).toBeVisible({
        timeout: 15000,
      });
    await context.tracing.stop({ path: resolve(evidence, "trace.zip") });
    assert.equal(errors.length, 0, errors.join("\n"));
    const unauthorized = await browser.newContext();
    const denied = await unauthorized.request.get(
      origin + "/v1/app/file-projects",
    );
    assert([401, 403].includes(denied.status()));
    await unauthorized.close();
    record("刷新后结果保持，未登录请求被拒绝");
    results.push({ product, passed: true, evidence, steps });
    console.log(product + ": PASS");
  } catch (error) {
    if (page) {
      await page
        .screenshot({ path: resolve(evidence, "failure.png") })
        .catch(() => {});
      await writeFile(
        resolve(evidence, "failure.txt"),
        await page
          .locator("body")
          .innerText()
          .catch(() => ""),
      );
    }
    await browser
      ?.contexts()[0]
      ?.tracing.stop({ path: resolve(evidence, "trace.zip") })
      .catch(() => {});
    results.push({ product, passed: false, evidence, error: String(error) });
    console.error(product + ": " + error);
  } finally {
    if (browser) await browser.close();
    service.kill("SIGTERM");
  }
  await writeFile(
    resolve(output, "browser-results.json"),
    JSON.stringify(results, null, 2),
  );
}
if (
  results.some((result) => products.includes(result.product) && !result.passed)
)
  process.exitCode = 1;
