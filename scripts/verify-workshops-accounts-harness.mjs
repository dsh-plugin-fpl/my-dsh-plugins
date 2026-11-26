/** Install the three actual tarballs in a disposable Harness profile. */
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { spawn, spawnSync } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
const base =
  process.env.WORKSHOPS_WORKSPACE ||
  resolve(dirname(fileURLToPath(import.meta.url)), "..");
const task = process.env.WORKSHOPS_TEST_ROOT;
if (!task) throw new Error("WORKSHOPS_TEST_ROOT required");
const fixture = resolve(task, "consumer"),
  home = resolve(task, "harness"),
  profileName = "workshops";
const profile = resolve(home, "profiles", profileName);
await mkdir(profile, { recursive: true });
await mkdir(fixture, { recursive: true });
await writeFile(
  resolve(fixture, "package.json"),
  JSON.stringify({
    name: "workshops-acceptance",
    version: "0.0.1",
    private: true,
    type: "module",
    main: "index.mjs",
    dsh: { bundle: { patch: "./cordis.patch.yml" } },
  }),
);
await writeFile(
  resolve(fixture, "cordis.patch.yml"),
  "- insert:\n    - id: workshops-acceptance\n      name: workshops-acceptance\n",
);
await writeFile(
  resolve(fixture, "index.mjs"),
  `import {readFile,writeFile} from 'node:fs/promises';
export const inject=['dshCore'];
export function apply(ctx){void(async()=>{const pair=JSON.parse(await readFile(process.env.WORKSHOPS_CORE_PAIR,'utf8'));
const response=await ctx.dshCore.invoke({method:'credential.set',params:{value:pair.token}});
if(!response.ok)throw new Error(response.error.message);
const capabilities=await ctx.dshCore.capabilities();
await writeFile(process.env.WORKSHOPS_HARNESS_REPORT,JSON.stringify({status:'connected',catalog:!!capabilities.generation_options}));
})().catch(async e=>writeFile(process.env.WORKSHOPS_HARNESS_REPORT,JSON.stringify({status:'failed',message:e.message})));}`,
);
const core=process.env.WORKSHOPS_CORE_REPO||resolve(base,'fpl-core');
const applications=['presentation-workshop','thought-workshop','galgame-workshop','audio-annotation','visual-workshop','video-editor'];
const packages={};
for(const slug of ['core',...applications]){
 const directory=slug==='core'?core:resolve(base,'dsh-'+slug);
 const meta=JSON.parse(await readFile(resolve(directory,'package.json'),'utf8'));
 packages[meta.name]='file:'+resolve(directory,'.runtime/packages/'+meta.name.replace('@','').replace('/','-')+'-'+meta.version+'.tgz');
}
packages['workshops-acceptance']='file:'+fixture;
await writeFile(
  resolve(profile, "package.json"),
  JSON.stringify(
    {
      name: "workshops-isolated-profile",
      private: true,
      dependencies: packages,
      dsh: {
        profile: {
          bundles: [
            "@deepseek-ai/dsh-base",
            "@deepseek-ai/dsh-web-app",
            ...Object.keys(packages),
          ],
        },
      },
    },
    null,
    2,
  ),
);
await writeFile(
  resolve(profile, "cordis.patch.yml"),
  `- id: dsh-core\n  config:\n    manageService: false\n    endpoint: http://127.0.0.1:19310\n` +
    applications
      .map(
        (route, i) =>
          `- id: dsh-${route}\n  config:\n    manageService: false\n    endpoint: http://127.0.0.1:${19362 + i}\n    credentialFile: ${JSON.stringify(resolve(task, "dsh-" + route, "plugin.json"))}\n`,
      )
      .join(""),
);
const install = spawnSync("pnpm", ["install", "--ignore-scripts"], {
  cwd: profile,
  encoding: "utf8",
});
if (install.status) throw new Error(install.stderr.slice(-2000));
const report = resolve(task, "harness-result.json"),
  log = [];
const child = spawn(
  "dsh",
  ["--profile", profileName, "--no-open", "--port", "19368"],
  {
    cwd: base,
    env: {
      ...process.env,
      DSH_HOME: home,
      WORKSHOPS_CORE_PAIR: resolve(task, "core/fixture-pair.json"),
      WORKSHOPS_HARNESS_REPORT: report,
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
child.stdout.on("data", (d) => log.push(d.toString()));
child.stderr.on("data", (d) => log.push(d.toString()));
try {
  let result;
  for (let i = 0; i < 400; i++) {
    try {
      result = JSON.parse(await readFile(report, "utf8"));
      break;
    } catch {}
    if (child.exitCode !== null) throw new Error("Harness exited");
    await new Promise((r) => setTimeout(r, 100));
  }
  assert.equal(result?.status, "connected", result?.message);
  assert.equal(result.catalog, true);
  const cookies=JSON.parse(await readFile(resolve(task,'browser-state.json'),'utf8')).core_cookies;
  const headers={Cookie:cookies.map(v=>v.name+'='+v.value).join('; ')};
  const pair=JSON.parse(await readFile(resolve(task,'core/fixture-pair.json'),'utf8'));
  let registered=[];
  for(let attempt=0;attempt<120;attempt++){
   const response=await fetch('http://127.0.0.1:19310/v1/applications',{headers});
   assert.equal(response.status,200);
   registered=(await response.json()).items.filter(row=>row.bridge_id===pair.id);
   if(applications.every(alias=>registered.some(row=>row.application_id===alias&&row.status==='ready')))break;
   await new Promise(r=>setTimeout(r,100));
  }
  assert.equal(registered.length,6,JSON.stringify(registered));
  assert.ok(registered.every(row=>row.icon_url&&row.url.includes('/apps/')));
  await writeFile(resolve(task,'harness-registration.json'),JSON.stringify({status:'passed',applications:registered.map(({name,application_id,status})=>({name,application_id,status}))},null,2));

  console.log("HARNESS_TARBALLS_CONNECTED");
  await new Promise((r) => setTimeout(r, 3000));
} finally {
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((r) => child.once("exit", r)),
    new Promise((r) => setTimeout(r, 6000)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
  await writeFile(
    resolve(task, "harness.log"),
    log.join("").replace(/([?&]token=)[^\s]+/g, "$1[redacted]"),
  );
}
for (let i = 0; i < 6; i++)
  assert.ok(
    (await fetch("http://127.0.0.1:" + (19362 + i) + "/ready")).ok,
    "Application stopped with Harness",
  );
