import * as THREE from 'three';
import {localPoint,insideRoom} from './district-math.js';
export function buildNeighborhood(A,config) {
  const {world,mats,box,add,worldUV,ownMat,placeModel}=A;
  const rooms=[],doors=[],objects=[],solids=A.colliders;
  const solid=(x,z,w,d,rot,ymin,ymax)=>solids.push({type:'box',x,z,w:w/2,d:d/2,rot,ymin,ymax});
  const earth=ownMat(mats.earth.clone()),clay=ownMat(mats.clay.clone()),reed=ownMat(mats.thatch.clone());
  earth.normalScale.set(.6,.6);if(config.id==='bronze')earth.color.set('#9b987b');clay.normalScale.set(.65,.65);reed.side=THREE.DoubleSide;
  const wallmat=config.theme==='stone'?mats.pale:config.theme==='clay'?clay:clay;
  function piece(r,lx,ly,lz,w,h,d,mat,physical=false,bevel=.025) {
    const p=localPoint(r,lx,lz);box(p.x,ly,p.z,w,h,d,mat,r.rot,bevel);
    if(physical)solid(p.x,p.z,w,d,r.rot,ly-h/2,ly+h/2);
  }
  function roomWall(r,z,width,height,openings,mat) {
    const cuts=[-width/2,...openings.flatMap(o=>[o.x-o.w/2,o.x+o.w/2]),width/2].sort((a,b)=>a-b);
    for(let i=0;i<cuts.length-1;i++) {
      const lo=cuts[i],hi=cuts[i+1],middle=(lo+hi)/2;
      if(hi-lo<.02)continue;
      const opening=openings.find(o=>middle>o.x-o.w/2-.01&&middle<o.x+o.w/2+.01);
      if(!opening)piece(r,middle,height/2,z,hi-lo,height,.30,mat,true);
      else {
        if(opening.bottom>.03)piece(r,middle,opening.bottom/2,z,hi-lo,opening.bottom,.30,mat,true);
        const upper=height-opening.top;
        if(upper>.02)piece(r,middle,opening.top+upper/2,z,hi-lo,upper,.30,mat,true);
      }
    }
  }
  function windowFrame(r,x,z,w=.85) {
    const trim=config.theme==='stone'?mats.trim:mats.darkWood;
    for(const side of [-1,1])piece(r,x+side*(w/2+.07),1.6,z+.06,.13,.95,.28,trim);
    piece(r,x,1.16,z+.09,w+.32,.15,.39,trim);
    piece(r,x,2.04,z+.04,w+.30,.15,.24,trim);
    for(const side of [-1,1])piece(r,x+side*(w*.74+.08),1.62,z+.035,w*.4,.79,.09,mats.darkWood);
    piece(r,x,1.62,z+.055,.045,.78,.08,mats.darkWood);
  }
  function door(r,width=1.65) {
    const p=localPoint(r,0,r.d/2+.035),hinge=localPoint(r,-width/2,r.d/2+.035);
    const group=new THREE.Group();group.position.set(hinge.x,0,hinge.z);group.rotation.y=r.rot;
    const material=config.theme==='reed'?mats.linen:mats.wood;
    const geo=new THREE.BoxGeometry(width,2.08,.08);worldUV(geo,1.8);
    const leaf=new THREE.Mesh(geo,material);leaf.position.set(width/2,1.04,0);leaf.castShadow=true;leaf.receiveShadow=true;group.add(leaf);
    for(const h of [.38,1.62]){const brace=new THREE.Mesh(new THREE.BoxGeometry(width+.04,.10,.1),mats.darkWood);brace.position.set(width/2,h,.055);brace.castShadow=true;group.add(brace);}
    const handle=new THREE.Mesh(new THREE.TorusGeometry(.055,.012,6,14),mats.darkWood);handle.position.set(width-.15,1.1,.08);group.add(handle);
    world.add(group);
    const record={id:r.id+'-door',room:r.id,name:r.name,x:p.x,z:p.z,w:width,hinge,base:r.rot,angle:0,target:0,hold:0,mesh:group,requests:0,collider:{type:'box',x:p.x,z:p.z,w:width/2,d:.05,rot:r.rot,ymin:0,ymax:2.08}};
    r.door=record;doors.push(record);
    for(const side of [-1,1])piece(r,side*(width/2+.08),1.11,r.d/2,.15,2.22,.41,mats.darkWood);
    piece(r,0,2.20,r.d/2,width+.33,.18,.43,mats.darkWood);
  }
  function pitchedRoof(r,h,material) {
    const rise=config.theme==='stone'?1.15:.95;
    for(const side of [-1,1]){
      const v=[-r.w/2-.32,h,r.d/2*side+.38*side,r.w/2+.32,h,r.d/2*side+.38*side,r.w/2+.32,h+rise,0,-r.w/2-.32,h+rise,0];
      const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(v,3));g.setIndex(side>0?[0,1,2,0,2,3]:[0,2,1,0,3,2]);g.computeVertexNormals();worldUV(g,1.5);add(g,material,r.x,0,r.z,0,r.rot,0);
    }
  }
  function house(r) {
    const h=config.theme==='stone'?3.35:2.75;
    roomWall(r,r.d/2,r.w,h,[{x:0,w:1.7,bottom:0,top:2.12},{x:-r.w*.33,w:.85,bottom:1.23,top:1.96},{x:r.w*.33,w:.85,bottom:1.23,top:1.96}],wallmat);
    roomWall(r,-r.d/2,r.w,h,[{x:0,w:1.0,bottom:1.23,top:1.96}],wallmat);
    for(const side of [-1,1])piece(r,side*r.w/2,h/2,0,.30,h,r.d,wallmat,true);
    windowFrame(r,-r.w*.33,r.d/2);windowFrame(r,r.w*.33,r.d/2);
    piece(r,0,-.035,0,r.w,.09,r.d,config.theme==='stone'?mats.paving:earth);
    piece(r,0,h,0,r.w+.45,.18,r.d+.45,mats.darkWood);
    if(config.theme==='stone')pitchedRoof(r,h+.09,mats.roof);
    else {
      piece(r,0,h+.13,0,r.w+.36,.18,r.d+.36,clay);
      for(const side of [-1,1])piece(r,side*r.w/2,h+.34,0,.30,.38,r.d+.20,clay);
      for(let b=-r.w/2+.45;b<r.w/2;b+=.8)piece(r,b,h-.15,r.d/2+.22,.12,.16,.9,mats.darkWood);
    }
    door(r);r.height=h;
  }
  function hut(r) {
    const radius=r.w/2,h=2.35,segments=64,step=Math.PI*2/segments,gap=Math.asin(.86/radius);
    for(let i=0;i<segments;i++){
      const a=(i+.5)*step,p=localPoint(r,Math.sin(a)*radius,Math.cos(a)*radius),rot=r.rot+a;
      const nearFront=Math.abs(Math.atan2(Math.sin(a),Math.cos(a)))<gap;
      const window=Math.abs(a-Math.PI/2)<.16||Math.abs(a-3*Math.PI/2)<.16;
      const spans=nearFront?[[2.12,h]]:window?[[0,1.2],[1.95,h]]:[[0,h]];
      for(const [lo,hi]of spans){box(p.x,(lo+hi)/2,p.z,radius*step+.025,hi-lo,.20,clay,rot,.018);solid(p.x,p.z,radius*step+.025,.20,rot,lo,hi);}
      if(i%8===0){box(p.x,h/2,p.z,.11,h+.18,.14,mats.darkWood,rot,.02);}
    }
    const roof=new THREE.CylinderGeometry(.16,radius+.5,2.2,56,8,true);worldUV(roof,2);add(roof,reed,r.x,h+1.1,r.z,0,r.rot,0);
    const base=new THREE.CircleGeometry(radius,64);base.rotateX(-Math.PI/2);worldUV(base,2);add(base,earth,r.x,.015,r.z);
    door(r);r.height=h;
  }
  function interior(r,index) {
    const wx=r.w*.25,bx=-r.w*.28;
    piece(r,bx,.20,-.65,1.28,.3,2.12,mats.darkWood,true);
    piece(r,bx,.39,-.65,1.24,.18,2.10,mats.linen);
    piece(r,bx,.53,-1.32,.85,.15,.45,mats.linen);
    piece(r,wx,.88,-1.65,1.55,.14,1.30,mats.wood,true);
    for(const dx of [-.58,.58])for(const dz of [-.45,.45])piece(r,wx+dx,.4,-1.65+dz,.10,.8,.10,mats.darkWood,true);
    r.shelfY=r.round?1.7:2.13;piece(r,0,r.shelfY,-r.d/2+.26,r.w*(r.round?.30:.65),.12,.45,mats.wood);
    const chestX=r.round?0:bx,chestZ=-r.d/2+(r.round?1.0:.55);const lid=new THREE.Group(),chest=localPoint(r,chestX,chestZ);
    box(chest.x,.35,chest.z,1.15,.60,.68,mats.darkWood,r.rot,.045);
    solid(chest.x,chest.z,1.2,.74,r.rot,0,.7);
    const hinge=localPoint(r,chestX,chestZ-.33);lid.position.set(hinge.x,.68,hinge.z);lid.rotation.y=r.rot;
    const panel=new THREE.Mesh(new THREE.BoxGeometry(1.2,.08,.72),mats.wood);panel.position.z=.36;panel.castShadow=true;lid.add(panel);world.add(lid);
    objects.push({id:r.id+'-storage',kind:'storage',name:config.theme==='reed'?'grain basket cover':'storage chest',room:r.id,x:chest.x,z:chest.z,mesh:lid,angle:0,target:0,base:r.rot,position:localPoint(r,chestX,chestZ+.80)});
    const work=localPoint(r,wx,-1.18),tool=new THREE.Group();tool.position.set(work.x,.98,work.z);
    const bowlGeo=new THREE.LatheGeometry([new THREE.Vector2(.1,0),new THREE.Vector2(.22,.06),new THREE.Vector2(.3,.18),new THREE.Vector2(.28,.20),new THREE.Vector2(.12,.07)],24);
    const bowl=new THREE.Mesh(bowlGeo,config.theme==='stone'?mats.sandstone:clay);bowl.castShadow=true;tool.add(bowl);
    const pestle=new THREE.Mesh(new THREE.CapsuleGeometry(.035,.28,4,8),mats.darkWood);pestle.position.set(.03,.28,.02);pestle.rotation.z=.28;tool.add(pestle);world.add(tool);
    objects.push({id:r.id+'-work',kind:'work',name:index===1?'pottery bench':'grinding bench',room:r.id,x:work.x,z:work.z,mesh:pestle,active:0,position:localPoint(r,wx,-.4)});
    const lamp=localPoint(r,-r.w*.34,r.d*.18),light=new THREE.PointLight('#ffbd7a',9,6.5,2);light.position.set(lamp.x,1.7,lamp.z);world.add(light);
    piece(r,-r.w*.34,1.35,r.d*.18,.22,.12,.22,mats.wood);
    r.work=localPoint(r,wx,-.54);r.center=localPoint(r,0,-.20);r.outside=localPoint(r,0,r.d/2+1.6);
    r.inside=localPoint(r,0,r.d/2-1.4);r.sleep=localPoint(r,-.2,-1.8);
    r.window=r.round?localPoint(r,r.w/2,0):localPoint(r,r.w*.33,r.d/2);const insideLight=r.round?localPoint(r,r.w/2-.45,0):localPoint(r,r.w*.33,r.d/2-.45);const fill=new THREE.PointLight('#c3d7ea',5.5,5,2);fill.position.set(insideLight.x,1.65,insideLight.z);world.add(fill);
    if(index===0||index===3){
      for(const side of [-1,1])piece(r,-r.w*.27+side*.62,1.08,1.25,.10,2.1,.12,mats.darkWood,true);
      for(const y of [.13,1.97])piece(r,-r.w*.27,y,1.25,1.33,.11,.12,mats.darkWood);
      for(let thread=0;thread<21;thread++)piece(r,-r.w*.27-.56+thread*.056,1.05,1.25,.012,1.74,.012,mats.linen);
      piece(r,-r.w*.27,.85,1.27,1.1,.6,.014,mats.linen);
    }
  }
  function groundAndWater() {
    if(config.id==='capital'){A.floor();return;}
    const ground=new THREE.PlaneGeometry(62,62,100,100);ground.rotateX(-Math.PI/2);worldUV(ground,3.4);add(ground,earth,0,-.025,0);
    const water=new THREE.MeshPhysicalMaterial({color:config.id==='bronze'?'#527e70':'#6b8d82',roughness:.22,metalness:.12,transparent:true,opacity:.86,clearcoat:1});ownMat(water);
    const river=new THREE.PlaneGeometry(58,3.5,80,3);river.rotateX(-Math.PI/2);const mesh=add(river,water,0,.005,-23,0,0,0,false);mesh.name='River channel';
    solids.push({type:'box',x:-24,z:-23,w:5,d:1.8,rot:0,ymin:-2,ymax:.5},{type:'box',x:6.5,z:-23,w:22.5,d:1.8,rot:0,ymin:-2,ymax:.5});
    for(let i=0;i<100;i++){const z=-20.9-(i%2)*4.0,x=-28+i*.56;const rock=new THREE.IcosahedronGeometry(.17+(i%4)*.04,1);rock.scale(1.3,.6,1);add(rock,mats.sandstone,x,-.03,z);}
    const boards=6;for(let i=0;i<boards;i++)box(-18+i*.23,.11,-23,.22,.13,4.6,mats.wood,0,.015);
  }
  function villageDetails() {
    if(config.id==='capital'){A.fountain();A.market();return;}
    for(const side of [-1,1]){
      const z=3.8,x=side*7,table=new THREE.Group();
      box(x,.76,z,2.6,.16,1.15,mats.wood,0,.035);solid(x,z,2.6,1.15,0,0,.85);
      for(const dx of [-1,1])for(const dz of [-.35,.35])box(x+dx,.37,z+dz,.11,.75,.11,mats.darkWood);
      const canopy=new THREE.PlaneGeometry(3.8,2.7,18,12);canopy.rotateX(-Math.PI/2);const p=canopy.attributes.position,base=[];
      for(let i=0;i<p.count;i++){const y=.17*Math.cos(p.getX(i)*2.8);p.setY(i,y);base.push(y);}canopy.computeVertexNormals();
      const cloth=add(canopy,config.id==='bronze'?mats.linen:reed,x,2.7,z,0,0,0,false);cloth.userData.base=base;A.movingCloth.push(cloth);
      for(const dx of [-1.8,1.8])for(const dz of [-1.25,1.25])box(x+dx,1.4,z+dz,.11,2.8,.11,mats.darkWood);
    }
    const pit=new THREE.Group();for(let i=0;i<11;i++){const a=i/11*Math.PI*2;const g=new THREE.IcosahedronGeometry(.19,1);add(g,mats.sandstone,Math.sin(a)*.70,.15,Math.cos(a)*.70-1);}
    const embers=new THREE.Mesh(new THREE.CircleGeometry(.52,28),new THREE.MeshStandardMaterial({color:'#382015',emissive:'#ab4316',emissiveIntensity:1.0,roughness:1}));embers.rotation.x=-Math.PI/2;embers.position.set(0,.03,-1);world.add(embers);
    const fire=new THREE.PointLight('#ffa14d',5,7,2);fire.position.set(0,.7,-1);world.add(fire);solids.push({type:'circle',x:0,z:-1,r:.9,ymin:0,ymax:.7});
  }
  if(config.id!=='capital'){
    const terrain=new THREE.PlaneGeometry(240,240,80,80);terrain.rotateX(-Math.PI/2);
    const p=terrain.attributes.position;
    for(let i=0;i<p.count;i++){const x=p.getX(i),z=p.getZ(i),blend=Math.min(1,Math.max(0,(Math.hypot(x,z)-33)/60));p.setY(i,-.14+blend*(3.5+2.8*Math.sin(x*.035+1)*Math.cos(z*.042)));}
    terrain.computeVertexNormals();worldUV(terrain,4);const distant=ownMat(earth.clone());distant.color.set(config.id==='bronze'?'#727f55':'#bbaa86');add(terrain,distant);
  }
  groundAndWater();
  for(let i=0;i<config.roomLayout.length;i++){
    const [x,z,w,d,rot]=config.roomLayout[i],room={id:config.id+'-room-'+i,name:config.roomNames[i],x,z,w,d,rot,round:config.theme==='reed'};
    if(room.round)hut(room);else house(room);
    interior(room,i);rooms.push(room);
  }
  villageDetails();
  if(config.id==='capital'){
    for(const r of rooms){A.archFill(1.45,1.40,3.10,2.72,.38,mats.plaster,r.x,-8.6);A.archRing(r.x,-8.39,1.45,1.4,.42);solid(r.x-2.15,-8.6,1.12,.43,0,0,3.1);solid(r.x+2.15,-8.6,1.12,.43,0,0,3.1);box(r.x,3.12,-9.5,5.4,.16,2.1,mats.darkWood);}
    for(const side of [-1,1]){box(side*21,1.0,0,.45,2.0,37,mats.plaster);solid(side*21,0,.45,37,0,0,2);}
  }
  function populate() {
    const treePoints=config.id==='capital'?[[17,6,6],[-17,6,6],[-21,-21,8],[21,-21,8]]:config.id==='bronze'?[[-22,-13,9],[22,-13,9],[-22,15,7],[22,15,8]]:[[-21,14,5.5],[22,-16,5]];
    for(const [x,z,h]of treePoints)placeModel('tree',x,z,h,(x+z)*.19,true);if(config.id==='bronze'){for(const [x,z,h]of [[-31,-23,12],[-20,-31,11],[-7,-33,12],[9,-34,11],[25,-29,12],[33,-15,10],[30,20,11],[-30,20,12]])placeModel('tree',x,z,h,x*.12,false);}
    for(const r of rooms){const p=localPoint(r,r.w*.31,r.d/2+.72);placeModel('pot',p.x,p.z,.49,r.rot,true);}for(const r of rooms){for(const offset of [-.24,.20]){const p=localPoint(r,r.w*offset*(r.round?.44:1),-r.d/2+.26);const model=placeModel('pot',p.x,p.z,.24,r.rot,false);model.position.y=r.shelfY+.07;}}
    if(config.id==='capital')for(const [x,z]of [[-12,8],[11,8],[-18,-2]])placeModel('barrel',x,z,.92,.2,true);
    const reedMat=ownMat(mats.thatch.clone());reedMat.side=THREE.DoubleSide;
    if(config.id!=='capital'){
      const geo=new THREE.BufferGeometry(),v=[];
      for(let i=0;i<240;i++){const x=-24+(i%80)*.61,z=-20.8-Math.floor(i/80)*.18,h=.38+(i%7)*.09;v.push(x-.025,0,z,x+.025,0,z,x+.10,h,z+.07);}
      geo.setAttribute('position',new THREE.Float32BufferAttribute(v,3));geo.computeVertexNormals();worldUV(geo,1);add(geo,reedMat);
    }
  }
  const meeting=[{x:-1.0,z:5.5},{x:1.0,z:5.5},{x:-2.4,z:8},{x:2.4,z:8},{x:-1.5,z:1.5},{x:3.6,z:1.5}];
  return {rooms,doors,objects,solids,populate,meeting,config,
    roomAt:p=>rooms.find(r=>insideRoom(r,p,.3))||null,
    info:()=>({rooms:rooms.length,doors:doors.length,objects:objects.length,theme:config.theme})};
}
