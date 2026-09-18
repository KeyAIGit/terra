import test from 'node:test';import assert from 'node:assert/strict';
import {localPoint,toLocal,insideRoom,overlaps,occludes} from '../courtyard/district-math.js';
import {DistrictNav} from '../courtyard/district-nav.js';
import {ResidentSimulation} from '../courtyard/resident-sim.js';
test('local and world coordinates round-trip for all district rotations',()=>{
 for(const rot of [0,.15,-.15,Math.PI/2,-Math.PI/2]){const room={x:11,z:-9,rot,w:7,d:7};for(const p of [{x:0,z:0},{x:1.2,z:-3.1},{x:-2,z:1}]){const world=localPoint(room,p.x,p.z),back=toLocal(room,world);assert(Math.abs(back.x-p.x)<1e-12);assert(Math.abs(back.z-p.z)<1e-12);}}
});
test('round hut does not treat its corner as an interior',()=>{
 const r={x:0,z:0,rot:0,w:6,d:6,round:true};assert(insideRoom(r,{x:0,z:0}));assert(!insideRoom(r,{x:2.8,z:2.8}));
});
test('low pottery does not block a head-height sight ray',()=>{
 const a={x:0,z:-2,y:1.55},b={x:0,z:2,y:1.55};assert(!occludes({x:0,z:0,w:.3,d:.3,rot:0,ymin:0,ymax:.55},a,b));assert(occludes({x:0,z:0,w:.3,d:.3,rot:0,ymin:0,ymax:2},a,b));
});
test('window aperture transmits sight but its wall below does not',()=>{
 const low={x:0,z:0,w:1,d:.15,ymin:0,ymax:1.2},high={...low,ymin:1.96,ymax:3};
 assert(!occludes(low,{x:0,z:-1,y:1.55},{x:0,z:1,y:1.55}));assert(!occludes(high,{x:0,z:-1,y:1.55},{x:0,z:1,y:1.55}));assert(occludes(low,{x:0,z:-1,y:.5},{x:0,z:1,y:.5}));
});
test('navigation routes around solid walls without clipping its corners',()=>{
 const nav=new DistrictNav([-6,6,-6,6],[{x:0,z:0,w:3,d:.25,ymin:0,ymax:3}],[]);const start={x:0,z:-4},end={x:0,z:4},route=nav.path(start,end);assert(route?.length>1);let p=start;for(const q of route){assert(nav.clear(p,q,.27,false));p=q;}assert(Math.hypot(p.x-end.x,p.z-end.z)<1e-8);
});
test('a shut door blocks actual motion while a future open footprint is planned',()=>{
 const door={base:0,w:1.6,hinge:{x:-.8,z:0},collider:{x:0,z:0,w:.8,d:.05,rot:0,ymin:0,ymax:2.1}};
 const nav=new DistrictNav([-3,3,-3,3],[],[door]);assert(nav.blocked(0,0,.25,true));assert(!nav.blocked(0,0,.25,false));assert(nav.blocked(-.8,-.8,.25,false));
});
test('residents have limited range and a forward field of view',()=>{
 const s=Object.create(ResidentSimulation.prototype);s.nav=new DistrictNav([-30,30,-30,30],[],[]);
 const a={x:0,z:0,y:1.55,yaw:0};assert(s.visible(a,{x:0,z:3,y:1.55}));assert(!s.visible(a,{x:0,z:-3,y:1.55}));assert(!s.visible(a,{x:0,z:13,y:1.55}));
});
test('unseen events do not enter the observation memory',()=>{
 const wall={x:0,z:0,w:2,d:.15,ymin:0,ymax:3},a={id:'a',name:'A',x:0,z:-2,y:1.55,yaw:0,observations:[]};
 const s=Object.create(ResidentSimulation.prototype);Object.assign(s,{nav:new DistrictNav([-8,8,-8,8],[wall],[]),agents:[a],events:[],sequence:0,time:0,stats:{observations:0}});
 s.emit('used',{id:'visitor',name:'Visitor'},'a bowl',{x:0,z:2});assert.equal(a.observations.length,0);
 wall.disabled=true;s.emit('used',{id:'visitor',name:'Visitor'},'a bowl',{x:0,z:2});assert.equal(a.observations.length,1);assert.equal(a.observations[0].source,'line of sight');
});
test('observations remain bounded and local',()=>{
 const a={id:'a',name:'A',x:0,z:0,y:1.55,yaw:0,observations:[]},s=Object.create(ResidentSimulation.prototype);
 Object.assign(s,{nav:new DistrictNav([-8,8,-8,8],[],[]),agents:[a],events:[],sequence:0,time:0,stats:{observations:0}});
 for(let i=0;i<30;i++)s.emit('used',{id:'visitor',name:'Visitor'},'a bowl',{x:0,z:2});assert.equal(a.observations.length,12);assert.equal(a.observations[0].id,19);
});
test('contact replanning leaves personal space without moving through a neighbor',()=>{
 const nav=new DistrictNav([-6,6,-6,6],[],[]);
 const start={x:-2.159,z:7.459-6},neighbor={x:-2.382,z:7.952-6},target={x:3,z:3};
 const route=nav.path(start,target,[neighbor]);assert(route&&route.length);
 let a=start;
 for(const b of route){
  const dx=b.x-a.x,dz=b.z-a.z,L=dx*dx+dz*dz;
  const t=Math.max(0,Math.min(1,((neighbor.x-a.x)*dx+(neighbor.z-a.z)*dz)/(L||1)));
  const minimum=Math.hypot(neighbor.x-a.x-t*dx,neighbor.z-a.z-t*dz);
  assert(minimum>=.53);assert(nav.clear(a,b,.27,false));a=b;
 }
 assert(Math.hypot(a.x-target.x,a.z-target.z)<1e-6);
});
test('household access is ordered and releases after leaving its doorway',()=>{
 const s=Object.create(ResidentSimulation.prototype),r={id:'home',x:0,z:0,w:5,d:6,rot:0,door:{x:0,z:3}};
 const a={id:'a',x:0,z:0,goal:{room:'home'}},b={id:'b',x:5,z:5};
 Object.assign(s,{area:{rooms:[r]},agents:[a,b],householdOwners:new Map(),householdQueues:new Map()});
 assert(s.requestHousehold(a,'home'));assert(!s.requestHousehold(b,'home'));
 a.goal={kind:'social'};a.x=0;a.z=3.5;s.releaseHouseholds();assert(!s.requestHousehold(b,'home'));
 a.z=7;s.releaseHouseholds();assert(s.requestHousehold(b,'home'));assert.equal(s.householdOwners.get('home'),'b');
});
