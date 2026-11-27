/** Real public GitHub reads and product HTTP imports; each embedded product uses isolated state. */
import {createRequire} from 'node:module';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {mkdir, writeFile, open} from 'node:fs/promises';
import {createServer} from 'node:net';
import {spawn} from 'node:child_process';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = resolve(root, '.local/github-resource-library');
await mkdir(output, {recursive: true});
const products = process.argv.slice(2).length ? process.argv.slice(2) : ['visual-workshop', 'video-editor', 'presentation-workshop', 'thought-workshop', 'galgame-workshop', 'audio-annotation'];
const {chromium} = createRequire(resolve(root, 'visual-workshop/web/package.json'))('@playwright/test');
const results = [];
await writeFile(resolve(output,'result.json'),JSON.stringify({passed:false,status:'running'}));
for (const product of products) {
  const directory = resolve(root, product);
  const evidence = resolve(output, product);
  await mkdir(evidence, {recursive: true});
  const server = createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  const origin = `http://127.0.0.1:${port}`;
  const modules = {'visual-workshop':'fpl_visual','video-editor':'fpl_video','presentation-workshop':'fpl_presentation','thought-workshop':'fpl_thought','galgame-workshop':'fpl_galgame','audio-annotation':'fpl_annotation'};
  const secret = 'resource-library-isolated-browser-fixture-secret';
  const log = await open(resolve(evidence, 'backend.log'), 'a');
  const processHandle = spawn(resolve(directory, '.runtime/venv/bin/python'), ['-m', modules[product]+'.cli', 'desktop', '--state-root', resolve(evidence, 'state'), '--port', String(port)], {
    cwd: directory, env: {...process.env, PYTHONPATH: [resolve(directory,'python'),resolve(root,'fpl-core/python')].join(':'), FPL_DESKTOP_LAUNCH_SECRET: secret}, stdio: ['ignore', log.fd, log.fd],
  });
  await log.close();
  let browser, page;
  try {
    browser = await chromium.launch({channel:'chrome', headless:true});
    const context = await browser.newContext({viewport:{width:1440,height:960}});
    for (let count=0; count<150; count++) {
      if (processHandle.exitCode !== null) throw Error('Product backend exited');
      try {if ((await context.request.get(origin+'/ready')).ok()) break;} catch {}
      await new Promise(resolve => setTimeout(resolve,200));
    }
    const session = await context.request.post(origin+'/__desktop/session', {headers:{Origin:origin,'x-fpl-launch':secret}});
    if (!session.ok()) throw Error('Product session bootstrap failed: '+await session.text());
    page = await context.newPage();
    await page.goto(origin+'/core/');
    const errors = [], websiteRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if (/\/v1\/(core\/)?(fpl-connection|creative-workshop)/.test(request.url())) websiteRequests.push(request.url());});
    await page.waitForURL('**/core/');
    await page.goto(new URL('/core/creative-workshop', page.url()).href);
    await page.getByRole('heading', {name: '创意工坊', exact: true}).waitFor();
    if (await page.getByText('登录 FPL', {exact: true}).count()) throw Error('Website login entry remains');
    if (await page.getByText('FPL 网站账号', {exact: true}).count()) throw Error('Creative page is gated by website account');
    await page.locator('.resource-card').first().waitFor({timeout: 90000});
    await page.getByRole('button', {name:'浅色',exact:true}).click();
    await page.screenshot({path: resolve(evidence, 'library-light.png')});
    await page.getByRole('button', {name: '深色', exact: true}).click();
    await page.setViewportSize({width: 860, height: 760});
    await page.screenshot({path: resolve(evidence, 'library-dark-narrow.png')});
    await page.setViewportSize({width: 1440, height: 960});
    await page.getByRole('textbox', {name: '搜索资源', exact: true}).fill('简历经历优化');
    await page.locator('.resource-card').filter({hasText: '简历经历优化'}).click();
    await page.getByRole('heading', {name: '简历经历优化', exact: true}).waitFor();
    const button = page.getByRole('button', {name: '一键导入', exact: true});
    await button.click();
    await page.getByRole('status').filter({hasText: '已导入'}).waitFor({timeout: 90000});
    await button.click();
    await page.getByRole('status').filter({hasText: '已导入'}).waitFor();
    const installed = await page.evaluate(async () => {
      const skills = await fetch('/v1/core/integrations/skills').then(r => r.json());
      const receipts = await fetch('/v1/core/resource-library/imports').then(r => r.json());
      return {skills: skills.items.filter(i => i.name === 'resume-bullet-writer'), receipts: receipts.items.filter(r=>r.source_id==='official')};
    });
    if (installed.skills.length !== 1 || installed.skills[0].enabled || installed.receipts.length !== 1) throw Error('Import was not disabled and idempotent');
    await page.screenshot({path: resolve(evidence, 'imported-skill.png')});
    await page.getByRole('button', {name: '已导入', exact: true}).click();
    await page.getByText('resume-bullet-writer', {exact: true}).waitFor();
    await page.getByRole('button', {name: '来源管理', exact: true}).click();
    await page.getByRole('heading', {name: 'GitHub 资源来源', exact: true}).waitFor();
    await page.screenshot({path: resolve(evidence, 'sources.png')});
    if (product === products[0]) {
      await page.getByRole('textbox',{name:'GitHub 链接',exact:true}).fill('https://github.com/EmiyaredA/fpl-resources/tree/'+installed.receipts[0].revision+'/skills/resume-bullet-writer');
      await page.getByRole('button',{name:'添加并浏览',exact:true}).click();
      await page.locator('.resource-card').filter({hasText:'简历经历优化'}).waitFor({timeout:90000});
      await page.locator('.resource-card').filter({hasText:'简历经历优化'}).click();
      await page.getByRole('textbox',{name:'导入名称 简历经历优化',exact:true}).fill('resume-github-directory');
      await page.getByRole('button',{name:'一键导入',exact:true}).click();
      await page.getByRole('status').filter({hasText:'已导入'}).waitFor({timeout:90000});
      const imported = await page.evaluate(async()=> (await fetch('/v1/core/integrations/skills').then(r=>r.json())).items.some(i=>i.name==='resume-github-directory' && !i.enabled));
      if (!imported) throw Error('Pasted GitHub directory import failed');
    }

    // The old website-account URL now leads to source management.
    await page.goto(new URL('/core/fpl-account', page.url()).href);
    await page.waitForURL('**/core/creative-workshop?view=sources');
    await page.getByRole('heading', {name: 'GitHub 资源来源', exact: true}).waitFor();
    if (errors.length || websiteRequests.length) throw Error(JSON.stringify({errors, websiteRequests}));
    const result = {product, passed: true, errors, websiteRequests, revision: installed.receipts[0].revision, disabledSkillImported: true, duplicateImportReusedReceipt: true};
    results.push(result);
    await writeFile(resolve(evidence, 'result.json'), JSON.stringify(result, null, 2));
    console.log(product + ': public GitHub catalog and real local import passed');
  } catch (error) {
    console.error(product, page?.url(), error);
    if (page) {await page.screenshot({path:resolve(evidence,'failure.png')});console.error((await page.locator('body').innerText()).slice(0,1500));}
    throw error;
  } finally {
    await browser?.close();
    processHandle.kill('SIGTERM');
    await Promise.race([new Promise(resolve=>processHandle.once('exit',resolve)),new Promise(resolve=>setTimeout(resolve,5000))]);
    if (processHandle.exitCode === null) processHandle.kill('SIGKILL');
  }
}
await writeFile(resolve(output, 'result.json'), JSON.stringify({passed: true, results}, null, 2));
