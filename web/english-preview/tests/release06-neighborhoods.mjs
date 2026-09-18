import {chromium} from 'playwright';import {fileURLToPath} from 'node:url';
import fs from 'node:fs/promises';import path from 'node:path';import http from 'node:http';import assert from 'node:assert/strict';
const root=fileURLToPath(new URL('../courtyard',import.meta.url)).replaceAll(String.fromCharCode(92),'/'),qa=process.env.TERRA_QA||root+'/../qa-results';await fs.mkdir(qa,{recursive:true});
const server=http.createServer(async(req,res)=>{try{const u=new URL(req.url,'http://localhost'),file=path.resolve(root,'.'+(u.pathname==='/'?'/index.html':u.pathname));if(!file.startsWith(path.resolve(root)+path.sep))throw Error();const b=await fs.readFile(file);res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.webp':'image/webp','.glb':'model/gltf-binary'}[path.extname(file)]||'application/octet-stream'));res.end(b);}catch{res.statusCode=404;res.end('Missing');}});await new Promise(ok=>server.listen(8849,'127.0.0.1',ok));
const report={version:'0.6.0',checks:[],errors:[],consoleErrors:[],districts:[]};
const pass=(name,detail)=>{report.checks.push({name,pass:true,detail});console.log('PASS',name,detail||'');};
const browser=await chromium.launch({channel:'chrome',headless:true}),page=await browser.newPage({viewport:{width:1440,height:960}});
page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.consoleErrors.push(m.text());});
try{
 for(const era of ['capital','bronze','neolithic']){
  await page.goto('http://127.0.0.1:8849/?era='+era+'&qa=1');await page.waitForFunction(()=>window.COURTYARD?.ready,{},{timeout:120000});
  const initial=await page.evaluate(()=>COURTYARD.inspect());assert.equal(initial.district,era);assert.equal(initial.neighborhood.rooms,5);assert.equal(initial.residents.agents.length,6);assert.equal(initial.historyChanged,false);
  pass(era+'-five-interiors-six-residents');await page.waitForTimeout(1000);await page.screenshot({path:qa+'/View_'+era+'.png'});
  await page.evaluate(()=>{const s=COURTYARD.debug.sim();for(const a of s.agents){a.x=90+a.index;a.z=90;a.wait=9999;a.path=[];}});
  for(let i=0;i<5;i++){
    const prepared=await page.evaluate(i=>{const r=COURTYARD.debug.area().rooms[i],s=COURTYARD.debug.sim(),d=r.door;d.target=0;d.angle=0;d.hold=0;s.updateDoors(0);const ok=COURTYARD.debug.position(r.outside.x,r.outside.z,r.rot);return {ok,id:r.id,name:r.name,closed:s.nav.clear(r.outside,r.inside,.25,true)};},i);
    assert(prepared.ok);assert.equal(prepared.closed,false);await page.waitForTimeout(250);assert((await page.locator('#interact').textContent()).includes('Open'));
    await page.keyboard.press('e');await page.waitForFunction(i=>COURTYARD.debug.area().doors[i].angle>1.4,i,{timeout:4000});
    await page.locator('#view').click({position:{x:700,y:500}});await page.keyboard.down('w');await page.waitForTimeout(2400);await page.keyboard.up('w');
    await page.waitForTimeout(200);assert((await page.locator('#room-label').textContent()).includes(prepared.name));
    const storage=await page.evaluate(i=>{const a=COURTYARD.debug.area(),r=a.rooms[i],o=a.objects.find(o=>o.room===r.id&&o.kind==='storage');return {ok:COURTYARD.debug.position(o.position.x,o.position.z,r.rot),id:o.id};},i);assert(storage.ok);await page.waitForTimeout(200);
    assert((await page.locator('#interact').textContent()).includes('Open'));await page.keyboard.press('e');await page.waitForFunction(id=>COURTYARD.debug.area().objects.find(o=>o.id===id).angle>.8,storage.id,{timeout:3000});
    const work=await page.evaluate(i=>{const a=COURTYARD.debug.area(),r=a.rooms[i],o=a.objects.find(o=>o.room===r.id&&o.kind==='work');return {ok:COURTYARD.debug.position(r.work.x,r.work.z,r.rot),id:o.id};},i);assert(work.ok);await page.waitForTimeout(200);await page.keyboard.press('e');await page.waitForFunction(id=>COURTYARD.debug.area().objects.find(o=>o.id===id).active>0,work.id);
    if(i===0)await page.screenshot({path:qa+'/Interior_'+era+'.png'});
    pass(era+'-room-'+i+'-door-entry-storage-work');
  }
  const perception=await page.evaluate(()=>{
    const s=COURTYARD.debug.sim(),r=s.area.rooms[0],local=(x,z)=>({x:r.x+Math.cos(r.rot)*x+Math.sin(r.rot)*z,z:r.z-Math.sin(r.rot)*x+Math.cos(r.rot)*z,y:1.55});
    const d=r.door;d.angle=0;d.target=0;d.hold=0;s.updateDoors(0);
    const outside={...r.outside,y:1.55,yaw:r.rot+Math.PI},inside={...r.inside,y:1.55};
    const closed=s.visible(outside,inside);d.target=1.507964;d.angle=d.target;d.hold=s.time+50;s.updateDoors(0);
    const open=s.visible(outside,inside),back=s.visible({...outside,yaw:r.rot},inside);
    const wx=r.round?r.w/2:r.w*.33;
    const a=r.round?local(wx+.7,0):local(wx,r.d/2+.65),b=r.round?local(wx-.7,0):local(wx,r.d/2-.65);
    const throughWindow=s.nav.sight(a,b),throughWall=r.round?s.nav.sight(local(-r.w*.354-.5,-r.w*.354-.5),local(-r.w*.354+.5,-r.w*.354+.5)):s.nav.sight(local(-r.w/2-.65,0),local(-r.w/2+.65,0));
    return {closed,open,back,throughWindow,throughWall};
  });
  assert.equal(perception.closed,false);assert.equal(perception.open,true);assert.equal(perception.back,false);assert.equal(perception.throughWindow,true);
  assert.equal(perception.throughWall,false);pass(era+'-door-window-wall-and-view-direction',perception);
  await page.reload();await page.waitForFunction(()=>window.COURTYARD?.ready,{},{timeout:120000});
  const behavior=await page.evaluate(()=>{
    COURTYARD.pause(true);const s=COURTYARD.debug.sim();let penetrations=0,maxSpeed=0;
    for(let i=0;i<4800;i++){s.tick(.05,{x:99,z:99,y:1.65,yaw:0});for(const a of s.agents){if(s.nav.blocked(a.x,a.z,.245,true))penetrations++;maxSpeed=Math.max(maxSpeed,a.speed);}}
    COURTYARD.debug.advance(.05);return {state:s.inspect(),penetrations,maxSpeed,witnessed:s.agents.reduce((sum,a)=>sum+a.observations.filter(e=>e.source==='line of sight').length,0)};
  });
  assert.equal(behavior.penetrations,0);assert(behavior.maxSpeed<1.1);assert(behavior.state.agents.every(a=>a.entries>0&&a.work>0&&a.distanceWalked>20));assert(behavior.state.stats.conversations>0);assert(behavior.state.stats.observations>0);assert(behavior.witnessed>0);
  report.districts.push({era,...behavior});pass(era+'-four-minute-resident-routines',behavior.state.stats);
  const talk=await page.evaluate(()=>{const s=COURTYARD.debug.sim(),a=s.agents[0];for(let i=0;i<24;i++){const angle=i/24*Math.PI*2,p={x:a.x+Math.cos(angle)*.85,z:a.z+Math.sin(angle)*.85,y:1.65,yaw:0};if(!s.nav.blocked(p.x,p.z,.24,true)&&s.nav.sight(p,a)){s.player=p;return s.talk(a);}}return null;});
  assert(talk&&talk.name);assert.equal(talk.note.includes('no language-model calls'),true);pass(era+'-local-memory-dialogue');
 }
 assert.deepEqual(report.errors,[]);assert.deepEqual(report.consoleErrors,[]);pass('no-runtime-or-shader-errors');report.pass=true;
}catch(e){report.pass=false;report.failure=e.stack;console.log('FAIL',e.stack);await page.screenshot({path:qa+'/Failure.png'}).catch(()=>{});}
finally{await fs.writeFile(qa+'/QA_NEIGHBORHOODS.json',JSON.stringify(report,null,2));await browser.close();await new Promise(ok=>server.close(ok));}
if(!report.pass)process.exitCode=1;
