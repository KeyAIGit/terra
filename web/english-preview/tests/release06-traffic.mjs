import fs from 'node:fs/promises';import {fileURLToPath} from 'node:url';import assert from 'node:assert/strict';
import {ResidentSimulation} from '../courtyard/resident-sim.js';import {insideRoom} from '../courtyard/district-math.js';
const root=fileURLToPath(new URL('..',import.meta.url)),qa=process.env.TERRA_QA||root+'/qa-results';
await fs.mkdir(qa,{recursive:true});const report={version:'0.6.0',checks:[],scenarios:[],pass:false};
try{
 for(const era of ['capital','bronze','neolithic'])for(const variant of ['50ms','60hz','variable']){
  const area=JSON.parse(await fs.readFile(new URL('./fixtures06/'+era+'.json',import.meta.url)));
  for(const r of area.rooms)r.door=area.doors.find(d=>d.room===r.id);
  for(const o of area.objects)o.mesh={rotation:{x:0,z:0}};
  area.roomAt=p=>area.rooms.find(r=>insideRoom(r,p,.3))||null;
  const sim=new ResidentSimulation(area);sim.updateDoors(0);let step=0,overlaps=0,pairs=0;const stages=[];
  while(sim.time<600){const dt=variant==='50ms'?.05:variant==='60hz'?1/60:[.012,.04,.018,.03][step%4];step++;
   sim.tick(dt,{x:99,z:99,y:1.65,yaw:0});
   for(const a of sim.agents){if(sim.nav.blocked(a.x,a.z,.245,true))overlaps++;assert(Number.isFinite(a.x)&&Number.isFinite(a.z));}
   for(let i=0;i<6;i++)for(let j=i+1;j<6;j++)if(Math.hypot(sim.agents[i].x-sim.agents[j].x,sim.agents[i].z-sim.agents[j].z)<.50)pairs++;
   if(sim.time>=(stages.length+1)*120)stages.push({time:sim.time,arrivals:sim.agents.map(a=>a.arrivals),work:sim.agents.map(a=>a.completedWork)});
  }
  const state=sim.inspect();report.scenarios.push({era,variant,steps:step,overlaps,pairs,stages,stats:sim.stats,agents:state.agents});
  assert.equal(overlaps,0,era+' '+variant+' scenery overlap');assert.equal(pairs,0,era+' '+variant+' body overlap');
  assert(state.agents.every(a=>a.entries>=2&&a.work>=2&&a.distanceWalked>80),era+' '+variant+' unfinished routine');
  assert(stages[4].arrivals.every((n,i)=>n>stages[2].arrivals[i]),era+' '+variant+' resident stopped progressing');
  assert(sim.stats.conversations>0,era+' '+variant+' no conversation');
  report.checks.push({name:era+'-'+variant+'-ten-minute-traffic',pass:true});console.log('PASS',era,variant,sim.stats.arrivals,sim.stats.conversations);
 }
 report.pass=true;
}catch(e){report.failure=e.stack;console.error('FAIL',e.stack);}
await fs.writeFile(qa+'/QA_TRAFFIC.json',JSON.stringify(report,null,2));if(!report.pass)process.exitCode=1;
