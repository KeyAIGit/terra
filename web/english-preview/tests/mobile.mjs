import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import http from 'node:http';
import path from 'node:path';
const root=process.env.TERRA_WORKSPACE||process.cwd(),site=root+'/source/web/english-preview/site';
const report={checks:[],errors:[],externalRequests:[],mobileScenes:[]};
const pass=(name,detail)=>{report.checks.push({name,pass:true,detail});console.log('PASS',name,detail||'');};
const server=http.createServer(async(req,res)=>{try{const u=new URL(req.url,'http://localhost');const p=path.resolve(site,'.'+decodeURIComponent(u.pathname==='/ '?'/index.html':u.pathname));if(!p.startsWith(path.resolve(site)+path.sep)&&p!==path.resolve(site))throw Error();const f=u.pathname==='/'?site+'/index.html':p;const b=await fs.readFile(f);res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.webp':'image/webp','.json':'application/json','.gz':'application/gzip'}[path.extname(f)]||'application/octet-stream'));res.end(b);}catch{res.statusCode=404;res.end('Not found');}});
await new Promise(ok=>server.listen(8843,'127.0.0.1',ok));
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:2});
const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('404'))report.errors.push(m.text());});
page.on('request',r=>{if(/^https?:/.test(r.url())&&!r.url().startsWith('http://127.0.0.1:8843/'))report.externalRequests.push(r.url());});
await page.goto('http://127.0.0.1:8843/#walk/0');await page.waitForFunction(()=>document.querySelector('#walk-frame').contentWindow?.GAME?.ready,{},{timeout:40000});
const getFrame=()=>page.frames().find(f=>f.parentFrame());let frame=getFrame();assert(await frame.evaluate(()=>GAME.inspect().mobile));assert((await frame.locator('#terra-stick').isVisible()));pass('touch-controls-visible');
const cdp=await context.newCDPSession(page),rect=await frame.locator('#terra-stick').boundingBox(),x=rect.x+rect.width/2,y=rect.y+rect.height/2;
const before=await frame.evaluate(()=>GAME.inspect().player);
await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y,id:1}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:y-28,id:1}]});await page.waitForTimeout(650);await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
const after=await frame.evaluate(()=>GAME.inspect().player);assert(Math.hypot(after.x-before.x,after.z-before.z)>1);pass('real-touch-joystick-movement');
const canvas=await frame.locator('#c3d').boundingBox(),lx=canvas.x+canvas.width*.55,ly=canvas.y+canvas.height*.5,yaw=await frame.evaluate(()=>GAME.inspect().yaw);
await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:lx,y:ly,id:2}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:lx+65,y:ly+5,id:2}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});assert(Math.abs((await frame.evaluate(()=>GAME.inspect().yaw))-yaw)>.15);pass('touch-look');
await frame.locator('#terra-pause-button').tap();await page.waitForTimeout(100);console.log('PAUSE_STATE',await frame.evaluate(()=>({game:GAME.inspect(),hidden:document.getElementById('terra-pause').hidden})));const t0=await frame.evaluate(()=>GAME.inspect().time);await page.waitForTimeout(400);assert.equal(await frame.evaluate(()=>GAME.inspect().time),t0);assert(await frame.locator('#terra-pause').isVisible());await frame.locator('#terra-resume').tap();pass('pause-freezes-time');
await page.selectOption('#walk-quality','balanced');await page.waitForTimeout(100);assert.equal(await frame.evaluate(()=>GAME.inspect().quality),'balanced');pass('quality-setting');
await frame.evaluate(()=>{var n=GAME.someNPC();GAME.teleport(n.x+1,n.z+1);});await frame.locator('#terra-meet').tap();await frame.waitForSelector('#dlg',{state:'visible'});await frame.locator('#dtopics button').first().tap();assert((await frame.locator('.msg').count())>=3);await page.screenshot({path:root+'/qa/v03-touch-dialogue.png'});await frame.locator('#dclose').tap();pass('touch-meet-and-dialogue');
assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert(await frame.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));pass('mobile-no-horizontal-overflow');
for(let i=0;i<3;i++){
 if(i){await page.evaluate(i=>location.hash='walk/'+i,i);await page.waitForFunction(()=>document.querySelector('#walk-frame').contentWindow?.GAME?.ready,{},{timeout:30000});frame=getFrame();}
 await page.waitForTimeout(350);const state=await frame.evaluate(()=>GAME.inspect());assert.equal(state.npcCount,[34,30,23][i]);assert(state.canopyTrees>30);assert(state.streetProps>20);assert.equal(state.articulatedResidents,state.npcCount);assert.equal(state.archivedNPCs,0);assert.deepEqual(state.errors,[]);report.mobileScenes.push(state);await page.screenshot({path:root+'/qa/v03-touch-'+i+'.png'});pass('mobile-scene-'+i,{canopy:state.canopyTrees,props:state.streetProps,residents:state.npcCount});
}
await page.setViewportSize({width:844,height:390});await page.waitForTimeout(250);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));const stickBox=await frame.locator('#terra-stick').boundingBox();assert(stickBox.y>=0&&stickBox.y+stickBox.height<=390);await page.screenshot({path:root+'/qa/v03-touch-landscape.png'});pass('mobile-landscape-layout');
await page.evaluate(()=>location.hash='atlas');await page.waitForFunction(()=>TERRA_PREVIEW.inspect().world,{},{timeout:30000});assert(await page.evaluate(()=>TERRA_SELF_HOSTED));assert.deepEqual(report.externalRequests,[]);pass('self-hosted-no-external-runtime-dependencies');
assert.deepEqual(report.errors,[]);pass('no-javascript-or-shader-errors');report.host=await page.evaluate(()=>TERRA_PREVIEW.inspect());report.pass=true;
}catch(e){report.pass=false;report.failure=e.stack;console.error('FAIL',e.stack);}finally{await fs.writeFile(root+'/qa/QA03_EXTRA.json',JSON.stringify(report,null,2));await browser.close();await new Promise(ok=>server.close(ok));}
if(!report.pass)process.exitCode=1;
