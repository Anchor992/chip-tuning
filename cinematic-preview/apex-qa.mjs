import {chromium} from './.build/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const out='cinematic-preview/apex-proof';await fs.mkdir(out,{recursive:true});
const report={testedAt:new Date().toISOString(),browser:'Chromium software WebGL, not physical iPhone Safari',screens:[],status:'running'};
const save=()=>fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
const watchdog=setTimeout(()=>{console.error('Browser check exceeded its bounded runtime');process.exit(1)},240000);watchdog.unref();
const browser=await chromium.launch({headless:true,timeout:30000,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
async function newPage(context){context.setDefaultTimeout(15000);context.setDefaultNavigationTimeout(20000);const page=await context.newPage();await page.route(/fonts\.(googleapis|gstatic)\.com/,route=>route.abort());return page}
async function jump(page,id,p){await page.evaluate(({id,p})=>{const el=document.getElementById(id);window.scrollTo({top:el.getBoundingClientRect().top+scrollY+Math.max(1,el.offsetHeight-innerHeight)*p,behavior:'instant'})},{id,p});await page.waitForTimeout(600)}
try{
for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
 const tag=viewport.width===390?'mobile':'desktop';console.log('CHECK',tag);
 const context=await browser.newContext({viewport,deviceScaleFactor:1,isMobile:tag==='mobile',hasTouch:tag==='mobile'});
 const page=await newPage(context),errors=[],failed=[],states=[];
 report.screens.push({tag,viewport,states,errors,failed});await save();
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('console',m=>{if(m.type()==='error'&&/Shader Error|WebGLProgram/.test(m.text()))errors.push(m.text())});
 page.on('response',r=>{if(r.url().includes('127.0.0.1')&&r.status()>=400)failed.push([r.status(),r.url()])});
 await page.goto('http://127.0.0.1:8765/apex.html',{waitUntil:'domcontentloaded'});
 console.log('DOM ready',tag);await page.waitForFunction(()=>window.CHECK92_APEX?.car==='ready',null,{timeout:30000});console.log('Car loaded',tag);
 for(const [id,kind] of [['drive','hero'],['circuit','circuit'],['about','intro'],['services','services'],['response','response'],['process','process'],['velocity','velocity']]){
  const shots=[];console.log('SCENE',tag,id);
  for(const p of [.15,.55,.88]){
   await jump(page,id,p);
   if(['about','services','process'].includes(id))await page.waitForFunction(()=>window.CHECK92_APEX?.engine==='ready',null,{timeout:30000});
   await page.waitForFunction(k=>window.CHECK92_APEX?.scene===k,kind,{timeout:15000});
   const state=await page.evaluate(()=>({...window.CHECK92_APEX,overflow:document.documentElement.scrollWidth>innerWidth+1}));
   assert.equal(state.overflow,false,tag+' '+id+' overflows');assert(state.frames>0&&state.triangles>0,'Real render required');shots.push(state);
   if(p===.55)await page.screenshot({path:path.join(out,`${tag}-${id}.png`),animations:'disabled',timeout:10000});
  }
  assert.notDeepEqual(shots[0].camera,shots[2].camera,id+' camera must move');assert(shots[2].frames>shots[0].frames,id+' frames must advance');states.push({id,shots});await save();
 }
 await jump(page,'start',.52);assert.equal(await page.locator('#gl').count(),1);await page.screenshot({path:path.join(out,`${tag}-ecu.png`),animations:'disabled',timeout:10000});
 console.log('FORMS',tag);await page.locator('#platform').scrollIntoViewIfNeeded();
 await page.getByRole('button',{name:'PORSCHE',exact:true}).click();await page.locator('#vehicle-model').selectOption('911');
 await page.locator('#vehicle-cta').click();await page.waitForTimeout(850);assert.equal(await page.locator('#car').inputValue(),'PORSCHE 911');
 await page.locator('#engine').fill('3.0 / 2021');await page.locator('#task').fill('Тест формы, не отправлять');
 await page.route('https://t.me/**',route=>route.abort());
 const handoff=page.waitForRequest(r=>r.url().includes('t.me/share/url'),{timeout:10000});await page.locator('#form button[type=submit]').click();
 const request=await handoff;assert(new URL(request.url()).searchParams.get('text').includes('PORSCHE 911'));
 assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);report.screens.at(-1).forms='selection and Telegram handoff passed; no message sent';await save();await context.close();
}
console.log('REDUCED MOTION');const ctx=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'}),page=await newPage(ctx);
await page.goto('http://127.0.0.1:8765/apex.html',{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.CHECK92_APEX?.car==='ready',null,{timeout:30000});
await jump(page,'services',.2);await page.waitForTimeout(500);assert(await page.locator('.service').evaluateAll(nodes=>nodes.every(n=>!n.inert)));report.reducedMotion='service content remains available';await ctx.close();
console.log('FALLBACK');const fallbackCtx=await browser.newContext({viewport:{width:390,height:844}});await fallbackCtx.addInitScript(()=>{const get=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return /webgl/.test(type)?null:get.call(this,type,...args)}});
const fp=await newPage(fallbackCtx);await fp.goto('http://127.0.0.1:8765/apex.html',{waitUntil:'domcontentloaded'});await fp.waitForFunction(()=>document.body.classList.contains('film-fallback'),null,{timeout:15000});assert.equal(await fp.locator('#vehicle-brands button').count(),8);report.noWebGL='fallback and catalog available';await fallbackCtx.close();
report.status='passed';
}catch(error){report.status='failed';report.error=String(error);console.error(error);process.exitCode=1}
finally{clearTimeout(watchdog);await save();await fs.writeFile('cinematic-preview/apex-build-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,error:report.error,screens:report.screens.map(s=>s.tag)},null,2));await browser.close()}
