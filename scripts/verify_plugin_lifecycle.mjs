/** Current public tarballs, real Cordis fibers, isolated accounts/ports, provider CLIs only. */
import { mkdir, readFile, writeFile, realpath } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve, join } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { createServer } from "node:net";
import assert from "node:assert/strict";
const execute = promisify(execFile),
  root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const names = [
  "dsh-core",
  "dsh-visual-workshop",
  "dsh-video-editor",
  "dsh-presentation-workshop",
  "dsh-thought-workshop",
  "dsh-galgame-workshop",
  "dsh-audio-annotation",
];
const repos = names.map((name) => join(root, name === "dsh-core" ? "fpl-core" : name.replace(/^dsh-/, "")));
await execute(
  "git",
  ["check-ignore", ".local/plugin-lifecycle", ".runtime/plugin-lifecycle"],
  { cwd: root },
);
const stamp = String(Date.now()),
  temporary = join(root, ".local/plugin-lifecycle", stamp),
  profile = join(root, ".runtime/plugin-lifecycle", stamp);
await mkdir(temporary, { recursive: true, mode: 0o700 });
await mkdir(profile, { recursive: true, mode: 0o700 });
const corePackage = JSON.parse(
    await readFile(join(repos[0], "package.json"), "utf8"),
  ),
  dependencies = {};
async function installedPackage(name, from) {
  let directory = await realpath(from);
  while (true) {
    const candidate = join(directory, "node_modules", name);
    try {
      return {
        directory: await realpath(candidate),
        pkg: JSON.parse(
          await readFile(join(candidate, "package.json"), "utf8"),
        ),
      };
    } catch {}
    const parent = dirname(directory);
    if (parent === directory) break;
    directory = parent;
  }
  throw new Error("Installed peer is missing: " + name);
}
const queue = Object.keys(corePackage.peerDependencies).map((name) => ({
  name,
  from: repos[0],
}));
while (queue.length) {
  const { name, from } = queue.shift();
  if (dependencies[name]) continue;
  const { directory, pkg } = await installedPackage(name, from);
  dependencies[name] = pkg.version;
  for (const peer of Object.keys(pkg.peerDependencies || {})) {
    if (pkg.peerDependenciesMeta?.[peer]?.optional) continue;
    queue.push({ name: peer, from: directory });
  }
}
const packages = [];
for (const repo of repos) {
  const pkg = JSON.parse(await readFile(join(repo, "package.json"), "utf8"));
  const archive = join(
    repo,
    ".runtime/packages",
    pkg.name.replace(/^@/, "").replace("/", "-") + "-" + pkg.version + ".tgz",
  );
  dependencies[pkg.name] = "file:" + archive;
  packages.push(pkg);
}
await writeFile(
  join(profile, "package.json"),
  JSON.stringify(
    {
      name: "fpl-plugin-lifecycle-fixture",
      private: true,
      type: "module",
      dependencies,
    },
    null,
    2,
  ),
);
await writeFile(
  join(profile, "pnpm-workspace.yaml"),
  "packages: []\nautoInstallPeers: false\n",
);
await execute("pnpm", ["install", "--offline", "--ignore-scripts"], {
  cwd: profile,
  maxBuffer: 4 * 1024 * 1024,
});
async function publicModule(name) {
  const directory = join(profile, "node_modules", name),
    pkg = JSON.parse(await readFile(join(directory, "package.json"), "utf8"));
  const entry = pkg.exports?.["."];
  const path =
    typeof entry === "string"
      ? entry
      : entry?.import || entry?.default || pkg.main;
  assert.equal(typeof path, "string", name + " has no public import entry");
  return import(pathToFileURL(resolve(directory, path)));
}
const { Context } = await publicModule("@deepseek-ai/cordis");
const modules = await Promise.all(
  packages.map((pkg) => publicModule(pkg.name)),
);
const data = join(temporary, "应用 数据"),
  locator = join(temporary, "locator.json");
await mkdir(join(data, "core"), { recursive: true });
await writeFile(
  join(data, ".dsh-fpl-storage.json"),
  JSON.stringify({ instance: stamp }),
  { mode: 0o600 },
);
await writeFile(
  locator,
  JSON.stringify({ version: 1, revision: 1, instance: stamp, root: data }),
  { mode: 0o600 },
);
const previous = process.env.DSH_FPL_STORAGE_CONFIG;
process.env.DSH_FPL_STORAGE_CONFIG = locator;
const ports = [];
for (const repo of repos) {
  const server = createServer();
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  ports.push(server.address().port);
  await new Promise((r) => server.close(r));
}
const origins = ports.map((port) => "http://127.0.0.1:" + port),
  environment = (repo) => ({
    ...process.env,
    PYTHONPATH: join(repo, "python"),
  });
const core = (command, ...args) =>
  execute(
    join(repos[0], ".runtime/worker-venv/bin/python"),
    [
      "-m",
      "dsh_core_worker.cli",
      command,
      "--no-open",
      "--port",
      String(ports[0]),
      ...args,
    ],
    { cwd: repos[0], env: environment(repos[0]), timeout: 90000 },
  );
const app = (index, command, ...args) =>
  execute(
    process.execPath,
    [
      "scripts/application.mjs",
      command,
      "--port",
      String(ports[index]),
      ...args,
    ],
    { cwd: repos[index], env: environment(repos[index]), timeout: 90000 },
  );
async function ready(index) {
  try {
    return (
      await fetch(origins[index] + "/ready", {
        signal: AbortSignal.timeout(1500),
      })
    ).ok;
  } catch {
    return false;
  }
}
async function allReady(expected) {
  for (let attempt = 0; attempt < 200; attempt++) {
    const flags = await Promise.all(repos.map((_, i) => ready(i)));
    if (flags.every((flag) => flag === expected)) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(
    "Service state did not reach " +
      expected +
      ": " +
      JSON.stringify(await Promise.all(repos.map((_, i) => ready(i)))),
  );
}
const launch = join(temporary, "launch.json");
async function ticket() {
  await core("dashboard", "--output", launch);
  return new URL(JSON.parse(await readFile(launch, "utf8")).url).hash.slice(
    "#ticket=".length,
  );
}
let coreFiber, ctx;
const fibers = [];
const report = {
  versions: packages.map((pkg) => ({ name: pkg.name, version: pkg.version })),
};
try {
  await core("start");
  const signed = await fetch(origins[0] + "/v1/session", {
    method: "POST",
    headers: { Origin: origins[0], "Content-Type": "application/json" },
    body: JSON.stringify({ ticket: await ticket() }),
  });
  assert.ok(signed.ok);
  const csrf = (await signed.json()).csrf,
    cookie = signed.headers
      .getSetCookie()
      .map((v) => v.split(";")[0])
      .join("; ");
  const paired = await fetch(origins[0] + "/v1/bridges", {
    method: "POST",
    headers: {
      Origin: origins[0],
      Cookie: cookie,
      "X-Core-CSRF": csrf,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: "isolated-plugin-lifecycle" }),
  });
  assert.ok(paired.ok);
  const pair = await paired.json();
  for (let index = 1; index < repos.length; index++) {
    await app(index, "init");
    await core("dashboard", "--output", launch);
    await app(index, "connect-core", "--launch-file", launch);
  }
  await core("stop");
  ctx = new Context();
  ctx.provide("credentials", {
    resolve: async () => ({ value: pair.token }),
    set: async () => {},
  });
  ctx.provide("typert", { register: () => () => {} });
  coreFiber = ctx.plugin(modules[0], {
    endpoint: origins[0],
    serviceDirectory: repos[0],
  });
  await coreFiber;
  for (let index = 1; index < repos.length; index++) {
    const fiber = ctx.plugin(modules[index], {
      endpoint: origins[index],
      serviceDirectory: repos[index],
    });
    fibers.push(fiber);
    await fiber;
  }
  await allReady(true);
  report.enable_started_seven = true;
  const before = JSON.parse((await app(3, "status")).stdout).pid;
  await fibers[2].dispose();
  assert.equal(await ready(3), false);
  report.disable_stopped_application = true;
  fibers[2] = ctx.plugin(modules[3], {
    endpoint: origins[3],
    serviceDirectory: repos[3],
  });
  await fibers[2];
  const after = JSON.parse((await app(3, "status")).stdout).pid;
  assert.notEqual(before, after);
  report.reenable_started_new_process = true;
  await coreFiber.dispose();
  await allReady(false);
  report.core_disable_stopped_dependents = true;
  coreFiber = ctx.plugin(modules[0], {
    endpoint: origins[0],
    serviceDirectory: repos[0],
  });
  await coreFiber;
  await allReady(true);
  report.core_reenable_restarted_dependents = true;
  await coreFiber.dispose();
  await allReady(false);
  report.final_stop_complete = true;
  console.log(JSON.stringify(report));
} finally {
  for (const fiber of fibers.reverse())
    await Promise.resolve(fiber.dispose()).catch(() => {});
  await Promise.resolve(coreFiber?.dispose()).catch(() => {});
  for (let index = 1; index < repos.length; index++)
    await app(index, "stop").catch(() => {});
  await core("stop").catch(() => {});
  if (previous === undefined) delete process.env.DSH_FPL_STORAGE_CONFIG;
  else process.env.DSH_FPL_STORAGE_CONFIG = previous;
  await writeFile(
    join(temporary, "report.json"),
    JSON.stringify(report, null, 2),
    { mode: 0o600 },
  );
}
