import {chromium} from 'playwright';
import fs from 'node:fs/promises';import path from 'node:path';import http from 'node:http';
import assert from 'node:assert/strict';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';
const root=process.env.TERRA_WEB||fileURLToPath(new URL('..',import.meta.url)).replaceAll('\\','/').replace(/\/$/,'');
const qa=process.env.TERRA_QA||root+'/qa-results';await fs.mkdir(qa,{recursive:true});
const report={version:'0.6.0',checks:[],errors:[],offlineRequests:[],externalRequests:[]};
const pass=(name,detail)=>{report.checks.push({name,pass:true,detail});console.log('PASS',name,detail||'');};
const server=http.createServer(async(req,res)=>{
 try{const url=new URL(req.url,'http://localhost'),file=path.resolve(root+'/site','.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));
 if(!file.startsWith(path.resolve(root+'/site')+path.sep))throw Error();
 const b=await fs.readFile(file);res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.webp':'image/webp','.glb':'model/gltf-binary'}[path.extname(file)]||'application/octet-stream'));res.end(b);
 }catch{res.statusCode=404;res.end('Missing');}
});await new Promise(ok=>server.listen(8850,'127.0.0.1',ok));
const browser=await chromium.launch({channel:'chrome',headless:true});
async function districtFrame(page,id){
 await page.waitForFunction(id=>document.querySelector('#courtyard-frame').contentWindow?.COURTYARD?.ready&&document.querySelector('#courtyard-frame').contentWindow.COURTYARD.inspect().district===id,id,{timeout:120000});
 return (await page.$('#courtyard-frame')).contentFrame();
}
try{
 const offline=await browser.newContext({viewport:{width:1360,height:950},offline:true});
 const page=await offline.newPage();page.on('pageerror',e=>report.errors.push(e.message));
 page.on('request',r=>{if(/^https?:/.test(r.url()))report.offlineRequests.push(r.url());});
 await page.goto('file:///'+root+'/dist/Terra_World_06.html');
 await page.waitForFunction(()=>window.TERRA_PREVIEW?.version==='0.6.0');
 assert(!/English/i.test(await page.locator('body').innerText()));pass('offline-language-neutral-home');
 for(const id of ['capital','bronze','neolithic']){
  await page.evaluate(id=>location.hash='district/'+id,id);const frame=await districtFrame(page,id);
  const state=await frame.evaluate(()=>COURTYARD.inspect());assert.equal(state.neighborhood.rooms,5);assert.equal(state.residents.agents.length,6);assert.equal(state.version,'0.6.0');
  assert.deepEqual(state.errors,[]);assert.equal(await frame.evaluate(()=>!!COURTYARD.debug),false);pass('offline-'+id+'-correct-era-rooms-and-residents');
 }
 let frame=await districtFrame(page,'neolithic');
 await frame.selectOption('#district-select','bronze');frame=await districtFrame(page,'bronze');
 assert.equal(await page.evaluate(()=>location.hash),'#district/bronze');pass('offline-district-selector');
 await frame.locator('#info-button').click();await frame.waitForSelector('#info',{state:'visible'});
 assert((await frame.locator('#info').innerText()).includes('geometric line of sight'));
 await frame.locator('#archive').click();await page.waitForFunction(()=>TERRA_PREVIEW.inspect().journey.selectedCity?.name==='Rikã̀žàval',{},{timeout:60000});
 assert.equal(await page.evaluate(()=>TERRA_PREVIEW.inspect().journey.selectedCity.year),-1500);pass('offline-era-correct-atlas-link');
 assert.deepEqual(report.offlineRequests,[]);pass('complete-districts-work-with-zero-network');await offline.close();
 const touch=await browser.newContext({viewport:{width:393,height:852},isMobile:true,hasTouch:true,deviceScaleFactor:2});
 const phone=await touch.newPage();phone.on('pageerror',e=>report.errors.push(e.message));
 phone.on('request',r=>{if(/^https?:/.test(r.url())&&!r.url().startsWith('http://127.0.0.1:8850/'))report.externalRequests.push(r.url());});
 await phone.goto('http://127.0.0.1:8850/#district/bronze');frame=await districtFrame(phone,'bronze');
 assert(await frame.locator('#stick').isVisible());assert(await frame.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));pass('touch-district-ui-layout');
 const cdp=await touch.newCDPSession(phone),rect=await frame.locator('#stick').boundingBox();
 const x=rect.x+rect.width/2,y=rect.y+rect.height/2,before=await frame.evaluate(()=>COURTYARD.inspect().player);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y,id:1}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:y-29,id:1}]});
 await phone.waitForTimeout(700);await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 const after=await frame.evaluate(()=>COURTYARD.inspect().player);assert(Math.hypot(after.x-before.x,after.z-before.z)>.5);pass('touch-district-movement');
 await frame.locator('#pause').tap();await frame.waitForFunction(()=>COURTYARD.inspect().paused);
 const time=await frame.evaluate(()=>COURTYARD.inspect().residents.time);await phone.waitForTimeout(350);
 assert.equal(await frame.evaluate(()=>COURTYARD.inspect().residents.time),time);await frame.locator('#resume').tap();pass('touch-pause-freezes-residents');
 for(const id of ['capital','neolithic']){await frame.selectOption('#district-select',id);frame=await districtFrame(phone,id);assert.equal(await frame.evaluate(()=>COURTYARD.inspect().residents.agents.length),6);}pass('touch-all-three-era-switches');
 await phone.setViewportSize({width:852,height:393});await phone.waitForTimeout(250);const stick=await frame.locator('#stick').boundingBox();
 assert(stick.y>=0&&stick.y+stick.height<=393);assert(await frame.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await phone.screenshot({path:qa+'/ThreeEras_Touch_Landscape.png'});pass('touch-landscape-controls-fit');
 await phone.setViewportSize({width:393,height:852});
 await phone.goto('http://127.0.0.1:8850/courtyard/index.html?era=neolithic&qa=1');
 await phone.waitForFunction(()=>window.COURTYARD?.ready,{},{timeout:120000});
 await phone.evaluate(()=>{const s=COURTYARD.debug.sim(),r=COURTYARD.debug.area().rooms[0];for(const a of s.agents){a.x=80+a.index;a.z=80;a.wait=9999;a.path=[];}COURTYARD.debug.position(r.outside.x,r.outside.z,r.rot);r.door.angle=0;r.door.target=0;s.updateDoors(0);});
 await phone.waitForFunction(()=>!document.querySelector('#interact').hidden&&document.querySelector('#interact').textContent.includes('Open'));assert((await phone.locator('#interact').textContent()).includes('Open'));
 await phone.locator('#interact').tap();await phone.waitForFunction(()=>COURTYARD.debug.area().doors[0].angle>1.4);pass('touch-opens-real-door');
 await phone.evaluate(()=>{const a=COURTYARD.debug.area(),r=a.rooms[0],o=a.objects.find(o=>o.kind==='storage'&&o.room===r.id);COURTYARD.debug.position(o.position.x,o.position.z,r.rot);});
 await phone.waitForFunction(()=>!document.querySelector('#interact').hidden&&document.querySelector('#interact').textContent.includes('Open'));assert((await phone.locator('#interact').textContent()).includes('Open'));
 await phone.locator('#interact').tap();await phone.waitForFunction(()=>COURTYARD.debug.area().objects[0].angle>.8);pass('touch-operates-storage-cover');
 await phone.evaluate(()=>{const s=COURTYARD.debug.sim(),a=s.agents[0];a.x=0;a.z=6;a.yaw=0;a.wait=9999;a.path=[];COURTYARD.debug.position(0,7.25,0);s.emit('used',{id:'player',name:'Visitor'},'the grinding bench',{x:.2,z:7,y:1.4});});
 await phone.waitForFunction(()=>!document.querySelector('#interact').hidden&&document.querySelector('#interact').textContent.includes('Talk to'));assert((await phone.locator('#interact').textContent()).includes('Talk to'));
 await phone.locator('#interact').tap();await phone.waitForSelector('#resident-dialog',{state:'visible'});
 await phone.locator('[data-topic="seen"]').tap();assert((await phone.locator('#resident-answer').textContent()).includes('grinding bench'));
 await phone.locator('#resident-close').tap();await phone.waitForSelector('#resident-dialog',{state:'hidden'});pass('touch-memory-conversation-and-close');
 assert.deepEqual(report.errors,[]);assert.deepEqual(report.externalRequests,[]);pass('no-district-offline-or-touch-script-errors');report.pass=true;
}catch(e){report.pass=false;report.failure=e.stack;console.log('FAIL',e.stack);}
finally{report.tested_html_sha256=createHash('sha256').update(await fs.readFile(root+'/dist/Terra_World_06.html')).digest('hex');await fs.writeFile(qa+'/QA_DISTRICT_UI.json',JSON.stringify(report,null,2));await browser.close();await new Promise(ok=>server.close(ok));}
if(!report.pass)process.exitCode=1;
