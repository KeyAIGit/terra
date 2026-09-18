import * as THREE from 'three';
const Y=new THREE.Vector3(0,1,0);
const skinColors=['#b88969','#c29a7d','#967056','#d2ac89','#a77755','#b18d70'];
export async function createResidentVisuals(world,simulation,materials,asset){
  const data=await(await fetch(asset('assets/resident-head.json'))).json();
  const headGeometry=new THREE.BufferGeometry();headGeometry.setAttribute('position',new THREE.Float32BufferAttribute(data.positions,3));headGeometry.setIndex(data.indices);headGeometry.setAttribute('uv',new THREE.Float32BufferAttribute(data.uv,2));headGeometry.computeVertexNormals();
  const loader=new THREE.TextureLoader();
  const skins=await Promise.all(['young','mature'].map(n=>loader.loadAsync(asset('assets/head-'+n+'.webp'))));
  for(const t of skins)t.colorSpace=THREE.SRGBColorSpace;
  const hairAssets=[];
  for(const name of ['short02','short04']){const d=await(await fetch(asset('assets/hair-'+name+'.json'))).json();const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(d.positions,3));g.setAttribute('uv',new THREE.Float32BufferAttribute(d.uv,2));g.setIndex(d.indices);g.computeVertexNormals();const map=await loader.loadAsync(asset('assets/hair-'+name+'.webp'));map.colorSpace=THREE.SRGBColorSpace;hairAssets.push({g,map});}
  const hairIndices=[];
  for(let i=0;i<data.indices.length;i+=3){const ids=data.indices.slice(i,i+3);if(ids.every(j=>{const x=data.positions[j*3],y=data.positions[j*3+1],z=data.positions[j*3+2];return y>(z>.085?.215:Math.abs(x)>.085?.145:.13);}))hairIndices.push(...ids);}
  const hairGeometry=headGeometry.clone();hairGeometry.setIndex(hairIndices);hairGeometry.computeVertexNormals();
  const residents=[],audit={maxPlantedFootDrift:0,groundContacts:0,anatomicalHeadVertices:data.positions.length/3};
  function segment(material,radius){const profile=[[-.5,.64],[-.37,.74],[-.12,1.04],[.13,1.12],[.36,.95],[.5,.83]].map(([y,r])=>new THREE.Vector2(radius*r,y));const m=new THREE.Mesh(new THREE.LatheGeometry(profile,16),material);m.castShadow=true;m.receiveShadow=true;return m;}
  function connect(mesh,a,b){mesh.position.copy(a).add(b).multiplyScalar(.5);mesh.quaternion.setFromUnitVectors(Y,b.clone().sub(a).normalize());mesh.scale.y=a.distanceTo(b);}
  for(const a of simulation.agents){
    const root=new THREE.Group();world.add(root);const scale=.97+(a.index%4)*.025;root.scale.setScalar(scale);a.bodyScale=scale;
    const cloth=materials.linen.clone();cloth.color.set(['#c4ac80','#9a785b','#b58f68','#687465','#9c6d57','#b9b09a'][a.index]);cloth.side=THREE.DoubleSide;
    const skin=new THREE.MeshStandardMaterial({color:skinColors[a.index],roughness:.83});
    const hair=new THREE.MeshStandardMaterial({color:a.age>55?'#686259':['#30231a','#433425','#22251f'][a.index%3],roughness:1});
    const torso=new THREE.Group();root.add(torso);
    const profile=[[.56,.275,.18],[.71,.255,.17],[.88,.20,.15],[1.05,.20,.15],[1.22,.23,.15],[1.35,.235,.14],[1.40,.11,.08]],positions=[],uv=[],indices=[],N=48;
    for(let j=0;j<profile.length;j++){const [y,rx,rz]=profile[j];for(let k=0;k<=N;k++){const t=k/N*Math.PI*2,fold=1+.026*Math.cos(t*11+j*.25);positions.push(Math.sin(t)*rx*fold,y,Math.cos(t)*rz*fold);uv.push(k/N*2,j/profile.length*2);}}
    for(let j=0;j<profile.length-1;j++)for(let k=0;k<N;k++){const i=j*(N+1)+k;indices.push(i,i+N+1,i+1,i+1,i+N+1,i+N+2);}
    const tunicGeo=new THREE.BufferGeometry();tunicGeo.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));tunicGeo.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));tunicGeo.setIndex(indices);tunicGeo.computeVertexNormals();
    const tunic=new THREE.Mesh(tunicGeo,cloth);tunic.castShadow=true;tunic.receiveShadow=true;torso.add(tunic);
    const belt=new THREE.Mesh(new THREE.TorusGeometry(.202,.018,8,40),hair);belt.rotation.x=Math.PI/2;belt.scale.y=.72;belt.position.y=.95;torso.add(belt);
    const head=new THREE.Group();head.position.y=1.40;torso.add(head);
    const faceMaterial=skin.clone();faceMaterial.map=skins[a.age>48?1:0];faceMaterial.color.set('#e5d4c1');const face=new THREE.Mesh(headGeometry,faceMaterial),scalp=new THREE.Mesh(hairGeometry,hair);face.castShadow=true;scalp.castShadow=true;scalp.scale.set(1.018,1.012,1.018);head.add(face,scalp);const ha=hairAssets[a.index%2],hm=new THREE.MeshStandardMaterial({map:ha.map,color:a.age>55?'#a69f93':'#44352b',roughness:.94,alphaTest:.43,side:THREE.DoubleSide});const hairstyle=new THREE.Mesh(ha.g,hm);hairstyle.castShadow=true;head.add(hairstyle);
    const eyes=[];
    for(const eye of data.eyes){
      const white=new THREE.Mesh(new THREE.SphereGeometry(.012,12,8),new THREE.MeshStandardMaterial({color:'#dfdbcd',roughness:.35}));white.position.fromArray(eye);white.position.z+=.002;head.add(white);
      const iris=new THREE.Mesh(new THREE.CircleGeometry(.0053,16),new THREE.MeshStandardMaterial({color:'#463c27',roughness:.4}));iris.position.copy(white.position);iris.position.z+=.0115;head.add(iris);eyes.push(white);
    }
    const legs=[],arms=[];
    for(const side of [-1,1]){
      const thigh=segment(cloth,.075),shin=segment(skin,.050),upper=segment(cloth,.065),forearm=segment(skin,.044);
      const foot=new THREE.Mesh(new THREE.SphereGeometry(1,12,8),hair);foot.scale.set(.068,.045,.145);foot.castShadow=true;
      const hand=new THREE.Mesh(new THREE.SphereGeometry(1,10,8),skin);hand.scale.set(.036,.067,.023);hand.castShadow=true;
      root.add(thigh,shin,foot,upper,forearm,hand);
      legs.push({side,thigh,shin,foot,anchor:null,lastWorld:null,wasStance:false,swingStart:null});
      arms.push({side,upper,forearm,hand});
    }
    residents.push({a,root,torso,head,eyes,legs,arms,scale});
  }
  const V=(x,y,z)=>new THREE.Vector3(x,y,z);
  function inWorld(r,p){return p.clone().multiplyScalar(r.scale).applyAxisAngle(Y,r.a.yaw).add(V(r.a.x,0,r.a.z));}
  function inLocal(r,p){return p.clone().sub(V(r.a.x,0,r.a.z)).applyAxisAngle(Y,-r.a.yaw).divideScalar(r.scale);}
  function knee(hip,ankle){
    const delta=ankle.clone().sub(hip),d=Math.min(.88,Math.max(.02,delta.length())),dir=delta.normalize();
    const mid=hip.clone().addScaledVector(dir,d/2),bend=V(0,0,1).addScaledVector(dir,-dir.z).normalize();
    return mid.addScaledVector(bend,Math.sqrt(Math.max(.002,.45*.45-d*d/4)));
  }
  function update(dt,time,player){
    for(const r of residents){const {a,root,torso,head}=r;root.position.set(a.x,0,a.z);root.rotation.y=a.yaw;
      const moving=a.speed>.04;torso.position.y=moving?Math.sin(a.gait*2)*.009:Math.sin(time*1.2+a.index)*.003;
      torso.rotation.x=a.state==='work'&&!moving?.10:0;
      if(a.noticed&&!moving){const angle=Math.atan2(player.x-a.x,player.z-a.z)-a.yaw;head.rotation.y=Math.max(-.65,Math.min(.65,Math.atan2(Math.sin(angle),Math.cos(angle))));}else head.rotation.y*=Math.exp(-dt*4);
      const blink=(time+a.index*.6)%4.8<.10;for(const eye of r.eyes)eye.scale.y=blink?.12:1;
      for(const leg of r.legs){
        const phase=((a.gait/(Math.PI*2)+(leg.side<0?.5:0))%1+1)%1,stance=!moving||phase<.60;
        const neutral=inWorld(r,V(leg.side*.125,.055,moving?.22:.04));neutral.y=.055*r.scale;
        if(!leg.anchor){leg.anchor=neutral.clone();leg.swingStart=neutral.clone();}
        if(stance&&!leg.wasStance){leg.anchor=neutral.clone();audit.groundContacts++;}
        let ankle;
        if(stance){ankle=leg.anchor.clone();if(leg.wasStance&&leg.lastWorld)audit.maxPlantedFootDrift=Math.max(audit.maxPlantedFootDrift,ankle.distanceTo(leg.lastWorld));leg.swingStart=ankle.clone();}
        else{const t=(phase-.60)/.40,blend=t*t*(3-2*t);ankle=leg.swingStart.clone().lerp(neutral,blend);ankle.y+=Math.sin(Math.PI*t)*.115*r.scale;}
        leg.wasStance=stance;leg.lastWorld=ankle.clone();const local=inLocal(r,ankle),hip=V(leg.side*.125,.845,0),joint=knee(hip,local);
        connect(leg.thigh,hip,joint);connect(leg.shin,joint,local);leg.foot.position.copy(local);leg.foot.position.z+=.055;
        leg.foot.rotation.x=!stance?Math.sin(phase*Math.PI*2)*.13:0;
      }
      for(const arm of r.arms){const swing=moving?Math.sin(a.gait+(arm.side<0?Math.PI:0))*.18:0;
        const working=a.state==='work'&&!moving,chatting=a.talking>0;
        const shoulder=V(arm.side*.255,1.30,0),elbow=V(arm.side*.30,working?1.08:1.01,working?.23:swing*.55);
        const hand=V(arm.side*(working?.18:.285),working?1.01+Math.sin(time*7)*.04:chatting?1.13:.75,working?.48:chatting?.24:-swing);
        connect(arm.upper,shoulder,elbow);connect(arm.forearm,elbow,hand);arm.hand.position.copy(hand);arm.hand.rotation.x=working?-.8:0;
      }
    }
  }
  return {update,inspect:()=>({...audit,residents:residents.length}),roots:residents};
}
