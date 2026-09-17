import * as THREE from 'three';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RGBELoader} from 'three/addons/loaders/RGBELoader.js';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';
import {mergeGeometries} from 'three/addons/utils/BufferGeometryUtils.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {SSAOPass} from 'three/addons/postprocessing/SSAOPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';

const $=id=>document.getElementById(id);
const mobile=matchMedia('(pointer:coarse)').matches;
const audit={version:'0.5.0',ready:false,errors:[],assetsLoaded:[],walkableArea:'capital-market-courtyard',historyChanged:false,modelNames:[],photorealism:'work-in-progress'};
window.COURTYARD={inspect:()=>({...audit}),ready:false};
const asset=p=>window.COURTYARD_ASSETS?.[p]||p;
const scene=new THREE.Scene();
const renderer=new THREE.WebGLRenderer({canvas:$('view'),antialias:true,powerPreference:'high-performance'});
renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.toneMapping=THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure=1.17;
renderer.info.autoReset=false;renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.setPixelRatio(Math.min(devicePixelRatio||1,mobile?1.15:1.6));
scene.background=new THREE.Color('#cbd8df');
scene.fog=new THREE.FogExp2('#cbd4d6',.004);
const camera=new THREE.PerspectiveCamera(58,1,.08,240);
camera.rotation.order='YXZ';
const world=new THREE.Group();scene.add(world);
const colliders=[],occluders=[],merges=new Map(),materials=[],textures=[],movingCloth=[];
const manager=new THREE.LoadingManager();
manager.onProgress=(url,done,total)=>{$('progress').textContent=`Preparing materials and objects ${done} / ${total}`;};
manager.onError=url=>audit.errors.push('Asset failed: '+url.slice(0,160));
const texLoader=new THREE.TextureLoader(manager),gltfLoader=new GLTFLoader(manager);gltfLoader.setMeshoptDecoder(MeshoptDecoder);
const rng=(()=>{let a=75211;return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296;};})();
function ownMat(m){materials.push(m);return m;}
const iron=ownMat(new THREE.MeshStandardMaterial({color:'#38372f',metalness:.8,roughness:.76}));
const recess=ownMat(new THREE.MeshStandardMaterial({color:'#39352a',roughness:1}));
const dirt=ownMat(new THREE.MeshStandardMaterial({color:'#7b7960',roughness:1}));
let mats={},heightImage=null,environmentTarget=null,aoPass=null,composer=null;
async function loadTexture(path,kind){const t=await texLoader.loadAsync(asset(path));t.wrapS=t.wrapT=THREE.RepeatWrapping;t.colorSpace=kind==='color'?THREE.SRGBColorSpace:THREE.NoColorSpace;if(mobile&&(t.image.width>1024||t.image.height>1024)){const scale=1024/Math.max(t.image.width,t.image.height),cv=document.createElement('canvas');cv.width=Math.round(t.image.width*scale);cv.height=Math.round(t.image.height*scale);cv.getContext('2d').drawImage(t.image,0,0,cv.width,cv.height);t.image=cv;t.needsUpdate=true;}t.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());textures.push(t);return t;}
async function loadMaterials(manifest){
 for(const entry of manifest.assets.filter(x=>x.type==='texture')){
  const loaded={};await Promise.all(Object.entries(entry.maps).map(async([k,p])=>{loaded[k]=await loadTexture(p,k);}));
  const m=ownMat(new THREE.MeshStandardMaterial({map:loaded.color,normalMap:loaded.normal,roughnessMap:loaded.rough,aoMap:loaded.ao,roughness:1,metalness:0,normalScale:new THREE.Vector2(entry.name==='plaster'?.42:1,entry.name==='plaster'?.42:1),aoMapIntensity:.72}));
  mats[entry.name]=m;audit.assetsLoaded.push(entry.id);
  if(entry.name==='paving'&&loaded.height){const img=loaded.height.image,cv=document.createElement('canvas');cv.width=img.width;cv.height=img.height;const ctx=cv.getContext('2d',{willReadFrequently:true});ctx.drawImage(img,0,0);heightImage={w:cv.width,h:cv.height,data:ctx.getImageData(0,0,cv.width,cv.height).data};}
 }
 mats.trim=ownMat(mats.plaster.clone());mats.trim.color.set('#c2bba4');mats.trim.normalScale.set(.8,.8);
 mats.pale=ownMat(mats.plaster.clone());mats.pale.color.set('#d2c19c');
 mats.ochre=ownMat(mats.plaster.clone());mats.ochre.color.set('#c5a581');
 mats.wood.color.set('#a99278');mats.linen.color.set('#d4c19c');
 mats.darkWood=ownMat(mats.wood.clone());mats.darkWood.color.set('#78624b');
 mats.redCloth=ownMat(mats.linen.clone());mats.redCloth.color.set('#97614e');mats.redCloth.side=THREE.DoubleSide;
 mats.linen.side=THREE.DoubleSide;mats.roof.side=THREE.DoubleSide;mats.soffit=ownMat(mats.darkWood.clone());mats.soffit.side=THREE.DoubleSide;
 mats.sandstone=ownMat(mats.stone.clone());mats.sandstone.color.set('#d7c7a2');mats.sandstone.normalScale.set(.6,.6);
}
function worldUV(geo,scale=2.4){const p=geo.attributes.position,n=geo.attributes.normal,uv=[];for(let i=0;i<p.count;i++){const nx=Math.abs(n.getX(i)),ny=Math.abs(n.getY(i)),nz=Math.abs(n.getZ(i));uv.push((ny>.7?p.getX(i):nx>nz?p.getZ(i):p.getX(i))/scale,(ny>.7?p.getZ(i):p.getY(i))/scale);}geo.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));return geo;}
function add(geo,mat,x=0,y=0,z=0,rx=0,ry=0,rz=0,merge=true){const mesh=new THREE.Mesh(geo,mat);mesh.position.set(x,y,z);mesh.rotation.set(rx,ry,rz);mesh.castShadow=true;mesh.receiveShadow=true;if(merge){mesh.updateMatrix();const g=geo.index?geo.toNonIndexed():geo.clone();g.applyMatrix4(mesh.matrix);if(!merges.has(mat))merges.set(mat,[]);merges.get(mat).push(g);geo.dispose();}else world.add(mesh);return mesh;}
function box(x,y,z,w,h,d,mat,rot=0,bevel=.035,merge=true){const g=bevel>0?new RoundedBoxGeometry(w,h,d,2,Math.min(bevel,w*.15,h*.15,d*.15)):new THREE.BoxGeometry(w,h,d);worldUV(g,mat===mats.wood||mat===mats.darkWood?1.7:2.5);return add(g,mat,x,y,z,0,rot,0,merge);}
function collider(x,z,w,d,rot=0){colliders.push({type:'box',x,z,w:w/2,d:d/2,rot});}
function circle(x,z,r){colliders.push({type:'circle',x,z,r});}
function wall(x,z,w,h,d,mat,rot=0){box(x,h/2,z,w,h,d,mat,rot,.06);collider(x,z,w,d,rot);box(x,.26,z,w+.06,.5,d+.12,mats.stone,rot,.02);box(x,h-.1,z,w+.16,.21,d+.18,mats.trim,rot,.035);}
function extrudedShape(shape,depth,mat,x,y,z,rot=0,bevel=.035){const geo=new THREE.ExtrudeGeometry(shape,{depth,steps:1,bevelEnabled:bevel>0,bevelSize:bevel,bevelThickness:bevel,bevelSegments:2,curveSegments:28});geo.translate(0,0,-depth/2);worldUV(geo,2.5);return add(geo,mat,x,y,z,0,rot,0);}
function archFill(r,spring,top,halfWidth,depth,mat,x,z,rot=0){const s=new THREE.Shape();s.moveTo(-halfWidth,0);s.lineTo(-halfWidth,top);s.lineTo(halfWidth,top);s.lineTo(halfWidth,0);s.lineTo(r,0);s.lineTo(r,spring);s.absarc(0,spring,r,0,Math.PI,false);s.lineTo(-r,0);s.closePath();extrudedShape(s,depth,mat,x,0,z,rot);}
function archRing(x,z,r,spring,depth,rot=0){const thick=.29,s=new THREE.Shape();s.absarc(0,spring,r+thick,0,Math.PI,false);s.lineTo(-r,spring);s.absarc(0,spring,r,Math.PI,0,true);s.closePath();extrudedShape(s,depth,mats.sandstone,x,0,z,rot,.018);for(const side of [-1,1]){const lx=side*(r+thick/2);for(let k=0;k<5;k++){const h=spring/5;box(x+Math.cos(rot)*lx,(k+.5)*h,z-Math.sin(rot)*lx,thick,h-.014,depth,mats.sandstone,rot,.016);}}
 for(let k=0;k<13;k++){const a=(k+.5)*Math.PI/13,s=new THREE.Shape(),a0=k*Math.PI/13+.009,a1=(k+1)*Math.PI/13-.009;const ri=r+.006,ro=r+thick+.025;s.moveTo(Math.cos(a0)*ri,Math.sin(a0)*ri+spring);s.lineTo(Math.cos(a0)*ro,Math.sin(a0)*ro+spring);s.lineTo(Math.cos(a1)*ro,Math.sin(a1)*ro+spring);s.lineTo(Math.cos(a1)*ri,Math.sin(a1)*ri+spring);s.closePath();extrudedShape(s,depth+.035,mats.sandstone,x,0,z,rot,.008);}}
function shutters(x,y,z,w,h,rot=0){const root=new THREE.Group();root.position.set(x,y,z);root.rotation.y=rot;
 const patch=(lx,ly,lz,pw,ph,pd,mat,angle=0)=>{const xx=x+Math.cos(rot)*lx+Math.sin(rot)*lz,zz=z-Math.sin(rot)*lx+Math.cos(rot)*lz;box(xx,y+ly,zz,pw,ph,pd,mat,rot+angle,.018);};
 patch(0,0,0,w,h,.07,recess);for(const strip of [-.25,0,.25])patch(strip*w,0,.06,.035,h,.04,mats.darkWood);patch(0,0,.07,w,.045,.06,mats.darkWood);for(const side of [-1,1]){patch(side*(w/2+.11),0,.08,.19,h+.34,.27,mats.trim);const a=side*(.22+rng()*.22),cx=side*(w*.55+.2);for(let j=0;j<4;j++)patch(cx+side*(j-1.5)*w*.12,0,.12+(j-1.5)*a*.25,w*.117,h,.085,mats.darkWood,a);patch(cx,-h*.28,.18,w*.5,.105,.1,mats.darkWood,a);patch(cx,h*.28,.18,w*.5,.105,.1,mats.darkWood,a);}patch(0,-h/2-.1,.14,w+.44,.2,.42,mats.sandstone);patch(0,h/2+.1,.03,w+.39,.19,.26,mats.trim);}
function roof(x,z,w,d,base,rise){const sideLen=Math.hypot(d/2,rise),angle=Math.atan2(rise,d/2);for(const sign of [-1,1]){const g=new THREE.PlaneGeometry(w+.9,sideLen+.26,1,1);g.rotateX(-Math.PI/2);g.rotateX(sign*angle);worldUV(g,1.3);add(g,mats.roof,x,base+rise/2,z+sign*d/4,0,0,0);box(x,base+.04,z+sign*d/2,w+.94,.2,.19,mats.darkWood);}
 const gable=new THREE.Shape();gable.moveTo(-d/2,0);gable.lineTo(0,rise);gable.lineTo(d/2,0);gable.closePath();for(const side of [-1,1])extrudedShape(gable,.20,mats.pale,x+side*w/2,base,z,Math.PI/2);
 const geo=new THREE.CylinderGeometry(.12,.13,.38,8,1,true,0,Math.PI);geo.rotateZ(Math.PI/2);const count=Math.ceil((w+.8)/.37),inst=new THREE.InstancedMesh(geo,mats.roof,count),m=new THREE.Matrix4();for(let i=0;i<count;i++){m.makeTranslation(x-w/2-.35+i*.37,base+rise+.06,z);inst.setMatrixAt(i,m);}inst.castShadow=true;inst.receiveShadow=true;world.add(inst);}
function floor(){const g=new THREE.PlaneGeometry(56,56,240,240);g.rotateX(-Math.PI/2);const p=g.attributes.position,uv=g.attributes.uv;for(let i=0;i<p.count;i++){const x=p.getX(i),z=p.getZ(i);uv.setXY(i,(x+28)/2.8,(z+28)/2.8);let y=-.038;if(heightImage){const u=((x+28)/2.8%1+1)%1,v=((z+28)/2.8%1+1)%1,ix=Math.floor(u*(heightImage.w-1)),iy=Math.floor((1-v)*(heightImage.h-1));y+=heightImage.data[(iy*heightImage.w+ix)*4]/255*.045;}p.setY(i,y);}g.computeVertexNormals();const m=mats.paving.clone();m.normalScale.set(.65,.65);ownMat(m);add(g,m,0,0,0,0,0,0,false);}
function structure(){floor();
 // North wing: arcade at pedestrian scale, recessed upper storey and roof.
 wall(0,-12.7,29,7,.8,mats.pale);wall(-14,0,.8,7.2,26,mats.plaster);wall(14,0,.8,6.65,26,mats.ochre);
 for(const x of [-10,-5,0,5,10]){archFill(1.45,1.95,4.45,2.5,.85,mats.plaster,x,-9.4);archRing(x,-8.93,1.45,1.95,.99);collider(x-2.02,-9.4,1.05,.95);collider(x+2.02,-9.4,1.05,.95);box(x,4.26,-9.38,5.13,.19,1.07,mats.trim);}
 box(0,4.58,-10.65,28.8,.30,4.25,mats.trim);box(0,5.80,-9.50,29,2.62,.72,mats.pale);box(0,7.09,-9.48,29.2,.19,.94,mats.trim);collider(0,-13.4,29,1);
 for(const x of [-11,-6.5,-2,2.5,7,11.5]){shutters(x,5.83,-9.08,1.15,1.52);}
 roof(0,-11.3,29,4.4,7,1.45);
 // Side façades, alternating wall tones and deep window surrounds.
 for(const z of [-7.6,-1.8,4.2,10.2]){shutters(-13.53,4.7,z,1.14,1.55,Math.PI/2);shutters(13.53,4.25,z,1.1,1.4,-Math.PI/2);}
 for(const z of [-8,-1.5,5.3]){box(-13.38,1.23,z,.17,2.4,1.23,mats.darkWood);box(13.38,1.3,z,.16,2.56,1.28,mats.darkWood);for(const side of [-1,1]){box(-13.32,1.23,z+side*.75,.3,2.72,.19,mats.trim);box(13.32,1.3,z+side*.75,.3,2.78,.2,mats.trim);}box(-13.32,2.66,z,.34,.20,1.72,mats.trim);box(13.31,2.78,z,.34,.2,1.74,mats.trim);}
 for(const x of [-13.75,13.75]){box(x,3.31,0,.29,.16,26,mats.trim);box(x,6.08,0,.45,.21,26,mats.trim);}
 // South entrance arch and side closures: no walk-through skybox facade.
 wall(-9,14.3,11,5.1,.8,mats.ochre);wall(9,14.3,11,5.1,.8,mats.pale);archFill(2.7,2.15,6.7,3.7,.9,mats.stone,0,14.3);archRing(0,13.83,2.7,2.15,1.1);collider(-3.3,14.3,1.2,1);collider(3.3,14.3,1.2,1);
 // Passage visibly continues before the boundary.
 wall(-3.9,19,1,5,9,mats.plaster);wall(3.9,19,1,5,9,mats.pale);wall(0,23.3,8.5,4.9,.7,mats.stone);shutters(0,2.6,22.9,1.8,2.2);
 // Covered timber gallery: visible beams, brackets and weathered joinery.
 for(const x of [-12.5,-7.5,-2.5,2.5,7.5,12.5]){box(x,3.9,-10.75,.18,.22,3.5,mats.darkWood);}
 for(const z of [-9,-3,3,9]){box(-13.3,6.62,z,2.8,.18,.22,mats.darkWood);box(13.3,6.08,z,2.8,.18,.22,mats.darkWood);}
 for(const side of [-1,1]){const inner=side*11.45,outer=side*15.4,low=side<0?6.7:6.13,high=low+.72;const positions=[inner,low,-13.35,inner,low,13.35,outer,high,13.35,outer,high,-13.35];const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geo.setIndex(side<0?[0,2,1,0,3,2]:[0,1,2,0,2,3]);geo.computeVertexNormals();worldUV(geo,1.5);const soffit=geo.clone();soffit.translate(0,-.07,0);add(geo,mats.roof);add(soffit,mats.soffit);box(inner,low-.1,0,.2,.22,26.8,mats.darkWood);}

 // Low perimeter wear, irregular repair patches in stone, not decorative wallpaper.
 for(let k=0;k<65;k++){const side=k%2?1:-1,z=-11+rng()*23;box(side*13.53,.18+rng()*.17,z,.16,.3+rng()*.23,.34+rng()*.6,mats.stone,0,.03);}
}
function fountain(){const x=1.9,z=-.7;
 for(const [radius,h,y]of [[1.73,.22,.10],[1.55,.19,.30]]){const g=new THREE.CylinderGeometry(radius,radius+.045,h,10,1);worldUV(g,2.5);add(g,mats.sandstone,x,y,z);}
 const ring=new THREE.Shape();ring.absarc(0,0,1.42,0,Math.PI*2,false);const hole=new THREE.Path();hole.absarc(0,0,1.06,0,Math.PI*2,true);ring.holes.push(hole);const g=new THREE.ExtrudeGeometry(ring,{depth:.55,bevelEnabled:true,bevelSegments:3,bevelSize:.045,bevelThickness:.035,curveSegments:40});g.rotateX(-Math.PI/2);worldUV(g,2.5);add(g,mats.sandstone,x,.47,z);
 const water=ownMat(new THREE.MeshPhysicalMaterial({color:'#587267',metalness:.12,roughness:.13,transparent:true,opacity:.80,clearcoat:1,clearcoatRoughness:.07}));const wm=add(new THREE.CircleGeometry(1.06,64),water,x,.94,z,-Math.PI/2,0,0,false);wm.name='courtyard-water';
 const stem=new THREE.CylinderGeometry(.11,.24,1.35,12);worldUV(stem,1);add(stem,mats.sandstone,x,1.10,z);const plate=new THREE.LatheGeometry([new THREE.Vector2(.10,0),new THREE.Vector2(.45,.08),new THREE.Vector2(.62,.20),new THREE.Vector2(.66,.26),new THREE.Vector2(.58,.27),new THREE.Vector2(.15,.13)],40);worldUV(plate,2);add(plate,mats.sandstone,x,1.72,z);circle(x,z,1.82);
 const drops=new THREE.BufferGeometry(),p=[];for(let i=0;i<140;i++){const a=rng()*6.283,phase=rng();p.push(x+Math.cos(a)*.52,1.1+phase*.68,z+Math.sin(a)*.52);}drops.setAttribute('position',new THREE.Float32BufferAttribute(p,3));const spray=new THREE.Points(drops,new THREE.PointsMaterial({color:'#c4d8d5',size:.021,transparent:true,opacity:.42,depthWrite:false}));world.add(spray);spray.userData.water=true;movingCloth.push(spray);
}
function market(){
 for(const group of [{x:-8,z:1.8,w:7,d:3.5,cloth:'linen'},{x:8.5,z:-4.4,w:5,d:3,cloth:'redCloth'}]){
  const {x,z,w,d,cloth}=group;for(const side of [-1,1])for(const dz of [-d/2,d/2]){box(x+side*w/2,1.6,z+dz,.13,3.2,.13,mats.darkWood);circle(x+side*w/2,z+dz,.19);}
  for(const dz of [-d/2,d/2])box(x,3.05,z+dz,w+.4,.14,.17,mats.darkWood);
  const geo=new THREE.PlaneGeometry(w+.55,d+.7,32,16);geo.rotateX(-Math.PI/2);const p=geo.attributes.position,base=[];for(let i=0;i<p.count;i++){const xx=p.getX(i),zz=p.getZ(i),y=.34*(xx/(w/2))**2-.34+.045*Math.cos(xx*5)+zz*.065;p.setY(i,y);base.push(y);}geo.computeVertexNormals();const canopy=add(geo,mats[cloth],x,3.04,z,0,0,0,false);canopy.material=ownMat(mats[cloth].clone());canopy.material.normalScale.set(.20,.20);canopy.userData.base=base;movingCloth.push(canopy);
  for(const side of [-1,1]){const g=new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(x+side*w/2,3.1,z-d/2),new THREE.Vector3(x+side*(w/2+.14),2,z-d/2-.25),new THREE.Vector3(x+side*(w/2+.28),.15,z-d/2-.5)]),12,.014,4,false);add(g,mats.darkWood);}
  const tw=w*.73;for(let k=0;k<6;k++)box(x,.92,z+(k-2.5)*.24,tw,.095,.235,mats.wood);for(const xx of [-tw*.38,tw*.38])for(const zz of [-.52,.52])box(x+xx,.43,z+zz,.13,.86,.13,mats.darkWood);collider(x,z,tw,1.5);
  // Shallow produce trays and produce geometry, kept at believable human scale.
  for(let tray=0;tray<3;tray++){const tx=x+(tray-1)*tw*.29;box(tx,1.02,z,tw*.25,.12,1.18,mats.darkWood);for(const side of [-1,1])box(tx+side*tw*.125,1.13,z,.045,.18,1.20,mats.wood);for(let fruit=0;fruit<22;fruit++){const shade=Math.floor(rng()*4),materialKey='fruit'+tray+'_'+shade;const mat=mats[materialKey]||(mats[materialKey]=ownMat(new THREE.MeshStandardMaterial({color:new THREE.Color(tray===0?'#a66e29':tray===1?'#6f773d':'#a33e26').multiplyScalar(.8+shade*.08),roughness:.6})));const geo=new THREE.SphereGeometry(.055+rng()*.018,8,6);add(geo,mat,tx+(rng()-.5)*tw*.22,1.18+rng()*.035,z+(rng()-.5)*.95);}}
 }
 // Side bench and individual slats.
 for(const z of [-5,5.3]){for(let k=0;k<4;k++)box(12.7,.51,z+(k-1.5)*.11,.48,.075,.105,mats.wood);for(const zz of [-.14,.14])box(12.7,.25,z+zz,.12,.50,.12,mats.darkWood);}
}
function planting(){
 const foliage=ownMat(new THREE.MeshStandardMaterial({color:'#4c653c',roughness:.93,side:THREE.DoubleSide}));
 const leafGeo=new THREE.SphereGeometry(.5,6,4);leafGeo.scale(.11,.018,.035);const total=1450,inst=new THREE.InstancedMesh(leafGeo,foliage,total),matrix=new THREE.Matrix4(),q=new THREE.Quaternion(),p=new THREE.Vector3(),sc=new THREE.Vector3();
 for(let i=0;i<total;i++){let x,y,z;if(i<900){z=-8+rng()*14;y=.15+rng()*5.5;x=-13.47+(rng()-.5)*.15;const fade=Math.sin(z*.85+y*.6);if(fade<-.5)y*=.35;}else{const a=rng()*6.283,r=.3+rng()*.8;x=10.3+Math.cos(a)*r;z=8.8+Math.sin(a)*r;y=.7+rng()*1.7;}
 p.set(x,y,z);q.setFromEuler(new THREE.Euler(rng()*2,rng()*6.3,rng()*1.2));sc.setScalar(.85+rng()*1.8);matrix.compose(p,q,sc);inst.setMatrixAt(i,matrix);inst.setColorAt(i,new THREE.Color('#687b3b').multiplyScalar(.58+rng()*.50));}inst.castShadow=true;inst.receiveShadow=true;world.add(inst);
 // Tufts occupy cracks and margins, not the middle of navigation corridors.
 const blades=[];for(let i=0;i<260;i++){const side=i%2?1:-1,x=side*(12.9+rng()*.55),z=-11+rng()*24,y=0;for(let k=0;k<5;k++){const a=rng()*6.3,h=.12+rng()*.23,w=.018;blades.push(x-w,y,z,x+w,y,z,x+Math.cos(a)*.13,y+h,z+Math.sin(a)*.13);}}const grass=new THREE.BufferGeometry();grass.setAttribute('position',new THREE.Float32BufferAttribute(blades,3));grass.computeVertexNormals();add(grass,foliage,0,0,0,0,0,0,false);
}
function flush(){for(const [mat,list]of merges){if(!list.length)continue;const g=mergeGeometries(list,false);if(!g)throw Error('Geometry merge failed');const m=new THREE.Mesh(g,mat);m.castShadow=true;m.receiveShadow=true;world.add(m);for(const item of list)item.dispose();}merges.clear();}
const modelTemplates={};
async function loadModels(manifest){for(const entry of manifest.assets.filter(a=>a.type==='model')){const gltf=await gltfLoader.loadAsync(asset(entry.file));gltf.scene.updateMatrixWorld(true);modelTemplates[entry.name]=gltf.scene;audit.modelNames.push(entry.name);audit.assetsLoaded.push(entry.id);}}
function placeModel(name,x,z,height,rot=0,collision=true){const model=modelTemplates[name].clone(true),bbox=new THREE.Box3().setFromObject(model),size=bbox.getSize(new THREE.Vector3()),center=bbox.getCenter(new THREE.Vector3()),s=height/size.y;const pivot=new THREE.Group();model.position.sub(new THREE.Vector3(center.x,bbox.min.y,center.z));pivot.add(model);pivot.scale.setScalar(s);pivot.rotation.y=rot;pivot.position.set(x,0,z);pivot.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;if(o.material){o.material.envMapIntensity=.65;if(o.material.map)o.material.map.anisotropy=4;}}});world.add(pivot);if(collision){if(name==='tree')circle(x,z,.4);else circle(x,z,Math.max(size.x,size.z)*s*.45);}return pivot;}
function props(){
 for(const [x,z,h,r]of [[-11,8.4,1.05,.2],[-10.4,9.1,.85,1],[-11,-7.6,1.08,.8],[8.4,-11.5,.95,2],[9.5,-11.5,.83,1.2],[12.6,10,1.02,1.8]])placeModel('barrel',x,z,h,r);
 for(const [x,z,h,r]of [[-11.6,5.3,.55,.4],[-10.9,5.65,.37,2],[11.8,8.2,.67,1],[11.35,9.1,.4,2],[-12.4,-3.8,.58,.8],[4.2,-11.75,.72,.3],[-5.2,-10.6,.5,.7],[8.8,5,.76,1.7]])placeModel('pot',x,z,h,r);
 placeModel('tree',10.8,6.8,7.0,-.4);placeModel('tree',-10.7,-5.6,5.0,1.3);placeModel('tree',-13.0,18,7.7,.3);placeModel('tree',14.5,-17,9,.7);
 // The heritage door is an illustrative asset, not an archaeological claim.
 const door=placeModel('door',0,-12.14,3.6,0,false);collider(0,-12.25,2.8,.4);
}
const sun=new THREE.DirectionalLight('#ffead0',3.4);sun.position.set(-11,18,13);sun.target.position.set(0,0,-3);sun.castShadow=true;sun.shadow.mapSize.set(mobile?2048:4096,mobile?2048:4096);sun.shadow.camera.left=-24;sun.shadow.camera.right=24;sun.shadow.camera.top=24;sun.shadow.camera.bottom=-24;sun.shadow.camera.near=.1;sun.shadow.camera.far=75;sun.shadow.bias=-.00016;sun.shadow.normalBias=.022;sun.shadow.radius=3;scene.add(sun,sun.target);scene.add(new THREE.HemisphereLight('#c6d8e3','#756445',.23));
function setupPost(){composer=new EffectComposer(renderer);composer.addPass(new RenderPass(scene,camera));aoPass=new SSAOPass(scene,camera,innerWidth,innerHeight,16);aoPass.kernelRadius=.5;aoPass.minDistance=.003;aoPass.maxDistance=.14;aoPass.enabled=!mobile;composer.addPass(aoPass);composer.addPass(new OutputPass());}
function resize(){const w=innerWidth,h=innerHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();if(composer)composer.setSize(w,h);}
window.addEventListener('resize',resize);
let x=7.2,z=10.8,yaw=.55,pitch=-.018,paused=false,disposed=false,loaded=false,time=0,last=0,frames=0,frameMs=[],drag=null;
const keys=new Set(),velocity=new THREE.Vector2(),touchVector=new THREE.Vector2(),namedView={entrance:[6.8,7.8,.55,-.018],market:[-2,7.5,.50,-.02],fountain:[5.4,3.8,.60,-.02],arcade:[-5.5,-5.8,-.25,.025]};
function clearInput(){keys.clear();touchVector.set(0,0);drag=null;}
function blocked(px,pz){if(px<-13.2||px>13.2||pz<-12.15||pz>22.65)return true;for(const c of colliders){if(c.type==='circle'){if(Math.hypot(px-c.x,pz-c.z)<c.r+.24)return true;}else{const dx=px-c.x,dz=pz-c.z,cs=Math.cos(c.rot),sn=Math.sin(c.rot),lx=cs*dx-sn*dz,lz=sn*dx+cs*dz;if(Math.abs(lx)<c.w+.24&&Math.abs(lz)<c.d+.24)return true;}}return false;}
function teleport(name){const p=namedView[name];if(!p||blocked(p[0],p[1]))return false;[x,z,yaw,pitch]=p;$('places').value=name;velocity.set(0,0);clearInput();return true;}
function setPause(v){paused=!!v;clearInput();$('pause').textContent=paused?'Resume':'Pause';$('paused').hidden=!paused;}
function setLight(value){if(value==='late'){sun.position.set(-18,9,11);sun.color.set('#ffd7a2');sun.intensity=2.7;scene.environmentIntensity=.36;renderer.toneMappingExposure=1.12;}else{sun.position.set(-11,18,13);sun.color.set('#ffead0');sun.intensity=3.4;scene.environmentIntensity=.65;renderer.toneMappingExposure=1.05;}}
function setQuality(value){const low=value==='balanced'||(value==='auto'&&mobile);renderer.setPixelRatio(Math.min(devicePixelRatio||1,low?1:1.6));if(aoPass)aoPass.enabled=!low;renderer.shadowMap.enabled=true;resize();audit.quality=value;}
$('pause').onclick=()=>setPause(!paused);$('resume').onclick=()=>setPause(false);$('quality').onchange=e=>setQuality(e.target.value);$('light').onchange=e=>setLight(e.target.value);
$('home').onclick=()=>parent!==window?parent.postMessage({type:'courtyard-exit'},'*'):location.assign('../#home');
$('loading-back').onclick=()=>$('home').click();
$('archive').onclick=()=>parent!==window?parent.postMessage({type:'courtyard-archive'},'*'):location.assign('../#atlas?year=500&city='+encodeURIComponent('Níhmīwū')+'&polity=294');
$('places').onchange=e=>teleport(e.target.value);
$('info-button').onclick=()=>{setPause(true);$('info').showModal();};$('info-close').onclick=()=>{$('info').close();setPause(false);};$('info').addEventListener('cancel',()=>setPause(false));
$('photo').onclick=()=>{document.body.classList.toggle('photo');};
document.addEventListener('keydown',e=>{if(['SELECT','BUTTON','INPUT'].includes(e.target.tagName)&&!['Escape','KeyP','KeyH'].includes(e.code))return;if(['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space'].includes(e.code))e.preventDefault();keys.add(e.code);if(e.code==='KeyP')setPause(!paused);if(e.code==='KeyH')document.body.classList.toggle('photo');if(e.code==='Escape'){if($('info').open)$('info').close();document.body.classList.remove('photo');setPause(false);}});
document.addEventListener('keyup',e=>keys.delete(e.code));
const canvas=$('view');canvas.addEventListener('pointerdown',e=>{if(paused)return;canvas.focus({preventScroll:true});drag={id:e.pointerId,x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);e.preventDefault();});canvas.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id||paused)return;yaw-=(e.clientX-drag.x)*.003;pitch=THREE.MathUtils.clamp(pitch-(e.clientY-drag.y)*.003,-1.22,1.15);drag={id:e.pointerId,x:e.clientX,y:e.clientY};});for(const ev of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(ev,()=>drag=null);
let stickPointer=null;const stick=$('stick');function joy(e){if(e.pointerId!==stickPointer)return;const r=stick.getBoundingClientRect(),dx=(e.clientX-r.left-r.width/2)/34,dz=(e.clientY-r.top-r.height/2)/34;touchVector.set(dx,dz);if(touchVector.length()>1)touchVector.normalize();$('thumb').style.transform=`translate(${touchVector.x*29}px,${touchVector.y*29}px)`;e.preventDefault();}stick.addEventListener('pointerdown',e=>{stickPointer=e.pointerId;stick.setPointerCapture(e.pointerId);joy(e);});stick.addEventListener('pointermove',joy);for(const ev of ['pointerup','pointercancel','lostpointercapture'])stick.addEventListener(ev,()=>{stickPointer=null;touchVector.set(0,0);$('thumb').style.transform='';});
// Activate touch buttons on pointerup; suppress the compatibility click after a modal changes the target.
let touchButton=null,lastTouchAt=0,lastTouchButton=null;
document.addEventListener('pointerdown',e=>{if(e.pointerType!=='touch')return;const b=e.target.closest('button');touchButton=b?{button:b,id:e.pointerId,x:e.clientX,y:e.clientY}:null;},true);
document.addEventListener('pointerup',e=>{if(e.pointerType!=='touch'||!touchButton||e.pointerId!==touchButton.id)return;const t=touchButton;touchButton=null;if(e.target.closest('button')!==t.button||Math.hypot(e.clientX-t.x,e.clientY-t.y)>14)return;lastTouchButton=t.button;lastTouchAt=performance.now();e.preventDefault();t.button.click();},true);
document.addEventListener('pointercancel',()=>touchButton=null,true);
document.addEventListener('click',e=>{if(e.isTrusted&&lastTouchButton&&e.detail!==0&&performance.now()-lastTouchAt<650){e.preventDefault();e.stopImmediatePropagation();}},true);
window.addEventListener('blur',clearInput);document.addEventListener('visibilitychange',()=>{if(document.hidden)setPause(true);});document.body.classList.toggle('touch',mobile);
function update(dt){const side=(keys.has('KeyD')||keys.has('ArrowRight')?1:0)-(keys.has('KeyA')||keys.has('ArrowLeft')?1:0)+touchVector.x,forward=(keys.has('KeyW')||keys.has('ArrowUp')?1:0)-(keys.has('KeyS')||keys.has('ArrowDown')?1:0)-touchVector.y;const len=Math.max(1,Math.hypot(side,forward)),speed=keys.has('ShiftLeft')?3.3:1.85;const vx=(Math.cos(yaw)*side-Math.sin(yaw)*forward)/len*speed,vz=(-Math.sin(yaw)*side-Math.cos(yaw)*forward)/len*speed;velocity.lerp(new THREE.Vector2(vx,vz),1-Math.exp(-12*dt));let nx=x+velocity.x*dt,nz=z+velocity.y*dt;if(!blocked(nx,z))x=nx;if(!blocked(x,nz))z=nz;const moving=velocity.length();camera.position.set(x,1.68+(moving>.15?Math.sin(time*8)*.014:0),z);camera.rotation.set(pitch,yaw,0,'YXZ');
 for(const obj of movingCloth){if(obj.userData.water){const a=obj.geometry.attributes.position;for(let i=0;i<a.count;i++){let v=a.getY(i)-dt*.44;if(v<1.02)v=1.80;a.setY(i,v);}a.needsUpdate=true;}else{const p=obj.geometry.attributes.position;for(let i=0;i<p.count;i++)p.setY(i,obj.userData.base[i]+Math.sin(time*.72+p.getX(i)*1.8+p.getZ(i))*.018);p.needsUpdate=true;if(frames%20===0)obj.geometry.computeVertexNormals();}}
}
function loop(ts){if(disposed)return;requestAnimationFrame(loop);const dt=Math.min(.04,(ts-last)/1000||.016);if(last&&loaded){frameMs.push(ts-last);if(frameMs.length>300)frameMs.shift();}last=ts;frames++;if(!paused){time+=dt;update(dt);}renderer.info.reset();if(composer)composer.render();else renderer.render(scene,camera);}
function dispose(){if(disposed)return;disposed=true;clearInput();const geos=new Set(),matsAll=new Set(),texAll=new Set(textures);scene.traverse(o=>{if(o.geometry)geos.add(o.geometry);if(o.material)for(const m of Array.isArray(o.material)?o.material:[o.material])matsAll.add(m);});for(const m of matsAll)for(const v of Object.values(m))if(v?.isTexture)texAll.add(v);for(const g of geos)g.dispose();for(const m of matsAll)m.dispose();for(const t of texAll)t.dispose();environmentTarget?.dispose();composer?.dispose();aoPass?.dispose();renderer.dispose();audit.ready=false;window.COURTYARD.ready=false;}
window.addEventListener('message',e=>{if(e.source!==parent||!e.data)return;if(e.data.type==='courtyard-stop')dispose();});
Object.assign(window.COURTYARD,{inspect:()=>({...audit,ready:loaded&&!disposed,player:{x,z,y:camera.position.y,yaw,pitch},paused,disposed,animationTime:time,drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles,frames,frameTimeMedian:frameMs.length?[...frameMs].sort((a,b)=>a-b)[Math.floor(frameMs.length*.5)]:null,frameTimeP95:frameMs.length?[...frameMs].sort((a,b)=>a-b)[Math.floor(frameMs.length*.95)]:null,collisionObjects:colliders.length}),teleport,pause:setPause,dispose,blocked});
async function main(){const manifest=window.COURTYARD_MANIFEST||await(await fetch('ASSETS.json')).json();if(window.COURTYARD_MANIFEST){const link=document.querySelector('a[href="ASSETS.json"]');if(link)link.href=URL.createObjectURL(new Blob([JSON.stringify(manifest,null,2)],{type:'application/json'}));}await loadMaterials(manifest);if(disposed)return;const env=await new RGBELoader(manager).loadAsync(asset('assets/sky.hdr'));env.mapping=THREE.EquirectangularReflectionMapping;const pmrem=new THREE.PMREMGenerator(renderer);environmentTarget=pmrem.fromEquirectangular(env);scene.environment=environmentTarget.texture;scene.environmentIntensity=.47;scene.background=env;scene.backgroundIntensity=.92;scene.backgroundBlurriness=.02;textures.push(env);pmrem.dispose();structure();fountain();market();planting();flush();await loadModels(manifest);if(disposed)return;props();audit.assetsLoaded.push(manifest.assets.find(a=>a.type==='hdri')?.id||'HDR environment');setupPost();setQuality('auto');teleport('entrance');resize();renderer.compile(scene,camera);await renderer.compileAsync(scene,camera);update(0);renderer.info.reset();composer.render();loaded=true;audit.ready=true;window.COURTYARD.ready=true;$('loading').hidden=true;requestAnimationFrame(loop);}
main().catch(e=>{if(disposed)return;audit.errors.push(e.message);$('progress').textContent=e.message;$('loading-title').textContent='The courtyard could not be opened';$('loading-help').hidden=false;console.error(e);});
