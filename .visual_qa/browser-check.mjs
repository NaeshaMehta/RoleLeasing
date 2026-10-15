import {chromium} from 'file:///C:/Users/arkob/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const out=new URL('./',import.meta.url);await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:'C:/Users/arkob/AppData/Local/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-win64/chrome-headless-shell.exe'});
const page=await browser.newPage({viewport:{width:1500,height:1100},deviceScaleFactor:1});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const response=await page.goto('http://127.0.0.1:4174');assert.equal(response.status(),200);
await page.waitForSelector('#networkCanvas');await page.screenshot({path:fileURLToPath(new URL('placement.png',out)),fullPage:true});
for(let i=0;i<4;i++)await page.getByRole('button',{name:'Next phase →',exact:true}).click();
assert.match(await page.locator('#leaseMetric').innerText(),/56/);
await page.getByRole('tab',{name:'Hierarchy',exact:true}).click();await page.screenshot({path:fileURLToPath(new URL('hierarchy.png',out)),fullPage:true});
await page.getByRole('button',{name:'Skip to live',exact:true}).click();await page.getByRole('tab',{name:'Field map',exact:true}).click();
await page.getByRole('button',{name:'Drain holder',exact:true}).click();await page.getByRole('button',{name:'Step 1 tick →',exact:true}).click();assert.equal(await page.locator('#handoverBanner').isVisible(),true);
await page.screenshot({path:fileURLToPath(new URL('handover.png',out)),fullPage:true});
await page.getByRole('button',{name:'Step 1 tick →',exact:true}).click();assert.ok(Number(await page.locator('#migrationMetric').innerText())>0);
await page.getByRole('button',{name:'Replay stale grant',exact:true}).click();assert.match(await page.locator('#eventFeed').innerText(),/Stale epoch 0 grant rejected/);
await page.getByRole('button',{name:'Inspect current role holder ↗',exact:true}).click();await page.getByRole('button',{name:'Fail selected node',exact:true}).click();assert.match(await page.locator('#entityStatus').innerText(),/Failed/);
for(let i=0;i<3;i++)await page.getByRole('button',{name:'Step 1 tick →',exact:true}).click();
await page.getByRole('button',{name:'Recover selected',exact:true}).click();assert.match(await page.locator('#entityStatus').innerText(),/Online/);
await page.getByRole('button',{name:'Join a new node',exact:true}).click();assert.match(await page.locator('#activeMetric').innerText(),/61/);
await page.getByRole('button',{name:'Compare all 3 policies · 120 ticks',exact:true}).click();await page.waitForSelector('#comparison tbody tr');assert.equal(await page.locator('#comparison tbody tr').count(),3);
const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'Export run ↓',exact:true}).click();const download=await downloadPromise;assert.match(download.suggestedFilename(),/role-leasing-seed-42-tick-/);
await page.screenshot({path:fileURLToPath(new URL('live-desktop.png',out)),fullPage:true});
for(const width of [390,768,1024]){await page.setViewportSize({width,height:1000});await page.waitForTimeout(120);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Horizontal overflow at ${width}`);await page.screenshot({path:fileURLToPath(new URL(`width-${width}.png`,out)),fullPage:true});}
await page.getByRole('button',{name:'Model notes',exact:true}).click();assert.equal(await page.locator('#aboutDialog').isVisible(),true);await page.getByRole('button',{name:'Close',exact:true}).click();
await page.setViewportSize({width:1500,height:1100});await page.locator('#sizeInput').selectOption('10');await page.getByRole('button',{name:'↻ Rebuild world',exact:true}).click();await page.getByRole('button',{name:'Skip to live',exact:true}).click();assert.match(await page.locator('#activeMetric').innerText(),/100/);
assert.deepEqual(errors,[]);await browser.close();console.log('Browser checks passed: phases, maps, migration, failure/recovery, fencing, joins, comparison, export, 3 responsive widths, and 100 nodes.');




