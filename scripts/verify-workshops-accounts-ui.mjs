import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const base=process.env.WORKSHOPS_WORKSPACE,core=process.env.WORKSHOPS_CORE_REPO||base+'/fpl-core',task=process.env.WORKSHOPS_TEST_ROOT;
const {chromium}=await import(pathToFileURL(core+'/web/node_modules/@playwright/test/index.mjs'));
const state=JSON.parse(await readFile(task+'/browser-state.json','utf8'));
const browser=await chromium.launch({channel:'chrome',headless:true});
const report=[];
try{
 for(const app of [...state.apps,{slug:'dsh-core',port:19310,route:'/apps',editor:'/account',cookies:state.core_cookies}]){
  const context=await browser.newContext({viewport:{width:1440,height:960}});await context.addCookies(app.cookies);
  const page=await context.newPage();page.setDefaultTimeout(20000);
  const errors=[],failed=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.status()>=400&&r.url().startsWith('http://127.0.0.1:'+app.port+'/v1/'))failed.push(r.status()+' '+new URL(r.url()).pathname)});
  await page.goto('http://127.0.0.1:'+app.port+app.route);await page.waitForLoadState('networkidle');
  if(app.slug==='dsh-thought-workshop')await page.getByText('独立知识库验收',{exact:true}).first().waitFor();
  const body=await page.locator('body').innerText();assert.ok(body.length>100&& !body.includes('页面加载失败'),app.slug+' index '+body);
  const favicon=await page.locator('link[rel="icon"]').getAttribute('href');assert.ok(favicon,app.slug+' favicon');
  const icon=await context.request.get('http://127.0.0.1:'+app.port+favicon);assert.equal(icon.status(),200);assert.ok(icon.headers()['content-type'].startsWith('image/'));
  await page.screenshot({path:task+'/'+app.slug+'-index-light.png',fullPage:true});
  const dark=page.getByRole('button',{name:'深色',exact:true});if(await dark.count())await dark.first().click();
  await page.screenshot({path:task+'/'+app.slug+'-index-dark.png',fullPage:true});
  await page.goto('http://127.0.0.1:'+app.port+app.editor);await page.waitForLoadState('networkidle');
  if(app.slug==='dsh-thought-workshop')await page.locator('[contenteditable="true"]').first().waitFor();
  if(app.slug==='dsh-core')await page.getByRole('heading',{name:'账号管理',exact:true}).waitFor();
  if(app.slug==='dsh-video-editor')await page.locator('.ve-editor-shell').first().waitFor();
  const text=await page.locator('body').innerText();assert.ok(!text.includes('页面加载失败')&&!text.includes('页面不存在'),app.slug+' editor '+text);
  await page.screenshot({path:task+'/'+app.slug+'-editor-wide.png',fullPage:true});
  for(const width of [860,390]){await page.setViewportSize({width,height:960});await page.screenshot({path:task+'/'+app.slug+'-editor-'+width+'.png',fullPage:true});}
  report.push({slug:app.slug,errors,failed,index:true,editor:true,favicon:true});await context.close();
 }
}finally{await browser.close()}
await writeFile(task+'/ui-result.json',JSON.stringify(report,null,2));
assert.ok(report.every(r=>!r.errors.length&&!r.failed.length),JSON.stringify(report));
console.log('SEVEN_SERVICE_UI_PASSED');
