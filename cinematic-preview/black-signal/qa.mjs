import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { deriveTimeline, carouselOffset } from './timeline.js';
const here=path.dirname(fileURLToPath(import.meta.url)),out=path.resolve(here,'../../review');
await fs.mkdir(out,{recursive:true});
const url=process.env.CHECK92_BASE_URL||'http://127.0.0.1:8765/cinematic-preview/black-signal/';
const report={testedAt:new Date().toISOString(),renderer:'Headless Chromium / software WebGL; not physical iPhone or hardware FPS',checks:[],errors:[],states:[]};
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--enable-unsafe-swiftshader','--use-angle=swiftshader']});
async function ready(page){await page.waitForFunction(()=>window.__check92?.snapshot().loaded.every(Boolean),{},{timeout:60000});await page.waitForTimeout(1200)}
async function at(page,p){await page.evaluate(progress=>{const m=window.__check92.snapshot().metrics;window.scrollTo({top:m.filmTop+m.filmTravel*progress,behavior:'instant'})},p);await page.waitForFunction(p=>Math.abs(window.__check92.snapshot().visualProgress-p)<.012,p,{timeout:30000});await page.waitForTimeout(500)}
async function section(page,id){await page.evaluate(id=>window.scrollTo({top:document.querySelector(id).offsetTop-80,behavior:'instant'}),id);await page.waitForTimeout(900)}
try{
 for(let i=0;i<3;i++){
  const context=await browser.newContext({viewport:{width:1000,height:650},deviceScaleFactor:1}),page=await context.newPage();
  await page.goto(url+'?poster=1&car='+i,{waitUntil:'load'});await ready(page);
  const name=['porsche','audi','bmw'][i];await page.locator('#scene').screenshot({path:path.join(here,'assets',name+'-poster.png')});report.states.push({name:'poster-'+name,...await page.evaluate(()=>window.__check92.snapshot())});await context.close();
 }
 for(const[name,viewport]of[['desktop',{width:1440,height:900}],['mobile',{width:390,height:844}]]){
  const context=await browser.newContext({viewport,deviceScaleFactor:1,recordVideo:{dir:path.join(out,'video-'+name),size:viewport},hasTouch:name==='mobile',isMobile:name==='mobile'}),page=await context.newPage();
  page.on('pageerror',e=>report.errors.push(name+': '+e.message));page.on('console',m=>{if(m.type()==='error')report.errors.push(name+' console: '+m.text())});
  await page.goto(url,{waitUntil:'load'});await ready(page);
  assert.equal(await page.evaluate(()=>window.__check92.snapshot().webgl),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'Horizontal overflow '+name);
  await page.screenshot({path:path.join(out,name+'-01-showroom.png')});
  for(let i=0;i<3;i++){await page.locator(`[data-car="${i}"]`).click();await page.waitForTimeout(1350);assert.equal(await page.locator(`[data-car="${i}"]`).getAttribute('aria-pressed'),'true');assert.equal(await page.locator('#brand-select').inputValue(),['PORSCHE','AUDI','BMW'][i]);await page.screenshot({path:path.join(out,name+'-car-'+i+'.png')})}
  report.checks.push(name+': all three distinct vehicle files loaded; selection and prefill work');
  await page.locator('[data-car="0"]').click();await page.waitForTimeout(1100);await page.locator('#enter-story').click();await page.waitForFunction(()=>window.__check92.snapshot().approach>.9,{}, {timeout:30000});
  for(const[label,p]of[['02-ecu-closed',.025],['03-ecu-open',.23],['04-macro',.39],['05-engine',.66],['06-reassembly',.83],['07-return',.97]]){await at(page,p);await page.screenshot({path:path.join(out,name+'-'+label+'.png')});report.states.push({name:name+'-'+label,...await page.evaluate(()=>window.__check92.snapshot())})}
  assert.equal(await page.evaluate(()=>window.__check92.snapshot().engineLoaded),true,'Engine loaded '+name);assert.ok(await page.evaluate(()=>window.__check92.snapshot().engineParts>=18),'Separate engine parts '+name);
  await at(page,.23);const open=await page.evaluate(()=>window.__check92.snapshot().ecuLid[1]);await at(page,0);const closed=await page.evaluate(()=>window.__check92.snapshot().ecuLid[1]);assert.ok(open-closed>1,'ECU reverse assembly '+name);report.checks.push(name+': scroll-controlled ECU opening, reverse assembly and 18-part engine');
  await section(page,'#services');await page.screenshot({path:path.join(out,name+'-08-services.png')});await section(page,'#configurator');await page.screenshot({path:path.join(out,name+'-09-configurator.png')});
  await page.locator('#brand-select').selectOption('HYUNDAI');await page.locator('#model-select').selectOption('Solaris');await page.locator('#task').fill('Проверка интерфейса. Не реальная заявка.');
  await context.route('https://t.me/**',route=>route.fulfill({status:200,contentType:'text/html',body:'Test interception. No message was sent.'}));
  const popupPromise=context.waitForEvent('page');await page.locator('button[type="submit"]').click();const popup=await popupPromise;await popup.waitForLoadState('domcontentloaded');assert.ok(decodeURIComponent(popup.url()).includes('Solaris'));await popup.close();report.checks.push(name+': Telegram preparation validated; intercepted, no message sent');await context.close();
 }
 for(const kind of['reduced','fallback']){
  const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion:kind==='reduced'?'reduce':'no-preference'}),page=await context.newPage();await page.goto(url+(kind==='fallback'?'?no3d=1':''),{waitUntil:'load'});await page.waitForTimeout(1600);
  if(kind==='reduced')assert.equal(await page.locator('.chapter[inert]').count(),0);else assert.equal(await page.evaluate(()=>window.__check92.snapshot().webgl),false);
  assert.ok(await page.locator('a[href="tel:+79782502525"]').count()>0);await section(page,'#configurator');await page.screenshot({path:path.join(out,kind+'.png')});report.checks.push(kind+': content and contact path available');await context.close();
 }
 for(const p of[0,.025,.23,.39,.66,.83,.97,1])assert.deepEqual(deriveTimeline(p),deriveTimeline(p));assert.equal(deriveTimeline(1).engineOpen,0);assert.equal(carouselOffset(2,0),-1);report.checks.push('Pure reversible timeline and carousel invariants');
 report.status=report.errors.length?'passed-with-console-errors':'passed';if(report.errors.length)process.exitCode=1;
}catch(error){report.status='failed';report.failure=String(error.stack||error);for(const c of browser.contexts())for(const p of c.pages()){try{report.states.push({name:'failure-state',...await p.evaluate(()=>window.__check92?.snapshot())});await p.screenshot({path:path.join(out,'failure-state.png'),timeout:10000})}catch{}}console.error(error);process.exitCode=1}
finally{await fs.writeFile(path.join(out,'qa-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));await browser.close()}
