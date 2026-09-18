import {DistrictNav} from './district-nav.js';
import {distance,angleDifference,insideRoom,overlaps} from './district-math.js';
export class ResidentSimulation {
  constructor(area){
    this.area=area;this.nav=new DistrictNav(area.config.bounds,area.solids,area.doors);
    this.householdOwners=new Map();this.householdQueues=new Map();this.time=0;this.events=[];this.sequence=0;this.paused=false;
    this.stats={arrivals:0,entries:0,work:0,conversations:0,observations:0,doorOpens:0,blockedSteps:0};
    this.agents=area.config.residents.map((p,i)=>{
      const start=area.meeting[i],home=area.rooms[i%area.rooms.length];
      const neighbor=area.rooms[(i+1)%area.rooms.length];
      return {...p,index:i,x:start.x,z:start.z,y:1.5,yaw:Math.PI,home:home.id,
        agenda:[{...home.work,kind:'work',room:home.id,wait:7},{...start,kind:'social',wait:12},
          {...neighbor.center,kind:'visit',room:neighbor.id,wait:6},{...area.meeting[(i+2)%6],kind:'social',wait:10},
          {...home.center,kind:'rest',room:home.id,wait:7}],task:i%5,path:[],pathIndex:0,
        wait:i*.55,talking:0,chatCooldown:0,state:'starting',speed:0,distanceWalked:0,
        gait:0,observations:[],lastRoom:null,arrivals:0,entries:0,completedWork:0,speech:'',speechUntil:0,noticed:false,bodyScale:1};
    });
    this.player={id:'player',name:'Visitor',x:99,z:99,y:1.65,yaw:0};
    this.nav.build();
    for(const a of this.agents)if(this.nav.blocked(a.x,a.z,.27,false))throw Error('Resident spawn overlaps scenery: '+a.name);
  }
  visible(observer,target,range=12){
    const d=distance(observer,target);if(d>range||d<.001)return d<.001;
    const dx=(target.x-observer.x)/d,dz=(target.z-observer.z)/d;
    const dot=Math.sin(observer.yaw||0)*dx+Math.cos(observer.yaw||0)*dz;
    return dot>Math.cos(Math.PI*.40)&&this.nav.sight(observer,target);
  }
  emit(action,actor,subject,point){
    const e={id:++this.sequence,time:this.time,action,actor:actor.id||actor.name,name:actor.name||'Visitor',subject,x:point.x,z:point.z,y:1.4};
    this.events.push(e);if(this.events.length>250)this.events.shift();
    for(const a of this.agents){
      if(a.id!==e.actor&&!this.visible(a,e))continue;
      a.observations.push({...e,source:a.id===e.actor?'own action':'line of sight'});
      if(a.observations.length>12)a.observations.shift();this.stats.observations++;
    }
    return e;
  }
  doorRequest(door,actor,open=true){
    if(!open){
      const occupied=[...this.agents,this.player].some(p=>distance(p,door.hinge)<door.w+.42);
      if(occupied)return {ok:false,reason:'Someone is in the doorway’s swing area.'};
    }
    const changed=open?door.target<.1:door.target>.1;
    door.target=open?Math.PI*.48:0;door.hold=this.time+(open?8:0);
    if(changed){door.pendingActor={id:actor.id,name:actor.name};door.pendingAction=open?'opened':'closed';door.requests++;}
    return {ok:true,open};
  }
  updateDoors(dt){
    for(const d of this.area.doors){
      if(d.target>0&&this.time>d.hold){if(![...this.agents,this.player].some(a=>distance(a,d.hinge)<d.w+.65))d.target=0;}
      const delta=d.target-d.angle,candidate=d.angle+Math.sign(delta)*Math.min(Math.abs(delta),dt*1.9),rotation=d.base+candidate;
      const sweep={...d.collider,x:d.hinge.x+Math.cos(rotation)*d.w/2,z:d.hinge.z-Math.sin(rotation)*d.w/2,rot:rotation};
      d.obstructed=Math.abs(delta)>.001&&[...this.agents,this.player].some(a=>overlaps(sweep,a.x,a.z,.30));
      if(!d.obstructed)d.angle=candidate;
      const rot=d.base+d.angle;Object.assign(d.collider,{x:d.hinge.x+Math.cos(rot)*d.w/2,z:d.hinge.z-Math.sin(rot)*d.w/2,rot});
      if(d.mesh)d.mesh.rotation.y=rot;if(d.pendingAction&&((d.pendingAction==='opened'&&d.angle>.25)||(d.pendingAction==='closed'&&d.angle<.05))){this.emit(d.pendingAction,d.pendingActor,d.name+' door',d);if(d.pendingAction==='opened')this.stats.doorOpens++;d.pendingAction=null;}
    }
  }
  releaseHouseholds(){
    for(const [id,owner]of this.householdOwners){
      const a=this.agents.find(a=>a.id===owner),r=this.area.rooms.find(r=>r.id===id);
      if(!a||(a.goal?.room!==id&&!insideRoom(r,a)&&distance(a,r.door)>2.8))this.householdOwners.delete(id);
    }
  }
  requestHousehold(a,id){
    if(this.householdOwners.get(id)===a.id)return true;
    if(!this.householdQueues.has(id))this.householdQueues.set(id,[]);
    const queue=this.householdQueues.get(id);if(!queue.includes(a.id))queue.push(a.id);
    if(this.householdOwners.has(id)||queue[0]!==a.id)return false;
    queue.shift();this.householdOwners.set(id,a.id);return true;
  }
  plan(a){
    let goal={...a.agenda[a.task]};
    if(goal.room&&!this.requestHousehold(a,goal.room)){a.state='waiting to visit';a.wait=.75;a.speed=0;return;}
    if(this.agents.some(b=>b!==a&&(distance(b,goal)<.70||(b.goal&&b.path.length&&distance(b.goal,goal)<.70)))){
      for(let k=0;k<12;k++){const t=k*Math.PI/6,p={...goal,x:goal.x+Math.cos(t)*.75,z:goal.z+Math.sin(t)*.75};
        if(!this.nav.blocked(p.x,p.z,.30,false)&&!this.agents.some(b=>b!==a&&(distance(b,p)<.65||(b.goal&&b.path.length&&distance(b.goal,p)<.65)))){goal=p;break;}}
    }
    const path=this.nav.path(a,goal,a.stalled>2?this.agents.filter(b=>b!==a&&distance(a,b)<5):[]);
    if(!path){if(goal.room&&this.householdOwners.get(goal.room)===a.id&&!insideRoom(this.area.rooms.find(r=>r.id===goal.room),a))this.householdOwners.delete(goal.room);a.state='waiting for a clear route';a.wait=1.5;return;}
    a.goal=goal;a.path=path;a.pathIndex=0;a.state='walking';a.stalled=0;
  }
  move(a,dt){
    const next=a.path[a.pathIndex];if(!next)return;
    let waitingForDoor=false;
    for(const d of this.area.doors)if(distance(a,d)<2.3){this.doorRequest(d,a,true);if(d.angle<Math.PI*.48-.00001)waitingForDoor=true;}
    if(waitingForDoor){a.speed=0;return;}
    const dx=next.x-a.x,dz=next.z-a.z,d=Math.hypot(dx,dz);
    if(d<.075){a.pathIndex++;if(a.pathIndex>=a.path.length)this.arrive(a);return;}
    const aim=Math.atan2(dx,dz),turn=angleDifference(aim,a.yaw);
    a.yaw+=Math.sign(turn)*Math.min(Math.abs(turn),dt*3.0);
    const speed=(a.age>60?.71:.95)*Math.max(.15,1-Math.abs(turn)/Math.PI);
    const step=Math.min(d,dt*speed),p={x:a.x+dx/d*step,z:a.z+dz/d*step};
    const crowd=(p)=>this.agents.some(b=>b!==a&&distance(b,p)<.54)||distance(this.player,p)<.52;
    let allowed=!this.nav.blocked(p.x,p.z,.27,true)&&!crowd(p);
    if(!allowed&&crowd(p)&&a.stalled>.4){
      const sign=a.index%2?1:-1,side={x:a.x+dz/d*dt*.38*sign,z:a.z-dx/d*dt*.38*sign};
      if(!this.nav.blocked(side.x,side.z,.29,true)&&!crowd(side)){p.x=side.x;p.z=side.z;allowed=true;}
    }
    if(allowed){const dist=distance(a,p);a.x=p.x;a.z=p.z;a.speed=dist/dt;a.distanceWalked+=dist;a.gait+=dist/.84*Math.PI*2;a.stalled=0;}
    else{a.speed=0;a.stalled+=dt;this.stats.blockedSteps++;if(a.stalled>3.5){a.path=[];a.wait=.5;a.state='yielding';}}
  }
  arrive(a){
    a.path=[];a.speed=0;a.state=a.goal.kind;a.wait=a.goal.wait;a.arrivals++;this.stats.arrivals++;
    if(a.goal.kind==='work'){
      const object=this.area.objects.find(o=>o.kind==='work'&&o.room===a.goal.room);
      if(object){object.active=7;a.yaw=Math.atan2(object.x-a.x,object.z-a.z);}
      a.completedWork++;this.stats.work++;this.emit('worked at',a,object?.name||'the work area',a);
    }
    a.task=(a.task+1)%a.agenda.length;
  }
  conversations(){
    for(const a of this.agents){
      if(a.state!=='social'||a.talking>0)continue;
      const other=this.agents.filter(b=>b!==a&&b.state==='social'&&distance(a,b)<3.2).sort((b,c)=>distance(a,b)-distance(a,c))[0];
      if(!other)continue;a.yaw=Math.atan2(other.x-a.x,other.z-a.z);
      if(other.talking>0||a.chatCooldown>0||other.chatCooldown>0)continue;
      other.yaw=Math.atan2(a.x-other.x,a.z-other.z);
      if(!this.visible(a,other)||!this.visible(other,a))continue;
      a.talking=6;other.talking=6;a.chatCooldown=20;other.chatCooldown=20;
      a.speech='The work is ready. Shall we meet here again?';other.speech='Yes. I will finish my visit first.';
      a.speechUntil=this.time+6;other.speechUntil=this.time+6;
      a.partner=other.id;other.partner=a.id;this.stats.conversations++;
      this.emit('spoke with',a,other.name,a);
    }
  }
  tick(dt,player=this.player){
    if(this.paused)return;dt=Math.min(.10,Math.max(0,dt));this.time+=dt;this.player={...player,id:'player',name:'Visitor'};
    this.releaseHouseholds();this.updateDoors(dt);
    for(const a of this.agents){
      a.chatCooldown=Math.max(0,a.chatCooldown-dt);a.noticed=this.visible(a,this.player,7);
      if(a.talking>0){a.talking=Math.max(0,a.talking-dt);a.speed=0;}
      else if(a.path.length)this.move(a,dt);
      else if(a.wait>0){a.wait=Math.max(0,a.wait-dt);a.speed=0;}
      else this.plan(a);
      const room=this.area.roomAt(a),id=room?.id||null;
      if(id!==a.lastRoom){
        if(room){a.entries++;this.stats.entries++;this.emit('entered',a,room.name,a);}
        else if(a.lastRoom){const old=this.area.rooms.find(r=>r.id===a.lastRoom);this.emit('left',a,old?.name||'a home',a);}
        a.lastRoom=id;
      }
    }
    this.conversations();
    for(const o of this.area.objects){
      if(o.kind==='storage'){o.angle+=(o.target-o.angle)*Math.min(1,dt*5);o.mesh.rotation.x=-o.angle;}
      if(o.kind==='work'){o.active=Math.max(0,o.active-dt);o.mesh.rotation.z=.28+(o.active>0?Math.sin(this.time*7)*.22:0);}
    }
  }
  interactObject(o){
    if(o.kind==='storage'){o.target=o.target>.2?0:1.05;this.emit(o.target?'opened':'closed',this.player,o.name,o);return o.target?'The cover opens.':'The cover closes.';}
    o.active=3;this.emit('used',this.player,o.name,o);return 'You work the tool against the bowl.';
  }
  talk(a){
    if(distance(a,this.player)>3||!this.nav.sight(a,this.player))return null;
    a.yaw=Math.atan2(this.player.x-a.x,this.player.z-a.z);
    const seen=a.observations.filter(e=>e.source==='line of sight').slice(-3);
    return {id:a.id,name:a.name,role:a.role,age:a.age,state:a.state,home:this.area.rooms.find(r=>r.id===a.home)?.name,
      memories:seen.map(e=>'I witnessed this: '+e.name+' '+e.action+' '+e.subject+'.'),note:'Reconstructed resident. Local rules and line-of-sight memory; no language-model calls.'};
  }
  inspect(){return {time:this.time,stats:{...this.stats},nav:{searches:this.nav.searches,failures:this.nav.failures},householdOwners:Object.fromEntries(this.householdOwners),agents:this.agents.map(a=>({id:a.id,name:a.name,x:a.x,z:a.z,yaw:a.yaw,state:a.state,speed:a.speed,room:a.lastRoom,entries:a.entries,arrivals:a.arrivals,work:a.completedWork,memories:a.observations.length,noticed:a.noticed,distanceWalked:a.distanceWalked})),doors:this.area.doors.map(d=>({id:d.id,angle:d.angle,target:d.target,requests:d.requests})),events:this.events.slice(-30)};}
}
