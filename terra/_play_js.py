"""JS-приложение режима прогулки (terra.play). Держится отдельным файлом,
чтобы play.py читался; сюда вшит весь трёхмерный движок сцены."""

APP_JS = r"""
(function(){
'use strict';
/* ══════════════════ 0. служебное ══════════════════ */
window.GAME = {ready:false, errors:[], fps:0, scene:-1};
window.addEventListener('error', function(e){ GAME.errors.push(String(e.message)); });
window.addEventListener('unhandledrejection', function(e){
  GAME.errors.push('promise: '+String(e.reason&&e.reason.message||e.reason)); e.preventDefault(); });

var Q = new URLSearchParams(location.search);
var DEBUG = Q.get('debug')==='1';

function mulberry(a){ return function(){ a|=0; a=a+0x6D2B79F5|0;
  var t=Math.imul(a^a>>>15,1|a); t=t+Math.imul(t^t>>>7,61|t)^t;
  return ((t^t>>>14)>>>0)/4294967296; }; }
function clamp(v,a,b){ return v<a?a:(v>b?b:v); }
function lerp(a,b,t){ return a+(b-a)*t; }
function sstep(t){ t=clamp(t,0,1); return t*t*(3-2*t); }
function pick(rng,arr){ return arr[Math.floor(rng()*arr.length)%arr.length]; }

/* детерминированный 2D value-noise */
function _h2(x,y){ var n=Math.sin(x*127.1+y*311.7+NZSEED*13.7)*43758.5453;
  return n-Math.floor(n); }
function vnoise(x,y){ var ix=Math.floor(x), iy=Math.floor(y), fx=x-ix, fy=y-iy;
  var a=_h2(ix,iy), b=_h2(ix+1,iy), c=_h2(ix,iy+1), d=_h2(ix+1,iy+1);
  var ux=fx*fx*(3-2*fx), uy=fy*fy*(3-2*fy);
  return a+(b-a)*ux+(c-a)*uy+(a-b-c+d)*ux*uy; }
function fbm(x,y,oct){ var s=0, amp=0.5, n=0;
  for(var i=0;i<oct;i++){ s+=amp*vnoise(x,y); n+=amp; x*=2.03; y*=1.97; amp*=0.5; }
  return s/n; }
var NZSEED = 7;

function col(hex){ return new THREE.Color(hex); }
function colVar(rng,hex,amt){ var c=col(hex);
  var f=1+(rng()*2-1)*(amt||0.08); c.r=clamp(c.r*f,0,1); c.g=clamp(c.g*f,0,1);
  c.b=clamp(c.b*f,0,1); return c; }
function fmtClock(t){ var h=Math.floor(t*24), m=Math.floor((t*24-h)*60);
  return (h<10?'0':'')+h+':'+(m<10?'0':'')+m; }
function dayWord(t){
  if(t<0.21||t>=0.84) return 'ночь';
  if(t<0.29) return 'рассвет'; if(t<0.45) return 'утро';
  if(t<0.63) return 'день';    if(t<0.72) return 'вечер';
  return 'закат'; }

/* ══════════════════ 1. меню ══════════════════ */
var EL = {};
['menu','cards','menuFoot','hud','hudPlace','hudLine','hudTime','hint','dot','talk',
 'pause','pauseText','dlg','dcard','dmsgs','dtopics','apiKey','apiMsg','apiSend',
 'dclose','map','menuBtn','fade','loading','c3d'].forEach(function(id){ EL[id]=document.getElementById(id); });

function bandArt(cv, sc){ var g=cv.getContext('2d'), w=cv.width, h=cv.height;
  var skies={capital:['#2c4a6e','#c9885a'],bronze:['#3a5a4e','#c9a35a'],
             neolithic:['#4a4258','#b8763f']};
  var sk=skies[sc.id]||skies.capital;
  var gr=g.createLinearGradient(0,0,0,h); gr.addColorStop(0,sk[0]); gr.addColorStop(1,sk[1]);
  g.fillStyle=gr; g.fillRect(0,0,w,h);
  g.fillStyle='#f5d9a0'; g.beginPath(); g.arc(w*0.72,h*0.52,13,0,7); g.fill();
  g.fillStyle='#12141b';
  if(sc.id==='capital'){ g.fillRect(0,h-26,w,26);
    for(var i=0;i<7;i++){ g.fillRect(8+i*46,h-46,26,20); g.fillRect(12+i*46,h-54,18,8); }
    for(i=0;i<5;i++) g.fillRect(60+i*14,h-70,5,26); g.fillRect(54,h-74,86,6);
  } else if(sc.id==='bronze'){ g.fillRect(0,h-22,w,22);
    g.fillRect(30,h-52,74,30); g.fillRect(44,h-68,46,16); g.fillRect(56,h-80,22,12);
    for(i=0;i<5;i++) g.fillRect(130+i*34,h-40,24,18);
  } else { g.fillRect(0,h-20,w,20);
    for(i=0;i<6;i++){ var x=16+i*48; g.beginPath(); g.moveTo(x,h-20);
      g.lineTo(x+16,h-52); g.lineTo(x+32,h-20); g.closePath(); g.fill(); } }
}
function buildMenu(){
  PLAY.scenes.forEach(function(sc,i){
    var d=document.createElement('div'); d.className='card';
    var cv=document.createElement('canvas'); cv.width=300; cv.height=86;
    cv.className='band'; bandArt(cv,sc);
    d.appendChild(cv);
    var h2=document.createElement('h2'); h2.textContent=sc.title; d.appendChild(h2);
    var wn=document.createElement('div'); wn.className='when';
    wn.textContent=sc.year_ru+' · '+sc.era; d.appendChild(wn);
    var p=document.createElement('p'); p.textContent=sc.desc; d.appendChild(p);
    d.onclick=function(){ startScene(i); };
    EL.cards.appendChild(d);
  });
  EL.menuFoot.innerHTML='Каждая сцена собрана из данных прогона «'+PLAY.run_id+
   '»: настоящие города, народы, боги и люди книги мира.<br>'+
   'Управление: <b>WASD</b> — шаг, <b>мышь</b> — взгляд, <b>Shift</b> — бег, '+
   '<b>E</b> — заговорить, <b>T</b> — время, <b>F</b> — вид, <b>M</b> — карта.';
}

/* ══════════════════ 2. мир ══════════════════ */
var S=null, G=null, R3=null;   // сцена-данные, рантайм, three-объекты

var PALS = {
  6:{ grass:'#93a05a', grass2:'#7e8f4e', dry:'#c0ac6e', rock:'#8f8878', sand:'#d2c298',
      path:'#b39c70', field:'#8a7a46', water:'#2f6f86', deep:'#1d4a63',
      treeA:'#6f7d4a', treeB:'#41582f', trunk:'#6b5138', reed:'#7d8a4f', sky:0 },
  12:{ grass:'#5b8d4c', grass2:'#4d7d43', dry:'#8fa060', rock:'#7d7a68', sand:'#c6b489',
      path:'#9c8c64', field:'#6d7a3d', water:'#2e7a6e', deep:'#174f4a',
      treeA:'#4f8a44', treeB:'#3d6e38', trunk:'#5f4a34', reed:'#6f8a4a', sky:1 },
  8:{ grass:'#b1a06e', grass2:'#a3915f', dry:'#c9b681', rock:'#8b8378', sand:'#d8c69c',
      path:'#bda878', field:'#93824c', water:'#2e6b80', deep:'#1a4a63',
      treeA:'#6d7a4d', treeB:'#57683f', trunk:'#64503b', reed:'#8a8a54', sky:2 },
  5:{ grass:'#a2ac62', grass2:'#8f9c55', dry:'#c4b273', rock:'#8d8578', sand:'#d0c096',
      path:'#b3a071', field:'#8a7a46', water:'#2f6f86', deep:'#1d4a63',
      treeA:'#6f7d4a', treeB:'#4c6136', trunk:'#6b5138', reed:'#7d8a4f', sky:0 },
  10:{ grass:'#659552', grass2:'#568547', dry:'#94a45e', rock:'#84806e', sand:'#c9b78c',
      path:'#a08e62', field:'#75823f', water:'#2a7268', deep:'#144a45',
      treeA:'#3f7d38', treeB:'#2f632c', trunk:'#5a462f', reed:'#5f8a44', sky:1 },
  9:{ grass:'#b0a45e', grass2:'#9d9350', dry:'#c9b675', rock:'#8b8378', sand:'#d6c396',
      path:'#bda878', field:'#93824c', water:'#2f6f86', deep:'#1d4a63',
      treeA:'#6d7d43', treeB:'#556638', trunk:'#64503b', reed:'#8a8a54', sky:2 },
  4:{ grass:'#6f9448', grass2:'#5d833f', dry:'#a0a05c', rock:'#837d6e', sand:'#c9ba8e',
      path:'#a3906a', field:'#77743c', water:'#2f6f86', deep:'#1d4a63',
      treeA:'#4d7a3a', treeB:'#3a5f2e', trunk:'#5f4b34', reed:'#6f8a4a', sky:1 } };
function getPal(){ return PALS[S.biome] || PALS[5]; }

var ERACOL = {
  capital:{ wallS:'#98907e', house:['#cfc0a2','#c6b493','#d5c6a8','#bfae8e'],
    roof:['#9d5f43','#a86b4b','#8f563d'], wood:'#6b5138', stoneT:'#d0c6ac',
    door:'#4a3826', col:'#cfc6b0', pave:'#a89a80' },
  bronze:{ wallS:'#b5986e', house:['#c7ab80','#cfb489','#bda276','#d3b98c'],
    roof:['#c3a778','#cbb086'], wood:'#5d4832', stoneT:'#d8cba8',
    door:'#443521', col:'#c9ad82', pave:'#b09a72' },
  neolithic:{ wallS:'#8a7052', house:['#b5987a','#ab8e6f','#bfa284'],
    roof:['#c2ab74','#b7a069','#cbb47e'], wood:'#6a5340', stoneT:'#a89878',
    door:'#3f3020', col:'#b5987a', pave:'#b3a078' } };

var WATER_Y=-1.1, BASE_H=2.3, TSIZE=1200, TSEG=192;
var FLATR = {capital:250, bronze:235, neolithic:180};

function riverDist(x,z){ if(!S.river) return 1e9;
  var px=S.river[0], pz=S.river[1], a=S.river[2];
  return Math.abs(-(x-px)*Math.sin(a)+(z-pz)*Math.cos(a)); }
function seaS(x,z){ if(!S.sea) return -1e9;
  return x*Math.cos(S.sea[0])+z*Math.sin(S.sea[0])-S.sea[1]; }

function groundH(x,z){
  var rug=S.rugg, amp=7+rug*30;
  var h=fbm(x*0.0042,z*0.0042,5)*amp + fbm(x*0.021,z*0.021,3)*amp*0.14;
  var dc=Math.hypot(x,z);
  h += sstep((dc-330)/280)*rug*26;                    // дальние холмы
  var flat=BASE_H+fbm(x*0.05,z*0.05,2)*0.55;
  h = lerp(flat, h+2.4, sstep((dc-FLATR[S.id])/170)); // ровная площадка города
  if(S.river){ var hw=S.river[3], d=riverDist(x,z);
    var carve=1-sstep((d-hw*0.4)/(hw*1.25));
    if(carve>0) h=Math.min(h, lerp(h,-3.8-hw*0.03,carve)); }
  if(S.sea){ var s=seaS(x,z);
    if(s>-60) h=Math.min(h, lerp(2.0,-11,sstep((s+42)/100))); }
  return h;
}

/* ─ террейн ─ */
function groundTexture(){ var cv=document.createElement('canvas');
  cv.width=cv.height=256; var g=cv.getContext('2d');
  g.fillStyle='#cfcfcf'; g.fillRect(0,0,256,256);
  var rng=mulberry(S.seed*3+1);
  for(var i=0;i<9000;i++){ var v=178+rng()*66|0;
    g.fillStyle='rgb('+v+','+v+','+v+')';
    g.fillRect(rng()*256|0, rng()*256|0, 1+rng()*2|0, 1+rng()*2|0); }
  for(i=0;i<700;i++){ var v2=160+rng()*56|0;
    g.fillStyle='rgba('+v2+','+v2+','+v2+',0.5)';
    var x=rng()*256, y=rng()*256;
    g.fillRect(x,y,1,3+rng()*4); }
  var tex=new THREE.CanvasTexture(cv);
  tex.wrapS=tex.wrapT=THREE.RepeatWrapping; tex.repeat.set(30,30);
  tex.colorSpace=THREE.SRGBColorSpace; return tex; }

function distToSeg(x,z,s){ var dx=s[2]-s[0], dz=s[3]-s[1];
  var L2=dx*dx+dz*dz, t=L2? clamp(((x-s[0])*dx+(z-s[1])*dz)/L2,0,1):0;
  var qx=s[0]+t*dx, qz=s[1]+t*dz; return Math.hypot(x-qx,z-qz); }

function buildTerrain(){
  var geo=new THREE.PlaneGeometry(TSIZE,TSIZE,TSEG,TSEG);
  geo.rotateX(-Math.PI/2);
  var pos=geo.attributes.position, n=pos.count;
  var colors=new Float32Array(n*3);
  var P=getPal();
  var cGrass=col(P.grass), cGrass2=col(P.grass2), cDry=col(P.dry),
      cRock=col(P.rock), cSand=col(P.sand), cPath=col(P.path), cField=col(P.field),
      cPave=col(ERACOL[S.id].pave), isCap=S.id==='capital',
      cDeepB=col(P.deep).multiplyScalar(0.55);
  // корзины зданий для «вытоптанности»
  var bgrid={};
  S.buildings.forEach(function(b){ if(b[0]==='field'||b[0]==='pen') return;
    var k=(b[1]/28|0)+':'+(b[2]/28|0); (bgrid[k]=bgrid[k]||[]).push(b); });
  function trampled(x,z){ var gx=x/28|0, gz=z/28|0, best=1e9;
    for(var i=-1;i<=1;i++) for(var j=-1;j<=1;j++){
      var L=bgrid[(gx+i)+':'+(gz+j)]; if(!L) continue;
      for(var q=0;q<L.length;q++){ var d=Math.hypot(x-L[q][1],z-L[q][2]);
        if(d<best) best=d; } }
    return best; }
  var tmp=new THREE.Color();
  for(var i=0;i<n;i++){
    var x=pos.getX(i), z=pos.getZ(i), h=groundH(x,z), dc2=Math.hypot(x,z);
    pos.setY(i,h);
    var m=fbm(x*0.013+40,z*0.013,3);
    tmp.copy(cGrass).lerp(cGrass2, m).lerp(cDry, 0.6*sstep((fbm(x*0.013,z*0.013+9,3)-0.46)/0.34));
    // сырость у воды
    var rd=riverDist(x,z), ss=seaS(x,z);
    if(S.river&&rd<S.river[3]*2.6) tmp.lerp(cGrass2, 0.5*(1-rd/(S.river[3]*2.6)));
    // песок на берегу и в русле, глубина темнеет
    if(h<0.9) tmp.lerp(cSand, sstep((0.9-h)/1.6));
    if(h<WATER_Y-0.3) tmp.lerp(cDeepB, sstep((WATER_Y-0.3-h)/5.5));
    if(S.sea&&ss>-46&&h>-2) tmp.lerp(cSand, sstep((ss+46)/60)*0.9);
    // камень на кручах
    var e=0.9; var slope=Math.abs(groundH(x+e,z)-h)+Math.abs(groundH(x,z+e)-h);
    tmp.lerp(cRock, sstep((slope-1.05)/1.3));
    // тропы и площадь
    var sd=1e9; for(var st=0;st<S.streets.length;st++){
      var d2=distToSeg(x,z,S.streets[st]); if(d2<sd) sd=d2; }
    var sw=4.2;
    if(sd<sw+4) tmp.lerp(isCap?cPave:cPath, 0.85*(1-sstep((sd-sw*0.5)/(sw*0.9))));
    var pz=S.pois.plaza; if(pz){ var pd=Math.hypot(x-pz[0],z-pz[1]);
      if(pd<34) tmp.lerp(isCap?cPave:cPath, 0.85*(1-sstep((pd-18)/14))); }
    var tr=trampled(x,z); if(tr<14) tmp.lerp(cPath, (isCap?0.45:0.6)*(1-tr/14));
    var townDust=sstep(1-dc2/(FLATR[S.id]*0.8));
    if(townDust>0) tmp.lerp(cPath, townDust*(isCap?0.34:0.44)*(0.5+0.5*fbm(x*0.045,z*0.045,2)));
    // поля: тёмная пашня
    for(var f=0;f<S.pois.fields.length;f++){ var ff=S.pois.fields[f];
      var fd=Math.hypot(x-ff[0],z-ff[1]); if(fd<20) tmp.lerp(cField,0.5*(1-sstep((fd-12)/8))); }
    var g2=0.93+fbm(x*0.09,z*0.09,2)*0.14;
    colors[i*3]=tmp.r*g2; colors[i*3+1]=tmp.g*g2; colors[i*3+2]=tmp.b*g2;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors,3));
  geo.computeVertexNormals();
  var mat=new THREE.MeshLambertMaterial({map:groundTexture(), vertexColors:true});
  var mesh=new THREE.Mesh(geo,mat); mesh.receiveShadow=true;
  R3.scene.add(mesh); R3.terrain=mesh;
  // юбка-продолжение: рельеф за краем площадки, чтобы мир не обрывался
  var ap=new THREE.PlaneGeometry(4400,4400,56,56); ap.rotateX(-Math.PI/2);
  var app=ap.attributes.position;
  var apc=new Float32Array(app.count*3);
  var edgeC=col(P.grass).lerp(col(P.dry),0.6).multiplyScalar(0.94);
  var deepC=col(P.deep).multiplyScalar(0.8);
  for(var ai=0;ai<app.count;ai++){
    var ax=app.getX(ai), az=app.getZ(ai);
    var cx2=clamp(ax,-596,596), cz3=clamp(az,-596,596);
    var hh2=groundH(cx2,cz3)-0.5;
    var far2=Math.max(Math.abs(ax),Math.abs(az))-596;
    if(far2>0&&hh2>WATER_Y+0.5) hh2+=fbm(ax*0.002,az*0.002,3)*S.rugg*30*sstep(far2/700);
    app.setY(ai,hh2);
    var vf=0.9*(0.82+0.36*fbm(ax*0.004,az*0.004,3));
    var uc=edgeC;
    if(hh2<WATER_Y-0.5){ uc=deepC; vf=1; }
    apc[ai*3]=uc.r*vf; apc[ai*3+1]=uc.g*vf; apc[ai*3+2]=uc.b*vf; }
  ap.setAttribute('color',new THREE.BufferAttribute(apc,3));
  ap.computeVertexNormals();
  var apm=new THREE.Mesh(ap,new THREE.MeshLambertMaterial({vertexColors:true}));
  R3.scene.add(apm);
  // вода
  var P2=getPal();
  var wgeo=new THREE.PlaneGeometry(5800,5800,32,32); wgeo.rotateX(-Math.PI/2);
  var wmat=new THREE.MeshPhongMaterial({color:col(P2.water), transparent:true,
    opacity:0.93, shininess:130, specular:new THREE.Color('#9ab'),
    emissive:new THREE.Color(P2.deep), emissiveIntensity:0.35});
  var wm=new THREE.Mesh(wgeo,wmat); wm.position.y=WATER_Y;
  R3.scene.add(wm); R3.water=wm;
}

/* ─ склейка геометрий ─ */
var PRIM = {};
function prims(){
  PRIM.box=new THREE.BoxGeometry(1,1,1);
  PRIM.cyl=new THREE.CylinderGeometry(0.5,0.5,1,8);
  PRIM.cyl6=new THREE.CylinderGeometry(0.5,0.5,1,6);
  PRIM.cone=new THREE.ConeGeometry(0.5,1,8);
  PRIM.cone3=new THREE.CylinderGeometry(0.02,0.5,1,3);
  // двускатная призма: конёк вдоль X, основание 1×1 в XZ, конёк на y=1
  var pv=[
    -0.5,0,0.5,  0.5,0,0.5,  0.5,1,0,   -0.5,0,0.5, 0.5,1,0,  -0.5,1,0,
     0.5,0,-0.5, -0.5,0,-0.5, -0.5,1,0,  0.5,0,-0.5, -0.5,1,0, 0.5,1,0,
     0.5,0,0.5,  0.5,0,-0.5,  0.5,1,0,
    -0.5,0,-0.5, -0.5,0,0.5, -0.5,1,0,
    -0.5,0,-0.5, 0.5,0,-0.5, 0.5,0,0.5, -0.5,0,-0.5, 0.5,0,0.5, -0.5,0,0.5];
  var pg=new THREE.BufferGeometry();
  pg.setAttribute('position',new THREE.Float32BufferAttribute(pv,3));
  pg.computeVertexNormals();
  var pidx=[]; for(var pi3=0;pi3<pv.length/3;pi3++) pidx.push(pi3);
  pg.setIndex(pidx);
  PRIM.prism=pg;
  PRIM.sph=new THREE.SphereGeometry(0.5,7,5);
  PRIM.ico=new THREE.IcosahedronGeometry(0.5,0);
}
var _m4=new THREE.Matrix4(), _q=new THREE.Quaternion(), _e=new THREE.Euler(),
    _v3=new THREE.Vector3(), _s3=new THREE.Vector3(), _n3=new THREE.Matrix3();

function Bag(){ this.pos=[]; this.nor=[]; this.col=[]; this.idx=[]; this.base=0; }
Bag.prototype.put=function(geo,c,x,y,z,rx,ry,rz,sx,sy,sz,ao){
  _e.set(rx||0,ry||0,rz||0); _q.setFromEuler(_e);
  _v3.set(x,y,z); _s3.set(sx,sy||sx,sz||sx);
  _m4.compose(_v3,_q,_s3); _n3.getNormalMatrix(_m4);
  var p=geo.attributes.position, nr=geo.attributes.normal, ix=geo.index;
  var vp=new THREE.Vector3(), vn=new THREE.Vector3();
  var minY=1e9,maxY=-1e9;
  if(ao){ for(var i=0;i<p.count;i++){ var yy=p.getY(i);
      if(yy<minY)minY=yy; if(yy>maxY)maxY=yy; } }
  for(var i2=0;i2<p.count;i2++){
    vp.set(p.getX(i2),p.getY(i2),p.getZ(i2));
    var aoF=1; if(ao&&maxY>minY) aoF=lerp(0.82,1.04,(vp.y-minY)/(maxY-minY));
    vp.applyMatrix4(_m4);
    vn.set(nr.getX(i2),nr.getY(i2),nr.getZ(i2)).applyMatrix3(_n3).normalize();
    this.pos.push(vp.x,vp.y,vp.z); this.nor.push(vn.x,vn.y,vn.z);
    this.col.push(c.r*aoF,c.g*aoF,c.b*aoF);
  }
  if(ix){ for(var j=0;j<ix.count;j++) this.idx.push(ix.getX(j)+this.base); }
  else { for(var j2=0;j2<p.count;j2++) this.idx.push(j2+this.base); }
  this.base+=p.count;
};
Bag.prototype.mesh=function(mat){
  var g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.Float32BufferAttribute(this.pos,3));
  g.setAttribute('normal',new THREE.Float32BufferAttribute(this.nor,3));
  g.setAttribute('color',new THREE.Float32BufferAttribute(this.col,3));
  g.setIndex(this.idx);
  return new THREE.Mesh(g,mat);
};

/* ─ здания ─ */
function buildTown(){
  prims();
  var bag=new Bag(), rng=mulberry(S.seed*7+3), E=ERACOL[S.id], P=getPal();
  G.fireSrc=[]; G.smokeSrc=[]; G.colliders=[];
  var GY=function(x,z){ return groundH(x,z); };

  function collide(x,z,r){ G.colliders.push([x,z,r]); }

  S.buildings.forEach(function(b){
    var t=b[0], x=b[1], z=b[2], rot=b[3], sx=b[4], sz=b[5], h=b[6];
    var y=GY(x,z), c;
    if(t==='house'||t==='house2'){
      var two=t==='house2';
      c=colVar(rng,pick(rng,E.house),0.13);
      bag.put(PRIM.box,c,x,y+h/2,z,0,rot,0,sx,h,sz,1);
      collide(x,z,Math.max(sx,sz)*0.62);
      var dark=col(E.door);
      var dx=Math.cos(rot), dz=Math.sin(rot);
      bag.put(PRIM.box,dark,x+dx*(sx/2),y+1.05,z+dz*(sx/2),0,rot,0,0.14,2.1,1.0);
      if(rng()<0.3) G.fireSrc.push([x+dx*(sx/2+0.35),y+1.0,z+dz*(sx/2+0.35),0.42]);
      bag.put(PRIM.box,dark,x-dz*(sz/2)*0.9+dx*sx*0.18,y+h*0.62,z+dx*(sz/2)*0.9+dz*sx*0.18,
        0,rot,0,0.8,0.7,0.14);
      if(S.id==='bronze'){                       // плоская кровля с парапетом
        var rc=colVar(rng,pick(rng,E.roof),0.05);
        bag.put(PRIM.box,rc,x,y+h+0.12,z,0,rot,0,sx*1.06,0.26,sz*1.06);
        var pc=c.clone().multiplyScalar(0.92);
        bag.put(PRIM.box,pc,x+dx*(sx/2)*1.02,y+h+0.5,z+dz*(sx/2)*1.02,0,rot,0,0.2,0.55,sz*1.06);
        bag.put(PRIM.box,pc,x-dx*(sx/2)*1.02,y+h+0.5,z-dz*(sx/2)*1.02,0,rot,0,0.2,0.55,sz*1.06);
        bag.put(PRIM.box,pc,x-dz*(sz/2)*1.02,y+h+0.5,z+dx*(sz/2)*1.02,0,rot,0,sx*1.06,0.55,0.2);
        bag.put(PRIM.box,pc,x+dz*(sz/2)*1.02,y+h+0.5,z-dx*(sz/2)*1.02,0,rot,0,sx*1.06,0.55,0.2);
        var wc=col(E.wood);                      // навес у входа
        if(rng()<0.5){ bag.put(PRIM.box,wc,x+dx*(sx/2+0.9),y+2.25,z+dz*(sx/2+0.9),
            0,rot,0.06,2.0,0.1,1.7);
          bag.put(PRIM.cyl,wc,x+dx*(sx/2+1.6)-dz*0.7,y+1.1,z+dz*(sx/2+1.6)+dx*0.7,0,0,0,0.14,2.2,0.14);
          bag.put(PRIM.cyl,wc,x+dx*(sx/2+1.6)+dz*0.7,y+1.1,z+dz*(sx/2+1.6)-dx*0.7,0,0,0,0.14,2.2,0.14); }
        if(rng()<0.3) G.smokeSrc.push([x,y+h+0.4,z,0.5]);
      } else {                                   // скатная крыша (столица/хутора)
        if(two){ var c2=c.clone().multiplyScalar(1.05);   // второй этаж со свесом
          bag.put(PRIM.box,c2,x,y+h+h*0.42,z,0,rot,0,sx*1.1,h*0.84,sz*1.1,1);
          bag.put(PRIM.box,col(E.wood),x,y+h+0.05,z,0,rot,0,sx*1.14,0.16,sz*1.14);
          bag.put(PRIM.box,col(E.door),x+Math.cos(rot)*(sx*0.55),y+h+h*0.5,
            z+Math.sin(rot)*(sx*0.55),0,rot,0,0.1,0.8,0.8); }
        var top=y+h+(two?h*0.84:0);
        var rc2=colVar(rng,pick(rng,E.roof),0.07);
        var rw=(two?sx*1.1:sx)*1.18, rd=(two?sz*1.1:sz)*1.18;
        bag.put(PRIM.prism,rc2,x,top,z,0,rot,0,rw,h*0.62,rd);
        bag.put(PRIM.box,col(E.wood),x,top+0.02,z,0,rot,0,rw*0.98,0.12,rd*0.98);
        if(rng()<0.35) G.smokeSrc.push([x,top+h*0.5,z,0.6]);
      }
    }
    else if(t==='hut'){
      c=colVar(rng,pick(rng,E.house),0.07);
      bag.put(PRIM.cyl6,c,x,y+h*0.42,z,0,rot,0,sx*2,h*0.84,sx*2,1);
      var rc3=colVar(rng,pick(rng,ERACOL.neolithic.roof),0.06);
      bag.put(PRIM.cone,rc3,x,y+h*0.84+h*0.5,z,0,rot+0.3,0,sx*2.55,h*1.0,sx*2.55);
      bag.put(PRIM.cyl,col(E.wood),x,y+h*1.5,z,0,0,0,0.1,h*0.7,0.1);
      bag.put(PRIM.box,col(E.door),x+Math.cos(rot)*sx*0.97,y+0.8,z+Math.sin(rot)*sx*0.97,
        0,rot,0,0.2,1.6,1.1);
      collide(x,z,sx+0.3);
      if(rng()<0.55) G.smokeSrc.push([x,y+h*1.9,z,0.5]);
    }
    else if(t==='tent'){
      c=colVar(rng,'#8a6a4e',0.1);
      bag.put(PRIM.cone,c,x,y+h*0.45,z,0,rot,0,sx*2.1,h*0.95,sx*2.1,1);
      for(var pp=0;pp<4;pp++){ var pa=rot+pp*1.7;
        bag.put(PRIM.cyl,col(E.wood),x+Math.cos(pa)*0.4,y+h*0.95,z+Math.sin(pa)*0.4,
          Math.cos(pa)*0.35,0,Math.sin(pa)*0.35,0.07,h*0.55,0.07); }
      bag.put(PRIM.box,col('#3f3020'),x+Math.cos(rot)*sx*1.0,y+0.65,z+Math.sin(rot)*sx*1.0,
        0,rot,0,0.2,1.3,0.9);
      collide(x,z,sx+0.2);
    }
    else if(t==='granary'){
      var wcol=col(E.wood);
      for(var lg=0;lg<4;lg++){ var lx=(lg%2?0.9:-0.9), lz=(lg<2?0.9:-0.9);
        var ca=Math.cos(rot), sa=Math.sin(rot);
        bag.put(PRIM.cyl,wcol,x+lx*ca-lz*sa,y+0.55,z+lx*sa+lz*ca,0,0,0,0.16,1.1,0.16); }
      c=colVar(rng,pick(rng,E.house),0.08);
      bag.put(PRIM.box,c,x,y+1.1+h*0.3,z,0,rot,0,sx*0.75,h*0.6,sz*0.75,1);
      bag.put(PRIM.cone,colVar(rng,pick(rng,ERACOL.neolithic.roof),0.05),
        x,y+1.1+h*0.6+0.55,z,0,rot,0,sx*1.05,1.1,sz*1.05);
      bag.put(PRIM.box,wcol,x+Math.cos(rot)*1.2,y+0.6,z+Math.sin(rot)*1.2,0,rot,0.5,0.5,1.6,0.08);
      collide(x,z,Math.max(sx,sz)*0.6);
    }
    else if(t==='temple'){ buildTemple(bag,rng,x,GY(x,z),z,rot,sx,sz,h,E); collide(x,z,Math.max(sx,sz)*0.62); }
    else if(t==='market'){
      var wc2=col(E.wood);
      var cloths=['#a05a40','#b3763f','#8f7a4a','#a88a56'];
      var ca2=Math.cos(rot), sa2=Math.sin(rot);
      for(var mp=0;mp<4;mp++){ var mx=(mp%2?sx/2:-sx/2), mz=(mp<2?sz/2:-sz/2);
        bag.put(PRIM.cyl,wc2,x+mx*ca2-mz*sa2,y+1.35,z+mx*sa2+mz*ca2,0,0,0,0.13,2.7,0.13); }
      bag.put(PRIM.box,colVar(rng,pick(rng,cloths),0.1),x,y+2.75,z,0.07,rot,0.05,sx*1.15,0.12,sz*1.2);
      bag.put(PRIM.box,wc2,x,y+0.5,z,0,rot,0,sx*0.8,1.0,sz*0.5,1);
      bag.put(PRIM.sph,col('#b06a3f'),x+ca2*0.8,y+1.15,z+sa2*0.8,0,0,0,0.4,0.5,0.4);
      bag.put(PRIM.sph,col('#8a8a54'),x-ca2*0.9,y+1.12,z-sa2*0.9,0,0,0,0.45,0.4,0.45);
      bag.put(PRIM.box,col('#c9b384'),x+sa2*0.9,y+1.14,z-ca2*0.5,0,rot,0,0.7,0.28,0.5);
      collide(x,z,Math.max(sx,sz)*0.62);
    }
    else if(t==='well'){
      var stc=col(E.wallS);
      bag.put(PRIM.cyl,stc,x,y+0.45,z,0,0,0,2.0,0.9,2.0,1);
      bag.put(PRIM.cyl,col('#222831'),x,y+0.86,z,0,0,0,1.6,0.12,1.6);
      var wc3=col(E.wood);
      bag.put(PRIM.cyl,wc3,x-0.95,y+1.5,z,0,0,0,0.12,2.2,0.12);
      bag.put(PRIM.cyl,wc3,x+0.95,y+1.5,z,0,0,0,0.12,2.2,0.12);
      bag.put(PRIM.cyl,wc3,x,y+2.5,z,0,0,Math.PI/2,0.09,2.1,0.09);
      bag.put(PRIM.box,wc3,x+0.3,y+1.8,z,0,0,0,0.34,0.4,0.34);
      collide(x,z,1.4);
    }
    else if(t==='fire'){
      var rr=sx*0.9;
      for(var fs=0;fs<7;fs++){ var fa=fs/7*6.28;
        bag.put(PRIM.ico,col('#6d675e'),x+Math.cos(fa)*rr,y+0.16,z+Math.sin(fa)*rr,
          rng()*3,rng()*3,0,0.42,0.34,0.42); }
      bag.put(PRIM.cyl,col('#3a2c1c'),x,y+0.2,z,0.4,0.3,1.2,0.16,1.3,0.16);
      bag.put(PRIM.cyl,col('#463622'),x,y+0.2,z,-0.5,1.5,1.2,0.16,1.2,0.16);
      G.fireSrc.push([x,y+0.55,z,1.6]); G.smokeSrc.push([x,y+0.8,z,1.0]);
      collide(x,z,1.1);
    }
    else if(t==='stela'){
      var sc2=col(E.stoneT);
      bag.put(PRIM.box,sc2,x,y+0.25,z,0,rot,0,sx*1.4,0.5,sx*1.4);
      bag.put(PRIM.box,sc2,x,y+h/2,z,0,rot,0.02,sx*0.62,h,sx*0.4,1);
      var bandc=sc2.clone().multiplyScalar(0.8);
      for(var sb=1;sb<4;sb++) bag.put(PRIM.box,bandc,x,y+h*sb/4,z,0,rot,0,sx*0.64,0.1,sx*0.42);
      collide(x,z,sx);
    }
    else if(t==='tower'){
      var tc=col(E.wallS);
      bag.put(PRIM.box,tc,x,y+h/2,z,0,rot,0,sx,h,sz,1);
      bag.put(PRIM.box,tc.clone().multiplyScalar(1.06),x,y+h+0.3,z,0,rot,0,sx*1.18,0.6,sz*1.18);
      for(var mm=0;mm<4;mm++){ var ma=rot+mm*Math.PI/2;
        bag.put(PRIM.box,tc,x+Math.cos(ma)*sx*0.5,y+h+0.95,z+Math.sin(ma)*sx*0.5,0,ma,0,0.7,0.7,0.7); }
      collide(x,z,Math.max(sx,sz)*0.7);
    }
    else if(t==='gate'){
      var gc=col(E.wallS);
      var gx=Math.cos(rot), gz=Math.sin(rot);
      bag.put(PRIM.box,gc,x-gx*sx*0.42,y+ h*0.5,z-gz*sx*0.42,0,rot,0,5.5,h,7,1);
      bag.put(PRIM.box,gc,x+gx*sx*0.42,y+h*0.5,z+gz*sx*0.42,0,rot,0,5.5,h,7,1);
      bag.put(PRIM.box,gc,x,y+h*0.86,z,0,rot,0,sx,h*0.3,6);
      var wd=col('#5f4a34');
      bag.put(PRIM.box,wd,x-gx*sx*0.3,y+h*0.31,z-gz*sx*0.3,0,rot+1.05,0,0.3,h*0.62,4.2);
      bag.put(PRIM.box,wd,x+gx*sx*0.3,y+h*0.31,z+gz*sx*0.3,0,rot-1.05,0,0.3,h*0.62,4.2);
      collide(x-gx*sx*0.42,z-gz*sx*0.42,3.4); collide(x+gx*sx*0.42,z+gz*sx*0.42,3.4);
      G.fireSrc.push([x-gx*sx*0.30,y+3.4,z-gz*sx*0.30,0.9]);
      G.fireSrc.push([x+gx*sx*0.30,y+3.4,z+gz*sx*0.30,0.9]);
    }
    else if(t==='wall'){
      var wc4=col(S.id==='neolithic'?E.wood:E.wallS);
      if(S.id==='neolithic'){                          // частокол
        bag.put(PRIM.box,wc4,x,y+h/2,z,0,rot,0,sx,h,0.5,1);
        var nplk=Math.max(3,sx/1.4|0);
        for(var pk=0;pk<nplk;pk++){ var pt=(pk+0.5)/nplk-0.5;
          bag.put(PRIM.cone,wc4.clone().multiplyScalar(0.9),
            x+Math.cos(rot)*pt*sx,y+h+0.3,z+Math.sin(rot)*pt*sx,0,0,0,0.5,0.7,0.5); }
      } else {
        bag.put(PRIM.box,wc4,x,y+h/2,z,0,rot,0,sx,h,sz,1);
        bag.put(PRIM.box,wc4.clone().multiplyScalar(1.05),x,y+h+0.14,z,0,rot,0,sx,0.3,sz*1.35);
        var nm=Math.max(2,sx/3.2|0);
        for(var mq=0;mq<nm;mq++){ var mt=(mq+0.5)/nm-0.5;
          bag.put(PRIM.box,wc4,x+Math.cos(rot)*mt*sx,y+h+0.75,z+Math.sin(rot)*mt*sx,
            0,rot,0,1.3,0.9,sz*0.5); } }
      // коллизия цепочкой кругов
      var wl=Math.ceil(sx/2.2);
      for(var wq=0;wq<=wl;wq++){ var wt2=wq/wl-0.5;
        collide(x+Math.cos(rot)*wt2*sx, z+Math.sin(rot)*wt2*sx, sz*0.7+0.9); }
    }
    else if(t==='pen'){
      var pcol=col(E.wood);
      var hw2=sx/2, hd=sz/2, corners=[[-hw2,-hd],[hw2,-hd],[hw2,hd],[-hw2,hd]];
      for(var pe=0;pe<4;pe++){
        var A=corners[pe], B=corners[(pe+1)%4];
        var steps=Math.max(2,Math.hypot(B[0]-A[0],B[1]-A[1])/2.4|0);
        for(var pi2=0;pi2<=steps;pi2++){ var ptx=lerp(A[0],B[0],pi2/steps), ptz=lerp(A[1],B[1],pi2/steps);
          var ca3=Math.cos(rot), sa3=Math.sin(rot);
          var wx=x+ptx*ca3-ptz*sa3, wz=z+ptx*sa3+ptz*ca3;
          bag.put(PRIM.cyl,pcol,wx,GY(wx,wz)+0.55,wz,0,0,0,0.11,1.1,0.11); }
        var midx=x+((A[0]+B[0])/2)*Math.cos(rot)-((A[1]+B[1])/2)*Math.sin(rot);
        var midz=z+((A[0]+B[0])/2)*Math.sin(rot)+((A[1]+B[1])/2)*Math.cos(rot);
        var ang2=Math.atan2((B[1]-A[1]),(B[0]-A[0]))+rot;
        var LL=Math.hypot(B[0]-A[0],B[1]-A[1]);
        bag.put(PRIM.box,pcol,midx,GY(midx,midz)+0.72,midz,0,-ang2,0,LL,0.09,0.09);
        bag.put(PRIM.box,pcol,midx,GY(midx,midz)+0.38,midz,0,-ang2,0,LL,0.09,0.09);
      }
    }
    else if(t==='field'){
      var fg=new THREE.PlaneGeometry(sx,sz,6,4); fg.rotateX(-Math.PI/2);
      var fp=fg.attributes.position;
      for(var fv=0;fv<fp.count;fv++){
        var fx2=fp.getX(fv), fz2=fp.getZ(fv);
        var wx2=x+fx2*Math.cos(rot)-fz2*Math.sin(rot), wz2=z+fx2*Math.sin(rot)+fz2*Math.cos(rot);
        fp.setY(fv, groundH(wx2,wz2)-groundH(x,z)+0.12); }
      fg.computeVertexNormals();
      bag2Add(bag,fg,col(P.field).multiplyScalar(1.06),x,GY(x,z),z,rot);
      var rows=Math.max(3,sz/2.6|0), cropc=col(S.id==='neolithic'?'#9aa050':'#b0a050');
      for(var rw2=0;rw2<rows;rw2++){ var rz2=(rw2+0.5)/rows*sz-sz/2;
        var rxx=x-rz2*Math.sin(rot), rzz=z+rz2*Math.cos(rot);
        bag.put(PRIM.box,colVar(rng,'#a89a50',0.12),rxx,GY(rxx,rzz)+0.42,rzz,
          0,rot,0,sx*0.92,0.5,0.5); }
    }
    else if(t==='jetty'){
      var jw=col(E.wood);
      bag.put(PRIM.box,jw,x,WATER_Y+1.0,z,0,rot,0,sx,0.24,sz,1);
      var np2=Math.max(2,sx/4|0);
      for(var jp=0;jp<=np2;jp++){ var jt=jp/np2-0.5;
        var jx=x+Math.cos(rot)*jt*sx, jz=z+Math.sin(rot)*jt*sx;
        bag.put(PRIM.cyl,jw,jx,WATER_Y+0.35,jz-1.2,0,0,0,0.16,1.6,0.16);
        bag.put(PRIM.cyl,jw,jx,WATER_Y+0.35,jz+1.2,0,0,0,0.16,1.6,0.16); }
    }
    else if(t==='boat'){
      var bw=col(E.wood).multiplyScalar(0.9);
      var by=Math.max(GY(x,z)+0.3,WATER_Y+0.16);
      bag.put(PRIM.box,bw,x,by,z,0,rot,0,sx*0.8,0.5,sz,1);
      bag.put(PRIM.cone3,bw,x+Math.cos(rot)*sx*0.5,by+0.1,z+Math.sin(rot)*sx*0.5,
        1.5,rot+1.57,0,sz,sx*0.25,0.6);
      bag.put(PRIM.cone3,bw,x-Math.cos(rot)*sx*0.5,by+0.1,z-Math.sin(rot)*sx*0.5,
        1.5,rot-1.57,0,sz,sx*0.25,0.6);
    }
    else if(t==='totem'){
      var tw=col(E.wood);
      bag.put(PRIM.cyl,tw,x,y+h/2,z,0,0,0,sx*0.8,h,sx*0.8,1);
      for(var tb=1;tb<4;tb++) bag.put(PRIM.cyl,colVar(rng,'#9c4f3a',0.2),
        x,y+h*tb/4,z,0,0,0,sx*0.92,0.28,sx*0.92);
      bag.put(PRIM.sph,tw,x,y+h+0.3,z,0,0,0,0.6,0.5,0.6);
      collide(x,z,0.8);
    }
    else if(t==='rack'){
      var rw3=col(E.wood);
      bag.put(PRIM.cyl,rw3,x-sx/2,y+h/2,z,0,0,0,0.12,h,0.12);
      bag.put(PRIM.cyl,rw3,x+sx/2,y+h/2,z,0,0,0,0.12,h,0.12);
      bag.put(PRIM.cyl,rw3,x,y+h*0.92,z,0,0,Math.PI/2,0.08,sx,0.08);
      for(var fh=0;fh<4;fh++) bag.put(PRIM.box,col('#c9c2a8'),
        x-sx/2+((fh+0.7)/4.4)*sx,y+h*0.7,z,0.2,0,0,0.16,0.5,0.05);
      collide(x,z,1.2);
    }
    else if(t==='torch'){
      bag.put(PRIM.cyl,col(E.wood),x,y+h/2,z,0,0,0,0.16,h,0.16);
      bag.put(PRIM.cyl,col('#333'),x,y+h+0.08,z,0,0,0,0.34,0.3,0.34);
      G.fireSrc.push([x,y+h+0.3,z,0.85]);
      collide(x,z,0.4);
    }
    else if(t==='yard'){
      var yc=colVar(rng,pick(rng,E.house),0.08).multiplyScalar(0.92);
      var ca4=Math.cos(rot), sa4=Math.sin(rot);
      bag.put(PRIM.box,yc,x-sa4*sz/2,y+h/2,z+ca4*sz/2,0,rot,0,sx,h,0.35,1);
      bag.put(PRIM.box,yc,x+sa4*sz/2,y+h/2,z-ca4*sz/2,0,rot,0,sx,h,0.35,1);
      bag.put(PRIM.box,yc,x+ca4*sx/2,y+h/2,z+sa4*sx/2,0,rot,0,0.35,h,sz*0.55,1);
      collide(x,z,1.8);
    }
  });
  var mat=new THREE.MeshLambertMaterial({vertexColors:true});
  var mesh=bag.mesh(mat); mesh.castShadow=true; mesh.receiveShadow=true;
  R3.scene.add(mesh); R3.town=mesh;
  buildColliderGrid();
  // имя святилища — по первому богу народа
  var tp=S.pois.temple;
  if(tp){ var txt=S.id==='neolithic'? 'Столбы предков':
      'Святилище '+((S.gods&&S.gods[0])||'');
    var cvt=document.createElement('canvas'); cvt.width=512; cvt.height=80;
    var gt=cvt.getContext('2d');
    gt.textAlign='center'; gt.fillStyle='#f4e9cd';
    gt.font='bold 37px Georgia'; gt.shadowColor='#000'; gt.shadowBlur=8;
    gt.fillText(txt,256,50);
    var ttx=new THREE.CanvasTexture(cvt); ttx.colorSpace=THREE.SRGBColorSpace;
    var tsp=new THREE.Sprite(new THREE.SpriteMaterial({map:ttx,transparent:true,
      depthTest:false}));
    tsp.scale.set(19,3.0,1); tsp.renderOrder=29;
    var th3={capital:16,bronze:19,neolithic:7}[S.id]||12;
    tsp.position.set(tp[0],groundH(tp[0],tp[1])+th3,tp[1]);
    R3.scene.add(tsp); G.templeLabel=tsp; }
}
function bag2Add(bag,geo,c,x,y,z,ry){ // готовая геометрия в общий мешок
  _e.set(0,ry||0,0); _q.setFromEuler(_e); _v3.set(x,y,z); _s3.set(1,1,1);
  _m4.compose(_v3,_q,_s3); _n3.getNormalMatrix(_m4);
  var p=geo.attributes.position, nr=geo.attributes.normal, ix=geo.index;
  var vp=new THREE.Vector3(), vn=new THREE.Vector3();
  for(var i=0;i<p.count;i++){
    vp.set(p.getX(i),p.getY(i),p.getZ(i)).applyMatrix4(_m4);
    vn.set(nr.getX(i),nr.getY(i),nr.getZ(i)).applyMatrix3(_n3).normalize();
    bag.pos.push(vp.x,vp.y,vp.z); bag.nor.push(vn.x,vn.y,vn.z);
    bag.col.push(c.r,c.g,c.b); }
  if(ix){ for(var j=0;j<ix.count;j++) bag.idx.push(ix.getX(j)+bag.base); }
  else { for(var j2=0;j2<p.count;j2++) bag.idx.push(j2+bag.base); }
  bag.base+=p.count;
}

function buildTemple(bag,rng,x,y,z,rot,sx,sz,h,E){
  var stone=col(E.stoneT), wood=col(E.wood);
  var ca=Math.cos(rot), sa=Math.sin(rot);
  function W(lx,lz){ return [x+lx*ca-lz*sa, z+lx*sa+lz*ca]; }
  if(S.id==='capital'){
    // фронтон смотрит на площадь (+z): подий, целла, шестиколонный портик
    bag.put(PRIM.box,stone,x,y+0.45,z,0,rot,0,sx*1.22,0.9,sz*1.2,1);
    bag.put(PRIM.box,stone,x,y+1.15,z,0,rot,0,sx*1.1,0.62,sz*1.08,1);
    var st3=W(0,sz*0.62);
    bag.put(PRIM.box,stone,st3[0],y+0.62,st3[1],0,rot,0,sx*0.66,1.24,sz*0.16);
    var base=y+1.42;
    var cw=col(E.col);
    bag.put(PRIM.box,colVar(rng,E.stoneT,0.05),x,base+h*0.36,z,0,rot,-0,
      sx*0.78,h*0.72,sz*0.66,1);
    var cn=6;
    for(var i=0;i<cn;i++){ var cx=(i/(cn-1)-0.5)*sx*0.92;
      var pw=W(cx,sz*0.42);
      bag.put(PRIM.cyl,cw,pw[0],base+h*0.36,pw[1],0,0,0,0.62,h*0.72,0.62,1);
      bag.put(PRIM.box,cw,pw[0],base+h*0.74,pw[1],0,rot,0,0.95,0.18,0.95);
      var pw2=W(cx,sz*0.28);
      if(i===0||i===cn-1){
        bag.put(PRIM.cyl,cw,pw2[0],base+h*0.36,pw2[1],0,0,0,0.62,h*0.72,0.62,1); } }
    for(var i2=0;i2<4;i2++){ var czz=(i2/3-0.5)*sz*0.6;
      [-1,1].forEach(function(sg){ var pw3=W(sg*sx*0.46,czz-sz*0.05);
        bag.put(PRIM.cyl,cw,pw3[0],base+h*0.36,pw3[1],0,0,0,0.6,h*0.72,0.6,1); }); }
    bag.put(PRIM.box,stone,x,base+h*0.78,z,0,rot,0,sx*1.04,h*0.12,sz*1.02,1);
    // крыша: конёк вдоль глубины, фронтон к площади
    bag.put(PRIM.prism,colVar(rng,E.roof[0],0.05),x,base+h*0.84,z,0,rot+Math.PI/2,0,
      sz*1.14,h*0.34,sx*1.1);
    var ped=W(0,sz*0.53);
    bag.put(PRIM.prism,stone,ped[0],base+h*0.84,ped[1],0,rot+Math.PI/2,0,
      0.5,h*0.3,sx*1.02);
    // алтарь и огни перед входом
    var A=W(0,sz*0.86);
    bag.put(PRIM.box,stone,A[0],y+0.7,A[1],0,rot,0,2.4,1.4,1.5,1);
    G.fireSrc.push([A[0],y+1.75,A[1],1.15]); G.smokeSrc.push([A[0],y+2.0,A[1],0.7]);
    var T1=W(-sx*0.5,sz*0.75), T2=W(sx*0.5,sz*0.75);
    [T1,T2].forEach(function(T){
      bag.put(PRIM.cyl,wood,T[0],y+1.7,T[1],0,0,0,0.16,3.4,0.16);
      bag.put(PRIM.cyl,col('#333'),T[0],y+3.5,T[1],0,0,0,0.34,0.3,0.34);
      G.fireSrc.push([T[0],y+3.75,T[1],0.8]); });
  } else if(S.id==='bronze'){
    // зиккурат: три высоких яруса, длинный пандус, белёная целла
    var mud=col(E.wallS);
    var h1=h*0.4, h2=h*0.3, h3=h*0.22;
    bag.put(PRIM.box,mud,x,y+h1/2,z,0,rot,0,sx,h1,sz,1);
    bag.put(PRIM.box,colVar(rng,E.wallS,0.06),x,y+h1+h2/2,z,0,rot,0,sx*0.7,h2,sz*0.7,1);
    bag.put(PRIM.box,colVar(rng,E.wallS,0.06),x,y+h1+h2+h3/2,z,0,rot,0,sx*0.46,h3,sz*0.46,1);
    var topY=y+h1+h2+h3;
    bag.put(PRIM.box,col('#ddd2b4'),x,topY+h*0.09,z,0,rot,0,sx*0.24,h*0.18,sz*0.28,1);
    bag.put(PRIM.prism,col('#8f5a44'),x,topY+h*0.18,z,0,rot,0,sx*0.26,h*0.1,sz*0.32);
    // пандус-лестница от земли на первый ярус
    var rsteps=6, rstep=h1*2.4/rsteps;
    for(var rs2=0;rs2<rsteps;rs2++){
      var rh=h1*(1-rs2/rsteps);
      var RR=W(sx*0.5+(rs2+0.5)*rstep-0.6,0);
      bag.put(PRIM.box,colVar(rng,E.wallS,0.04),RR[0],y+rh/2,RR[1],0,rot,0,
        rstep+0.4,rh,3.6,1); }
    for(var bp=0;bp<4;bp++){ var bb=[[0.45,0.45],[-0.45,0.45],[0.45,-0.45],[-0.45,-0.45]][bp];
      var BP=W(bb[0]*sx,bb[1]*sz);
      bag.put(PRIM.cyl,col(E.wood),BP[0],y+h1+h*0.3,BP[1],0,0,0,0.14,h*0.6,0.14);
      bag.put(PRIM.box,colVar(rng,'#9c4f3a',0.3),BP[0],y+h1+h*0.52,BP[1],0,rot,0,0.08,1.1,0.6); }
    G.fireSrc.push([x,topY+h*0.2,z,1.05]); G.smokeSrc.push([x,topY+h*0.3,z,0.8]);
  }
}

/* коллизии: сетка кругов */
function buildColliderGrid(){
  G.cgrid={};
  G.colliders.forEach(function(c,i){
    var gx=c[0]/16|0, gz=c[1]/16|0;
    for(var a=gx-1;a<=gx+1;a++) for(var b=gz-1;b<=gz+1;b++){
      var k=a+':'+b; (G.cgrid[k]=G.cgrid[k]||[]).push(i); } });
}
function pushOut(px,pz,rad){
  var gx=px/16|0, gz=pz/16|0, L=G.cgrid[gx+':'+gz];
  if(!L) return [px,pz];
  for(var i=0;i<L.length;i++){ var c=G.colliders[L[i]];
    var dx=px-c[0], dz=pz-c[1], d2=dx*dx+dz*dz, mr=rad+c[2];
    if(d2<mr*mr&&d2>1e-6){ var d=Math.sqrt(d2), f=(mr-d)/d;
      px+=dx*f; pz+=dz*f; } }
  return [px,pz];
}

/* ─ растительность и камни ─ */
function treeGeo(kind,P){
  var bag=new Bag(), trunk=col(P.trunk), fol=col(kind===1?P.treeB:P.treeA);
  if(S.id==='bronze'&&kind===0){          // пальма
    bag.put(PRIM.cyl,trunk,0,2.2,0,0.06,0,0.1,0.34,4.4,0.34);
    for(var i=0;i<6;i++){ var a=i/6*6.28;
      bag.put(PRIM.cone3,fol,Math.cos(a)*1.5,4.6,Math.sin(a)*1.5,
        1.8,-a+1.57,0,1.1,3.2,0.5); }
    bag.put(PRIM.sph,fol.clone().multiplyScalar(0.9),0,4.5,0,0,0,0,1.0,0.7,1.0);
  } else if(kind===1&&S.id==='capital'){  // кипарис
    bag.put(PRIM.cyl,trunk,0,0.7,0,0,0,0,0.22,1.4,0.22);
    bag.put(PRIM.cone,fol,0,4.2,0,0,0,0,2.0,6.4,2.0,1);
  } else if(kind===2){                    // куст
    bag.put(PRIM.sph,fol,0,0.75,0,0,0,0,1.9,1.3,1.9,1);
    bag.put(PRIM.sph,fol.clone().multiplyScalar(1.12),0.7,0.6,0.4,0,0,0,1.2,0.9,1.2);
  } else {                                // раскидистое дерево
    bag.put(PRIM.cyl,trunk,0,1.5,0,0.05,0,0.1,0.45,3.0,0.45);
    bag.put(PRIM.sph,fol,0,4.0,0,0,0,0,4.6,3.1,4.6,1);
    bag.put(PRIM.sph,fol.clone().multiplyScalar(0.88),1.6,3.2,0.9,0,0,0,2.6,2.0,2.6);
    bag.put(PRIM.sph,fol.clone().multiplyScalar(1.1),-1.5,3.4,-0.7,0,0,0,2.4,1.9,2.4);
  }
  var g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.Float32BufferAttribute(bag.pos,3));
  g.setAttribute('normal',new THREE.Float32BufferAttribute(bag.nor,3));
  g.setAttribute('color',new THREE.Float32BufferAttribute(bag.col,3));
  g.setIndex(bag.idx); return g;
}
function scatterVeg(){
  var P=getPal(), rng=mulberry(S.seed*13+5);
  var kinds=[[],[],[]], rocks=[], reeds=[];
  function clearOf(x,z){
    if(riverDist(x,z)<(S.river?S.river[3]*1.5:0)) return false;
    if(seaS(x,z)>-52) return false;
    var g=pushOut(x,z,3.5); if(Math.abs(g[0]-x)+Math.abs(g[1]-z)>0.01) return false;
    for(var i=0;i<S.streets.length;i++) if(distToSeg(x,z,S.streets[i])<8) return false;
    var pz=S.pois.plaza; if(pz&&Math.hypot(x-pz[0],z-pz[1])<34) return false;
    for(var f=0;f<S.pois.fields.length;f++){ var ff=S.pois.fields[f];
      if(Math.hypot(x-ff[0],z-ff[1])<24) return false; }
    return true; }
  var nClust=S.biome===10? 44: S.id==='neolithic'?18:26;
  for(var c2=0;c2<nClust;c2++){
    var cx=(rng()*2-1)*560, cz2=(rng()*2-1)*560;
    var dc=Math.hypot(cx,cz2); if(dc<FLATR[S.id]*0.38) continue;
    var nn=3+rng()*7|0;
    for(var i=0;i<nn;i++){ var x=cx+(rng()*2-1)*46, z=cz2+(rng()*2-1)*46;
      if(Math.abs(x)>580||Math.abs(z)>580||!clearOf(x,z)) continue;
      var kind=rng()<0.55?0:(rng()<0.6?1:2);
      if(dc<FLATR[S.id]+60&&rng()<0.5) kind=2;
      var tsc=(0.85+rng()*0.7)*(S.biome===10?1.25:1);
      kinds[kind].push([x,z,tsc]); } }
  for(var r2=0;r2<(S.rugg*150+30|0);r2++){
    var rx=(rng()*2-1)*570, rz=(rng()*2-1)*570;
    if(Math.hypot(rx,rz)<FLATR[S.id]*0.5) continue;
    if(!clearOf(rx,rz)) continue;
    rocks.push([rx,rz,0.4+rng()*1.8]); }
  // пучки сухой травы, гуще в сухих биомах
  var tufts=[], tn=(S.biome===8||S.biome===9||S.biome===5)?900:420;
  for(var tf=0;tf<tn;tf++){
    var tx=(rng()*2-1)*575, tz=(rng()*2-1)*575;
    var th2=groundH(tx,tz);
    if(th2<WATER_Y+0.6) continue;
    var dtc=Math.hypot(tx,tz);
    if(dtc<FLATR[S.id]*0.45&&rng()<0.8) continue;
    if(!clearOf(tx,tz)&&rng()<0.7) continue;
    tufts.push([tx,tz,0.45+rng()*0.5]); }
  // тростник вдоль берегов: идём вдоль воды и подсаживаем пучки
  if(S.river||S.sea){ for(var t2=0;t2<2400;t2++){
    var x2=(rng()*2-1)*585, z2=(rng()*2-1)*585;
    var h2=groundH(x2,z2);
    if(h2<WATER_Y+1.5&&h2>WATER_Y-0.6) reeds.push([x2,z2,1.0+rng()*0.9]);
    if(reeds.length>620) break; } }
  function inst(geo,list,matOpts){
    if(!list.length) return null;
    var mat=new THREE.MeshLambertMaterial(Object.assign({vertexColors:true},matOpts||{}));
    var im=new THREE.InstancedMesh(geo,mat,list.length);
    var m4=new THREE.Matrix4(), q=new THREE.Quaternion(), e=new THREE.Euler(),
        v=new THREE.Vector3(), s=new THREE.Vector3(), cc=new THREE.Color();
    list.forEach(function(it,i){
      e.set(0,rng()*6.28,0); q.setFromEuler(e);
      v.set(it[0],groundH(it[0],it[1])-0.15,it[1]); s.set(it[2],it[2],it[2]);
      m4.compose(v,q,s); im.setMatrixAt(i,m4);
      var f=0.85+rng()*0.3; cc.setRGB(f,f,f); im.setColorAt(i,cc); });
    im.castShadow=true; im.receiveShadow=true;
    im.instanceMatrix.needsUpdate=true;
    if(im.instanceColor) im.instanceColor.needsUpdate=true;
    R3.scene.add(im); return im; }
  var P3=getPal();
  inst(treeGeo(0,P3),kinds[0]); inst(treeGeo(1,P3),kinds[1]); inst(treeGeo(2,P3),kinds[2]);
  var rockG=new THREE.IcosahedronGeometry(1,0);
  var rc=col(P3.rock), rcol=new Float32Array(rockG.attributes.position.count*3);
  for(var rv=0;rv<rockG.attributes.position.count;rv++){
    rcol[rv*3]=rc.r; rcol[rv*3+1]=rc.g; rcol[rv*3+2]=rc.b; }
  rockG.setAttribute('color',new THREE.BufferAttribute(rcol,3));
  var rockList=rocks.map(function(r){ return [r[0],r[1],r[2]]; });
  if(rockList.length){ var rm=new THREE.MeshLambertMaterial({vertexColors:true});
    var rim=new THREE.InstancedMesh(rockG,rm,rockList.length);
    var m42=new THREE.Matrix4(), q2=new THREE.Quaternion(), e2=new THREE.Euler(),
        v2=new THREE.Vector3(), s2=new THREE.Vector3();
    rockList.forEach(function(it,i){ e2.set(rng()*3,rng()*6.28,rng()*3);
      q2.setFromEuler(e2); v2.set(it[0],groundH(it[0],it[1])+it[2]*0.14,it[1]);
      s2.set(it[2],it[2]*0.72,it[2]); m42.compose(v2,q2,s2); rim.setMatrixAt(i,m42); });
    rim.castShadow=true; rim.receiveShadow=true; R3.scene.add(rim); }
  // тростник — конусы пучками
  if(reeds.length){ var reedBag=new Bag(), rcc=col(P3.reed);
    reedBag.put(PRIM.cone3,rcc,0,0.9,0,0,0,0.06,0.3,1.8,0.3);
    reedBag.put(PRIM.cone3,rcc.clone().multiplyScalar(0.9),0.3,0.8,0.15,0,0,-0.12,0.26,1.6,0.26);
    reedBag.put(PRIM.cone3,rcc.clone().multiplyScalar(1.1),-0.25,1.0,-0.1,0.1,0,0.1,0.3,2.0,0.3);
    var rgeo=new THREE.BufferGeometry();
    rgeo.setAttribute('position',new THREE.Float32BufferAttribute(reedBag.pos,3));
    rgeo.setAttribute('normal',new THREE.Float32BufferAttribute(reedBag.nor,3));
    rgeo.setAttribute('color',new THREE.Float32BufferAttribute(reedBag.col,3));
    rgeo.setIndex(reedBag.idx);
    var rmat=new THREE.MeshLambertMaterial({vertexColors:true});
    var rimm=new THREE.InstancedMesh(rgeo,rmat,reeds.length);
    var m43=new THREE.Matrix4(), q3=new THREE.Quaternion(), e3=new THREE.Euler(),
        v3=new THREE.Vector3(), s3=new THREE.Vector3();
    reeds.forEach(function(it,i){ e3.set(0,rng()*6.28,0); q3.setFromEuler(e3);
      v3.set(it[0],groundH(it[0],it[1]),it[1]); s3.set(it[2],it[2],it[2]);
      m43.compose(v3,q3,s3); rimm.setMatrixAt(i,m43); });
    R3.scene.add(rimm); }
  if(tufts.length){ var tuBag=new Bag(), tuc=col(P3.dry).lerp(col(P3.grass2),0.3);
    tuBag.put(PRIM.cone3,tuc,0,0.4,0,0,0,0.14,0.5,0.85,0.5);
    tuBag.put(PRIM.cone3,tuc.clone().multiplyScalar(0.88),0.3,0.35,0.1,0,0,-0.24,0.4,0.7,0.4);
    tuBag.put(PRIM.cone3,tuc.clone().multiplyScalar(1.08),-0.28,0.37,-0.12,0.2,0,0.2,0.44,0.75,0.44);
    var tuGeo=new THREE.BufferGeometry();
    tuGeo.setAttribute('position',new THREE.Float32BufferAttribute(tuBag.pos,3));
    tuGeo.setAttribute('normal',new THREE.Float32BufferAttribute(tuBag.nor,3));
    tuGeo.setAttribute('color',new THREE.Float32BufferAttribute(tuBag.col,3));
    tuGeo.setIndex(tuBag.idx);
    var tuIm=new THREE.InstancedMesh(tuGeo,new THREE.MeshLambertMaterial({vertexColors:true}),tufts.length);
    var m44=new THREE.Matrix4(), q4=new THREE.Quaternion(), e4=new THREE.Euler(),
        v4=new THREE.Vector3(), s4=new THREE.Vector3();
    tufts.forEach(function(it,i){ e4.set(0,rng()*6.28,0); q4.setFromEuler(e4);
      v4.set(it[0],groundH(it[0],it[1]),it[1]); s4.set(it[2],it[2],it[2]);
      m44.compose(v4,q4,s4); tuIm.setMatrixAt(i,m44); });
    R3.scene.add(tuIm); }
}

/* ══════════════════ 3. люди ══════════════════ */
var CLOTH={ wool:['#9c4f3a','#a8583f','#7c5a41','#8a7351','#5d6e7e','#996e35','#7a4a52'],
  hide:['#8a6a4e','#7a5c42','#93765a','#6d5540','#84644a'] };
function skinTone(rng){ var L=Math.abs(S.lat);
  var arr = L>32? ['#d9b490','#caa27c','#c2a077'] :
            L<16? ['#8a5c3c','#7a5034','#9a6b45'] : ['#b98f6b','#aa815d','#c09a74'];
  return pick(rng,arr); }
function clothColor(rng,npc){
  var pool = (S.garment==='wool'||S.garment==='weave')? CLOTH.wool: CLOTH.hide;
  if(npc.role==='priest') return '#d8cfba';
  if(npc.role==='chief') return S.id==='neolithic'? '#8a4a3a':'#7c3f4a';
  if(npc.role==='warrior') return '#5d564a';
  return pick(rng,pool); }

function npcGeos(){
  // тело: туловище-капсула + руки + ноги (цвет-маска: белый, ноги темнее)
  var bag=new Bag(), white=new THREE.Color(1,1,1), dark=new THREE.Color(0.42,0.38,0.34);
  var caps=new THREE.CapsuleGeometry(0.27,0.52,3,8);
  bag2Add(bag,caps,white,0,1.08,0,0);
  bag.put(PRIM.cyl,white,-0.36,1.06,0,0,0,0.18,0.14,0.62,0.14);
  bag.put(PRIM.cyl,white, 0.36,1.06,0,0,0,-0.18,0.14,0.62,0.14);
  bag.put(PRIM.cyl,dark,-0.14,0.36,0,0,0,0,0.15,0.72,0.15);
  bag.put(PRIM.cyl,dark, 0.14,0.36,0,0,0,0,0.15,0.72,0.15);
  var body=new THREE.BufferGeometry();
  body.setAttribute('position',new THREE.Float32BufferAttribute(bag.pos,3));
  body.setAttribute('normal',new THREE.Float32BufferAttribute(bag.nor,3));
  body.setAttribute('color',new THREE.Float32BufferAttribute(bag.col,3));
  body.setIndex(bag.idx);
  var hb=new Bag(), hw=new THREE.Color(1,1,1), hd=new THREE.Color(0.32,0.28,0.25);
  hb.put(PRIM.sph,hw,0,0,0,0,0,0,0.42,0.46,0.42);
  hb.put(PRIM.sph,hd,0,0.1,-0.04,0,0,0,0.44,0.4,0.44);   // волосы
  hb.put(PRIM.cyl,hw,0,-0.28,0,0,0,0,0.12,0.2,0.12);
  var head=new THREE.BufferGeometry();
  head.setAttribute('position',new THREE.Float32BufferAttribute(hb.pos,3));
  head.setAttribute('normal',new THREE.Float32BufferAttribute(hb.nor,3));
  head.setAttribute('color',new THREE.Float32BufferAttribute(hb.col,3));
  head.setIndex(hb.idx);
  return {body:body, head:head};
}

function buildNPCs(){
  var rng=mulberry(S.seed*17+9);
  var geos=npcGeos();
  var n=S.npcs.length;
  var bm=new THREE.MeshLambertMaterial({vertexColors:true});
  var hm=new THREE.MeshLambertMaterial({vertexColors:true});
  G.npcBody=new THREE.InstancedMesh(geos.body,bm,n);
  G.npcHead=new THREE.InstancedMesh(geos.head,hm,n);
  G.npcBody.castShadow=true; G.npcHead.castShadow=true;
  var cc=new THREE.Color();
  G.units=S.npcs.map(function(npc,i){
    cc.set(clothColor(rng,npc)); G.npcBody.setColorAt(i,cc);
    cc.set(skinTone(rng)); G.npcHead.setColorAt(i,cc);
    var route=npc.route.map(function(p){ return {x:p[0],z:p[1]}; });
    return { d:npc, i:i, x:npc.home[0], z:npc.home[1], yaw:rng()*6.28,
      route:route, leg:0, wait:rng()*10, spd:1.05+rng()*0.45,
      mode:'idle', vis:true, ph:rng()*6.28, scl:0.92+rng()*0.16 };
  });
  R3.scene.add(G.npcBody); R3.scene.add(G.npcHead);
  // золотые значки над замечательными
  var stars=G.units.filter(function(u){ return u.d.real; });
  if(stars.length){
    var sg=new THREE.OctahedronGeometry(0.16,0);
    var sm=new THREE.MeshBasicMaterial({color:'#ffd570'});
    G.badges=new THREE.InstancedMesh(sg,sm,stars.length);
    G.badgeUnits=stars; R3.scene.add(G.badges); }
  G.labelPool=[];
  for(var li=0;li<9;li++){
    var cvs=document.createElement('canvas'); cvs.width=256; cvs.height=72;
    var tex=new THREE.CanvasTexture(cvs); tex.colorSpace=THREE.SRGBColorSpace;
    var sp=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,
      depthTest:false}));
    sp.scale.set(2.3,0.65,1); sp.visible=false; sp.renderOrder=30;
    R3.scene.add(sp);
    G.labelPool.push({sp:sp,cv:cvs,tex:tex,owner:-1}); }
}
function drawLabel(L,u){
  var g=L.cv.getContext('2d'); g.clearRect(0,0,256,72);
  g.fillStyle='rgba(8,10,16,0.72)'; g.beginPath();
  g.roundRect(4,4,248,64,12); g.fill();
  g.textAlign='center'; g.fillStyle=u.d.real?'#ffd98a':'#efe6d2';
  g.font='24px Georgia'; var nm=u.d.name;
  if(nm.length>17) nm=nm.slice(0,16)+'…';
  g.fillText((u.d.real?'★ ':'')+nm,128,32);
  g.fillStyle='#9aa3b5'; g.font='19px Georgia';
  g.fillText(u.d.role_ru+', '+u.d.age,128,57);
  L.tex.needsUpdate=true;
}

/* расписание жителя: 0 сон, 1 день */
function npcAwake(t){ return t>0.245&&t<0.8; }
function updateNPCs(dt){
  var t=G.t, m4=new THREE.Matrix4(), q=new THREE.Quaternion(), e=new THREE.Euler(),
      v=new THREE.Vector3(), s=new THREE.Vector3();
  var awake=npcAwake(t);
  G.units.forEach(function(u){
    var wake=awake||(u.d.night==='fire');
    if(!wake){ u.vis=false; }
    else if(!awake&&u.d.night==='fire'){       // ночь у костра
      u.vis=true; u.sit=true;
      u.tx=u.d.nightpos[0]; u.tz=u.d.nightpos[1];
      stepToward(u,dt*0.6);
    } else { u.vis=true; u.sit=false;
      // дневной цикл: маршрут с паузами
      if(u.wait>0){ u.wait-=dt*G.spdReal; }
      else {
        var tgt=u.route[u.leg%u.route.length];
        u.tx=tgt.x; u.tz=tgt.z;
        if(stepToward(u,dt)){ u.leg++; u.wait=6+((u.ph*37)%22); } }
    }
    var sc=u.vis? u.scl:0.0001;
    var gy=groundH(u.x,u.z);
    var bob=u.moving? Math.sin(G.el*7.2+u.ph)*0.05: Math.sin(G.el*1.3+u.ph)*0.012;
    var sway=u.moving? Math.sin(G.el*3.6+u.ph)*0.045: Math.sin(G.el*0.9+u.ph)*0.014;
    e.set(0,-u.yaw+Math.PI/2,sway); q.setFromEuler(e);
    var yy=gy+bob+(u.sit?-0.42:0);
    v.set(u.x,yy,u.z); s.set(sc,u.sit?sc*0.72:sc,sc);
    m4.compose(v,q,s); G.npcBody.setMatrixAt(u.i,m4);
    var nod=u.moving? Math.sin(G.el*7.2+u.ph+0.6)*0.04:0;
    e.set(nod,-u.yaw+Math.PI/2,0); q.setFromEuler(e);
    v.set(u.x,yy+(u.sit?1.32:1.78)*sc/u.scl*u.scl,u.z); s.set(sc,sc,sc);
    m4.compose(v,q,s); G.npcHead.setMatrixAt(u.i,m4);
  });
  G.npcBody.instanceMatrix.needsUpdate=true;
  G.npcHead.instanceMatrix.needsUpdate=true;
  if(G.npcBody.instanceColor&&!G.colorsFlushed){
    G.npcBody.instanceColor.needsUpdate=true;
    G.npcHead.instanceColor.needsUpdate=true; G.colorsFlushed=true; }
  if(G.badges){ var bi=0;
    G.badgeUnits.forEach(function(u){
      var bs=u.vis?1:0.0001;
      e.set(0,G.el*1.8,0); q.setFromEuler(e);
      v.set(u.x,groundH(u.x,u.z)+2.35+Math.sin(G.el*2+u.ph)*0.08,u.z);
      s.set(bs,bs,bs); m4.compose(v,q,s); G.badges.setMatrixAt(bi++,m4); });
    G.badges.instanceMatrix.needsUpdate=true; }
}
function stepToward(u,dt){
  var dx=u.tx-u.x, dz=u.tz-u.z, d=Math.hypot(dx,dz);
  if(d<1.6){ u.moving=false; return true; }
  var sp=u.spd*dt*G.spdReal*(G.spdReal>4?4:1);
  var want=Math.atan2(dz,dx);
  var dy=want-u.yaw; while(dy>Math.PI)dy-=6.283; while(dy<-Math.PI)dy+=6.283;
  u.yaw+=clamp(dy,-3*dt,3*dt);
  u.x+=Math.cos(u.yaw)*sp; u.z+=Math.sin(u.yaw)*sp;
  var p=pushOut(u.x,u.z,0.5); u.x=p[0]; u.z=p[1];
  u.moving=true; return false;
}

/* ══════════════════ 4. небо, свет, атмосфера ══════════════════ */
var SKY_KEYS=[   // t, верх неба, горизонт, солнце-int, hemi-int, туман-цвет
  [0.00,'#070b18','#0b1020',0.00,0.145,'#0a0e18'],
  [0.20,'#0a1022','#141428',0.00,0.15,'#0d1020'],
  [0.245,'#20304e','#8a4f3a',0.12,0.20,'#4a3a38'],
  [0.275,'#4a6a92','#d8875a',0.55,0.42,'#a8765c'],
  [0.34,'#7ba3c8','#d8b98a',1.05,0.72,'#c2b49a'],
  [0.50,'#88b4d8','#cfd8d8',1.35,0.95,'#c8d0d4'],
  [0.66,'#82a8cc','#d8c49a',1.15,0.82,'#ccc0a4'],
  [0.73,'#5a6a9a','#e08a4a',0.8,0.52,'#b08464'],
  [0.765,'#3c4c74','#c86a40',0.42,0.36,'#8a5c4a'],
  [0.80,'#182040','#3a2a44',0.06,0.17,'#1c1c30'],
  [0.84,'#0a1024','#12142a',0.00,0.11,'#0d1020'],
  [1.00,'#070b18','#0b1020',0.00,0.10,'#0a0e18']];
function skyAt(t){
  var a=SKY_KEYS[0], b=SKY_KEYS[SKY_KEYS.length-1];
  for(var i=0;i<SKY_KEYS.length-1;i++)
    if(t>=SKY_KEYS[i][0]&&t<=SKY_KEYS[i+1][0]){ a=SKY_KEYS[i]; b=SKY_KEYS[i+1]; break; }
  var f=(t-a[0])/Math.max(1e-5,b[0]-a[0]); f=sstep(f);
  return { top:col(a[1]).lerp(col(b[1]),f), hor:col(a[2]).lerp(col(b[2]),f),
    sun:lerp(a[3],b[3],f), hemi:lerp(a[4],b[4],f), fog:col(a[5]).lerp(col(b[5]),f) };
}
function buildSky(){
  var geo=new THREE.SphereGeometry(1500,24,14);
  var mat=new THREE.ShaderMaterial({ side:THREE.BackSide, depthWrite:false, fog:false,
    uniforms:{ top:{value:new THREE.Color('#88b4d8')}, hor:{value:new THREE.Color('#cfd8d8')},
      sunDir:{value:new THREE.Vector3(0,1,0)}, sunCol:{value:new THREE.Color('#ffe0b0')},
      glow:{value:0.5} },
    vertexShader:'varying vec3 vP; void main(){ vP=normalize(position);'+
      ' gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
    fragmentShader:'varying vec3 vP; uniform vec3 top,hor,sunCol; uniform vec3 sunDir;'+
      ' uniform float glow;'+
      ' void main(){ float h=max(vP.y,0.0);'+
      ' vec3 c=mix(hor,top,pow(h,0.5));'+
      ' float d=max(dot(vP,sunDir),0.0);'+
      ' c+=sunCol*pow(d,240.0)*1.4*glow; c+=sunCol*pow(d,7.0)*0.24*glow;'+
      ' gl_FragColor=vec4(c,1.0);}'});
  R3.sky=new THREE.Mesh(geo,mat); R3.scene.add(R3.sky);
  // звёзды
  var starN=750, sp=new Float32Array(starN*3), rng=mulberry(99);
  for(var i=0;i<starN;i++){ var a=rng()*6.283, b=Math.acos(rng()*0.95);
    sp[i*3]=Math.sin(b)*Math.cos(a)*1400; sp[i*3+1]=Math.cos(b)*1400;
    sp[i*3+2]=Math.sin(b)*Math.sin(a)*1400; }
  var sg=new THREE.BufferGeometry();
  sg.setAttribute('position',new THREE.BufferAttribute(sp,3));
  R3.stars=new THREE.Points(sg,new THREE.PointsMaterial({color:'#cdd8f0',size:2.6,
    sizeAttenuation:false,transparent:true,opacity:0,depthWrite:false,fog:false}));
  R3.scene.add(R3.stars);
  R3.sun=new THREE.DirectionalLight('#ffe8c8',1.2);
  R3.sun.castShadow=true;
  R3.sun.shadow.mapSize.set(2048,2048);
  var sc=R3.sun.shadow.camera;
  sc.left=-160; sc.right=160; sc.top=160; sc.bottom=-160; sc.near=20; sc.far=640;
  R3.sun.shadow.bias=-0.0006; R3.sun.shadow.normalBias=0.5;
  R3.scene.add(R3.sun); R3.scene.add(R3.sun.target);
  R3.moon=new THREE.DirectionalLight('#8aa2cc',0.0); R3.scene.add(R3.moon);
  R3.hemi=new THREE.HemisphereLight('#bcd0e8','#6a6152',0.7); R3.scene.add(R3.hemi);
  R3.scene.fog=new THREE.Fog('#c8d0d4',60,760);
  // диск луны
  var mcv=document.createElement('canvas'); mcv.width=mcv.height=64;
  var mg=mcv.getContext('2d');
  var grd=mg.createRadialGradient(32,32,6,32,32,30);
  grd.addColorStop(0,'rgba(230,238,252,1)'); grd.addColorStop(0.55,'rgba(210,222,244,0.9)');
  grd.addColorStop(1,'rgba(200,210,240,0)');
  mg.fillStyle=grd; mg.fillRect(0,0,64,64);
  var mt=new THREE.CanvasTexture(mcv);
  R3.moonSp=new THREE.Sprite(new THREE.SpriteMaterial({map:mt,transparent:true,
    fog:false,depthWrite:false}));
  R3.moonSp.scale.set(90,90,1); R3.scene.add(R3.moonSp);
}
function sunPos(t){
  var lat=clamp(Math.abs(S.lat),0,72);
  var elevMax=clamp((90-lat+14)*0.72,24,54)*Math.PI/180;
  var p=(t-0.25)/0.5;                  // 0 рассвет, 1 закат
  var az=lerp(1.85,-1.85,p);
  var el=Math.sin(clamp(p,0,1)*Math.PI)*elevMax;
  if(t<0.25||t>0.75) el=-0.3;
  var sy=Math.sin(el), horiz=Math.cos(el);
  // в северных широтах солнце ходит южной стороной (+z), в южных — северной
  return new THREE.Vector3(Math.sin(az)*horiz, sy, Math.cos(az)*horiz*(S.lat<0?-1:1));
}
function updateSky(){
  var t=G.t, k=skyAt(t);
  var sd=sunPos(t), pl=G.player;
  R3.sky.material.uniforms.top.value.copy(k.top);
  R3.sky.material.uniforms.hor.value.copy(k.hor);
  R3.sky.material.uniforms.sunDir.value.copy(sd);
  R3.sky.material.uniforms.glow.value=k.sun>0? 1: (t>0.2&&t<0.3)||(t>0.7&&t<0.82)? 0.5:0.12;
  var warm=clamp(1-Math.abs(sd.y)*2.6,0,1);
  R3.sky.material.uniforms.sunCol.value.setRGB(1,0.9-warm*0.32,0.72-warm*0.36);
  R3.sky.position.set(pl.x,0,pl.z);
  R3.sun.intensity=k.sun*2.1;
  R3.sun.color.setRGB(1,0.94-warm*0.3,0.82-warm*0.42);
  var sp2=sd.clone().multiplyScalar(300);
  R3.sun.position.set(pl.x+sp2.x,sp2.y+40,pl.z+sp2.z);
  R3.sun.target.position.set(pl.x,0,pl.z);
  var night=clamp(1-k.sun*3-k.hemi,0,1);
  R3.moon.intensity=night*0.4;
  var md=sunPos((t+0.5)%1);
  R3.moon.position.set(pl.x+md.x*280,Math.abs(md.y)*280+60,pl.z+md.z*280);
  R3.moonSp.position.set(pl.x+md.x*900,Math.abs(md.y)*900+40,pl.z+md.z*900);
  R3.moonSp.material.opacity=night*0.95;
  R3.hemi.intensity=k.hemi*1.5+0.08;
  R3.hemi.color.copy(k.top).lerp(new THREE.Color('#ffffff'),0.4);
  R3.stars.material.opacity=night*0.9;
  R3.stars.position.set(pl.x,0,pl.z);
  var fogFar={capital:820, bronze:560, neolithic:760}[S.id]||760;
  var mist=1-0.35*clamp(Math.sin((t-0.2)*10),0,1);   // рассветная дымка
  R3.scene.fog.color.copy(k.fog);
  R3.scene.fog.near=30; R3.scene.fog.far=fogFar*mist*(night>0.5?0.7:1);
  if(R3.water){ R3.water.material.opacity=0.9+Math.sin(G.el*0.7)*0.03; }
}

/* огни и дым */
function buildFires(){
  G.lights=[];
  for(var i=0;i<8;i++){ var pl=new THREE.PointLight('#ff9a40',0,26,1.8);
    R3.scene.add(pl); G.lights.push(pl); }
  var n=G.fireSrc.length;
  var pos=new Float32Array(n*3), sz=new Float32Array(n), ph=new Float32Array(n);
  G.fireSrc.forEach(function(f,i){ pos[i*3]=f[0]; pos[i*3+1]=f[1]+0.3; pos[i*3+2]=f[2];
    sz[i]=f[3]; ph[i]=i*1.7; });
  var g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.BufferAttribute(pos,3));
  g.setAttribute('sz',new THREE.BufferAttribute(sz,1));
  g.setAttribute('ph',new THREE.BufferAttribute(ph,1));
  var mat=new THREE.ShaderMaterial({ transparent:true, depthWrite:false,
    blending:THREE.AdditiveBlending,
    uniforms:{uT:{value:0},uN:{value:1}},
    vertexShader:'attribute float sz; attribute float ph; uniform float uT; uniform float uN;'+
     'varying float vF; void main(){'+
     ' vec4 mv=modelViewMatrix*vec4(position,1.0);'+
     ' float fl=0.8+0.3*sin(uT*11.0+ph)+0.12*sin(uT*23.0+ph*2.0); vF=fl;'+
     ' gl_PointSize=sz*fl*mix(0.34,1.0,uN)*(330.0/max(1.0,-mv.z));'+
     ' gl_Position=projectionMatrix*mv; }',
    fragmentShader:'varying float vF; void main(){'+
     ' vec2 u=gl_PointCoord*2.0-1.0; float d=length(u);'+
     ' float a=smoothstep(1.0,0.15,d);'+
     ' vec3 c=mix(vec3(1.0,0.85,0.45),vec3(0.9,0.3,0.05),d);'+
     ' gl_FragColor=vec4(c*1.4,a*0.85*vF);}'});
  G.flames=new THREE.Points(g,mat); G.flames.renderOrder=20;
  R3.scene.add(G.flames);
  // дым: частицы над источниками
  var sn=Math.min(200,G.smokeSrc.length*10+40);
  var spx=new Float32Array(sn*3), sph=new Float32Array(sn), ssrc=[];
  for(var s2=0;s2<sn;s2++){ var src=G.smokeSrc[s2%Math.max(1,G.smokeSrc.length)]||[0,-99,0,0];
    ssrc.push(src); sph[s2]=Math.random()*8; }
  G.smokeSrcOf=ssrc; G.smokePh=sph; G.smokeN=sn;
  var sg2=new THREE.BufferGeometry();
  sg2.setAttribute('position',new THREE.BufferAttribute(spx,3));
  var scv=document.createElement('canvas'); scv.width=scv.height=48;
  var sgc=scv.getContext('2d');
  var sgr=sgc.createRadialGradient(24,24,3,24,24,22);
  sgr.addColorStop(0,'rgba(168,162,155,0.4)'); sgr.addColorStop(1,'rgba(168,162,155,0)');
  sgc.fillStyle=sgr; sgc.fillRect(0,0,48,48);
  var stx=new THREE.CanvasTexture(scv);
  G.smoke=new THREE.Points(sg2,new THREE.PointsMaterial({map:stx,size:2.1,
    transparent:true,opacity:0.3,depthWrite:false}));
  R3.scene.add(G.smoke);
}
function updateFires(dt){
  var t=G.t, night=(t<0.25||t>0.75)?1:0;
  G.flames.material.uniforms.uT.value=G.el;
  G.flames.material.uniforms.uN.value=night;
  // 8 ближних огней получают свет
  var pl=G.player, srt=G.fireSrc.map(function(f,i){
    return [ ((f[0]-pl.x)*(f[0]-pl.x)+(f[2]-pl.z)*(f[2]-pl.z))/(f[3]*f[3]), f]; });
  srt.sort(function(a,b){ return a[0]-b[0]; });
  for(var i=0;i<8;i++){ var L=G.lights[i], f=srt[i]&&srt[i][1];
    if(!f){ L.intensity=0; continue; }
    L.position.set(f[0],f[1]+0.6,f[2]);
    var base=night? 3.4: 0.55;
    L.intensity=(base+Math.sin(G.el*9+i*2.4)*0.6)*f[3]*0.75;
    L.distance=24+f[3]*11; }
  // дым
  var p=G.smoke.geometry.attributes.position;
  for(var s2=0;s2<G.smokeN;s2++){
    var src=G.smokeSrcOf[s2];
    var ph=(G.el*0.42+G.smokePh[s2])%8;
    var up=ph*0.8, drift=ph*ph*0.14;
    p.array[s2*3]=src[0]+Math.sin(G.el*0.4+s2)*0.4+drift*0.7;
    p.array[s2*3+1]=src[1]+up;
    p.array[s2*3+2]=src[2]+Math.cos(G.el*0.3+s2*1.3)*0.3+drift*0.4; }
  p.needsUpdate=true;
  G.smoke.material.opacity=0.15-night*0.07;
}
/* птицы */
function buildBirds(){
  G.birds=[];
  var geo=new THREE.BufferGeometry();
  var v=new Float32Array([ -0.9,0,0, 0,0.12,0.25, 0,0,0,  0.9,0,0, 0,0.12,0.25, 0,0,0]);
  geo.setAttribute('position',new THREE.BufferAttribute(v,3));
  geo.computeVertexNormals();
  var mat=new THREE.MeshBasicMaterial({color:'#20242c',side:THREE.DoubleSide});
  for(var i=0;i<6;i++){ var m=new THREE.Mesh(geo,mat);
    m.userData={cx:(Math.random()*2-1)*260, cz:(Math.random()*2-1)*260,
      r:60+Math.random()*90, h:55+Math.random()*40, ph:Math.random()*6.28,
      sp:0.25+Math.random()*0.2};
    R3.scene.add(m); G.birds.push(m); }
}
function updateBirds(){
  var day=npcAwake(G.t);
  G.birds.forEach(function(b,i){
    var u=b.userData;
    b.visible=day;
    if(!day) return;
    var a=G.el*u.sp+u.ph;
    b.position.set(u.cx+Math.cos(a)*u.r, u.h+Math.sin(a*2.3)*4, u.cz+Math.sin(a)*u.r);
    b.rotation.y=-a-1.57;
    b.rotation.z=Math.sin(G.el*9+i)*0.5;
  });
}

/* ══════════════════ 5. управление ══════════════════ */
var KEYS={};
function bindInput(){
  document.addEventListener('keydown',function(e){
    if(G&&G.dialog){ if(e.code==='Escape') closeDialog(); return; }
    KEYS[e.code]=true;
    if(!G||!G.on) return;
    if(e.code==='KeyT'){ G.spd = G.spd>=120? 1: G.spd>=24? 120: 24; flashHint('время ×'+G.spd); }
    if(e.code==='KeyF'){ G.third=!G.third; flashHint(G.third?'вид со спины':'вид от первого лица'); }
    if(e.code==='KeyM'){ G.mapOn=!G.mapOn; EL.map.style.display=G.mapOn?'block':'none'; }
    if(e.code==='KeyE'){ tryTalk(); }
  });
  document.addEventListener('keyup',function(e){ KEYS[e.code]=false; });
  EL.c3d.addEventListener('click',function(){
    if(!G||!G.on||G.dialog||DEBUG) return;
    if(document.pointerLockElement!==EL.c3d){
      var p=EL.c3d.requestPointerLock();
      if(p&&p.catch) p.catch(function(){}); }
  });
  document.addEventListener('pointerlockchange',function(){
    var locked=document.pointerLockElement===EL.c3d;
    if(G&&G.on&&!G.dialog&&!DEBUG)
      EL.pause.style.display=locked?'none':'flex';
  });
  EL.pause.addEventListener('click',function(){
    if(!G||!G.on) return;
    var p=EL.c3d.requestPointerLock(); if(p&&p.catch)p.catch(function(){});
    if(DEBUG) EL.pause.style.display='none';
  });
  document.addEventListener('mousemove',function(e){
    if(!G||!G.on||G.dialog) return;
    if(document.pointerLockElement===EL.c3d){
      G.yaw-=e.movementX*0.0023; G.pitch-=e.movementY*0.0021;
      G.pitch=clamp(G.pitch,-1.45,1.45); }
    else if(DEBUG&&G.drag){ G.yaw-=e.movementX*0.004; G.pitch-=e.movementY*0.004;
      G.pitch=clamp(G.pitch,-1.45,1.45); }
  });
  EL.c3d.addEventListener('mousedown',function(){ if(G)G.drag=true; });
  document.addEventListener('mouseup',function(){ if(G)G.drag=false; });
  EL.menuBtn.onclick=function(){ location.href=location.pathname; };
  EL.dclose.onclick=closeDialog;
  window.addEventListener('resize',function(){ if(!R3) return;
    R3.camera.aspect=innerWidth/innerHeight; R3.camera.updateProjectionMatrix();
    R3.renderer.setSize(innerWidth,innerHeight); });
}
var hintT=0;
function flashHint(s){ EL.talk.innerHTML=s; EL.talk.style.display='block'; hintT=1.6; }

function updatePlayer(dt){
  var p=G.player;
  var run=KEYS['ShiftLeft']||KEYS['ShiftRight'];
  var sp=(run?8.4:4.3)*dt;
  var fx=Math.sin(G.yaw), fz=Math.cos(G.yaw);
  var mx=0,mz=0;
  if(KEYS['KeyW']){ mx-=fx; mz-=fz; }
  if(KEYS['KeyS']){ mx+=fx; mz+=fz; }
  if(KEYS['KeyA']){ mx-=fz; mz+=fx; }
  if(KEYS['KeyD']){ mx+=fz; mz-=fx; }
  var ml=Math.hypot(mx,mz);
  G.moving=ml>0;
  if(ml>0){ mx/=ml; mz/=ml;
    var g=groundH(p.x,p.z);
    var wade=g<WATER_Y-0.2? 0.45:1;
    p.x+=mx*sp*wade; p.z+=mz*sp*wade; }
  var pr=pushOut(p.x,p.z,0.55); p.x=pr[0]; p.z=pr[1];
  p.x=clamp(p.x,-585,585); p.z=clamp(p.z,-585,585);
  var gh=groundH(p.x,p.z);
  if(gh<WATER_Y-2.6){ // глубина: не пускаем в открытое море
    var bx=p.x-mx*sp*2, bz=p.z-mz*sp*2;
    p.x=bx; p.z=bz; gh=groundH(p.x,p.z); }
  if(KEYS['Space']&&p.grounded){ p.vy=5.4; p.grounded=false; }
  p.vy-=14*dt; p.y+=p.vy*dt;
  var floor=Math.max(gh,WATER_Y-1.1);
  if(p.y<=floor){ p.y=floor; p.vy=0; p.grounded=true; }
  var eye=p.y+1.62;
  if(G.moving&&p.grounded) eye+=Math.sin(G.el*(run?11:7.6))*0.05;
  var cam=R3.camera;
  if(!G.third){
    cam.position.set(p.x,eye,p.z);
    cam.rotation.set(0,0,0,'YXZ');
    cam.rotation.order='YXZ';
    cam.rotation.y=G.yaw; cam.rotation.x=G.pitch;
    if(G.avatar) G.avatar.visible=false;
  } else {
    var bx2=p.x+Math.sin(G.yaw)*5.4, bz2=p.z+Math.cos(G.yaw)*5.4;
    var by=eye+1.7-G.pitch*2.4;
    by=Math.max(by, groundH(bx2,bz2)+0.5);
    cam.position.set(bx2,by,bz2);
    cam.lookAt(p.x,eye+0.2,p.z);
    if(G.avatar){ G.avatar.visible=true;
      G.avatar.position.set(p.x,p.y,p.z);
      G.avatar.rotation.y=-G.yaw; }
  }
}

/* ══════════════════ 6. HUD, ярлыки, карта ══════════════════ */
function nearestNPC(maxD){
  var p=G.player, best=null, bd=maxD*maxD;
  G.units.forEach(function(u){ if(!u.vis) return;
    var d=(u.x-p.x)*(u.x-p.x)+(u.z-p.z)*(u.z-p.z);
    if(d<bd){ bd=d; best=u; } });
  return best;
}
function updateHUD(){
  var t=G.t;
  EL.hudLine.innerHTML='<b>'+S.polity+'</b> · '+S.form_ru+' · '+S.year_ru;
  var near=0, p=G.player;
  G.units.forEach(function(u){ if(u.vis&&(u.x-p.x)*(u.x-p.x)+(u.z-p.z)*(u.z-p.z)<2100) near++; });
  EL.hudTime.innerHTML=dayWord(t)+' · '+fmtClock(t)+(G.spd>1?' · <b>×'+G.spd+'</b>':'')+
    ' &nbsp;·&nbsp; рядом жителей: '+near;
  var u2=nearestNPC(3.1);
  if(u2&&!G.dialog){ EL.talk.style.display='block';
    EL.talk.innerHTML='<b>[E]</b> — заговорить: '+u2.d.name+', '+u2.d.role_ru;
  } else if(hintT<=0) EL.talk.style.display='none';
}
function updateLabels(){
  var p=G.player, cams=R3.camera;
  if(G.templeLabel){ var tld=Math.hypot(G.templeLabel.position.x-p.x,
    G.templeLabel.position.z-p.z);
    G.templeLabel.material.opacity=clamp((120-tld)/70,0,0.92)*clamp((tld-18)/14,0,1);
    G.templeLabel.visible=!G.dialog; }
  if(G.dialog){ G.labelPool.forEach(function(L){ L.sp.visible=false; }); return; }
  var cand=[];
  G.units.forEach(function(u){ if(!u.vis) return;
    var d=Math.hypot(u.x-p.x,u.z-p.z);
    if(d<7.2) cand.push([d,u]); });
  cand.sort(function(a,b){ return a[0]-b[0]; });
  cand=cand.slice(0,G.labelPool.length);
  var used={};
  cand.forEach(function(cu,i){ var L=G.labelPool[i], u=cu[1];
    if(L.owner!==u.i){ drawLabel(L,u); L.owner=u.i; }
    L.sp.visible=true;
    L.sp.position.set(u.x,groundH(u.x,u.z)+2.6,u.z);
    L.sp.material.opacity=clamp(1.3-cu[0]/6,0,1)*clamp((cu[0]-2.1)/0.8,0,1);
    used[i]=1; });
  for(var i=cand.length;i<G.labelPool.length;i++) G.labelPool[i].sp.visible=false;
}
function buildMinimap(){
  var cv=document.createElement('canvas'); cv.width=cv.height=230;
  var g=cv.getContext('2d'), P=getPal();
  var sc=230/TSIZE;
  g.fillStyle=P.grass; g.fillRect(0,0,230,230);
  for(var y=0;y<58;y++) for(var x=0;x<58;x++){
    var wx=(x/57-0.5)*TSIZE, wz=(y/57-0.5)*TSIZE;
    var h=groundH(wx,wz);
    if(h<WATER_Y){ g.fillStyle=P.water; g.fillRect(x*4,y*4,4.2,4.2); }
    else if(h>BASE_H+9){ g.fillStyle=P.rock; g.fillRect(x*4,y*4,4.2,4.2); } }
  g.strokeStyle=P.path; g.lineWidth=2;
  S.streets.forEach(function(s){ g.beginPath();
    g.moveTo((s[0]/TSIZE+0.5)*230,(s[1]/TSIZE+0.5)*230);
    g.lineTo((s[2]/TSIZE+0.5)*230,(s[3]/TSIZE+0.5)*230); g.stroke(); });
  S.buildings.forEach(function(b){
    var x=(b[1]/TSIZE+0.5)*230, y2=(b[2]/TSIZE+0.5)*230;
    if(b[0]==='temple'){ g.fillStyle='#e8d8a0'; g.fillRect(x-3,y2-3,6,6); }
    else if(b[0]==='wall'||b[0]==='tower'){ g.fillStyle='#77706a';
      g.fillRect(x-1.4,y2-1.4,2.8,2.8); }
    else if(b[0]==='field'){ g.fillStyle='rgba(140,120,60,0.5)'; g.fillRect(x-3,y2-2,6,4); }
    else if(b[0]!=='fire'&&b[0]!=='torch'){ g.fillStyle='#4a4038'; g.fillRect(x-1.2,y2-1.2,2.4,2.4); } });
  G.mapBase=cv;
}
function updateMinimap(){
  if(!G.mapOn) return;
  var g=EL.map.getContext('2d');
  g.clearRect(0,0,230,230); g.drawImage(G.mapBase,0,0);
  G.units.forEach(function(u){ if(!u.vis) return;
    g.fillStyle=u.d.real?'#ffd570':'#d8d0c0';
    g.fillRect((u.x/TSIZE+0.5)*230-1,(u.z/TSIZE+0.5)*230-1,2.4,2.4); });
  var p=G.player;
  g.save(); g.translate((p.x/TSIZE+0.5)*230,(p.z/TSIZE+0.5)*230);
  g.rotate(-G.yaw);
  g.fillStyle='#ff6a4a'; g.beginPath();
  g.moveTo(0,-6); g.lineTo(4,5); g.lineTo(-4,5); g.closePath(); g.fill(); g.restore();
}

/* ══════════════════ 7. диалог ══════════════════ */
function tryTalk(){ var u=nearestNPC(3.1); if(u) openDialog(u); }
function openDialog(u){
  G.dialog=u; G.chat=[];
  if(document.pointerLockElement) document.exitPointerLock();
  EL.pause.style.display='none';
  EL.dlg.style.display='flex';
  fillCard(u.d);
  EL.dmsgs.innerHTML='';
  addMsg(u.d.name, greet(u), false);
  EL.dtopics.innerHTML='';
  [['Кто ты?','who'],['Что нового в городе?','news'],
   ['Во что ты веришь?','faith'],['Расскажи о своём народе','folk']]
  .forEach(function(tp){ var b=document.createElement('button');
    b.textContent=tp[0];
    b.onclick=function(){ addMsg('Вы',tp[0],true);
      var u2=G.dialog; u2.clicks=(u2.clicks||0)+1;
      setTimeout(function(){ addMsg(u2.d.name, answer(u2,tp[1]), false); },140); };
    EL.dtopics.appendChild(b); });
}
function closeDialog(){
  if(!G.dialog) return;
  G.dialog=null; EL.dlg.style.display='none';
  if(!DEBUG){ var p=EL.c3d.requestPointerLock(); if(p&&p.catch)p.catch(function(){}); }
}
function fillCard(d){
  var html='<h3>'+(d.real?'★ ':'')+d.name+'</h3>'+
   '<div class="r">'+d.role_ru+', '+d.age+
   (d.sex? ' лет':' лет')+'</div>'+
   '<div class="kv">народ: <b>'+S.polity+'</b><br>эпоха: <b>'+S.era+'</b>'+
   (d.born!==null&&d.born!==undefined? '<br>род. '+fmtYear(d.born):'')+
   (d.real? '<br><span style="color:#c9a35a">записан в книге людей мира</span>':'')+'</div>';
  if(d.deeds&&d.deeds.length){ html+='<div class="sec">деяния</div>';
    d.deeds.forEach(function(dd){ html+='<div class="deed"><i>'+fmtYear(dd.y)+
      ':</i> '+dd.t+'</div>'; }); }
  if(d.crafts&&d.crafts.length){ html+='<div class="sec">чему выучились руки</div>';
    d.crafts.forEach(function(c){ html+='<span class="chip">'+c[0]+' '+
      lvlWord(c[1])+'</span>'; }); }
  if(d.scars&&Object.keys(d.scars).length){ html+='<div class="sec">пережитое</div>';
    Object.keys(d.scars).forEach(function(k){ html+='<span class="chip scar">'+k+
      ' '+lvlWord(d.scars[k])+'</span>'; }); }
  if(d.memories&&d.memories.length){ html+='<div class="sec">помнит</div>';
    d.memories.forEach(function(m){ html+='<div class="deed"><i>'+fmtYear(m.y)+
      ':</i> '+m.k+'</div>'; }); }
  html+='<div class="sec">черты</div>';
  d.traits.forEach(function(t2){ html+='<span class="chip">'+t2[0]+' '+
    lvlWord(t2[1])+'</span>'; });
  html+='<div class="sec">убеждения</div>';
  d.beliefs.forEach(function(b2){ html+='<span class="chip">'+b2[0]+'</span>'; });
  if(d.taught) html+='<div class="kv" style="margin-top:8px">выучил учеников: <b>'+
    d.taught+'</b></div>';
  EL.dcard.innerHTML=html;
}
function lvlWord(v){ return v>0.75?'●●●':v>0.55?'●●':v>0.4?'●':'○'; }
function fmtYear(y){ if(y===null||y===undefined) return '';
  return y<0? Math.abs(y)+' г. до н. э.': y+' г. н. э.'; }
function addMsg(who,txt,me,err){
  var d=document.createElement('div'); d.className='msg'+(me?' me':'')+(err?' err':'');
  d.innerHTML='<div class="who">'+who+'</div><div class="txt"></div>';
  d.querySelector('.txt').textContent=txt;
  EL.dmsgs.appendChild(d); EL.dmsgs.scrollTop=EL.dmsgs.scrollHeight;
}

/* шаблонные ответы из данных мира */
function rngOf(u,topic){ var s=0, str=u.d.name+topic+(u.clicks||0);
  for(var i=0;i<str.length;i++) s=(s*31+str.charCodeAt(i))|0;
  return mulberry(s); }
function god(rng){ return S.gods&&S.gods.length? pick(rng,S.gods):'небо'; }
function styleUp(u,rng,s){
  var tr=u.d.tr||{};
  if(tr.aggression>0.66&&rng()<0.8)
    s=pick(rng,['Ну?.. ','Говори быстрее. ','Чего пристал? '])+s;
  if(tr.piety>0.66&&rng()<0.7)
    s+=' Да хранит нас '+god(rng)+'.';
  if(tr.curiosity>0.7&&rng()<0.5)
    s+=' '+pick(rng,['А сам-то ты чьих будешь?','А ты откуда идёшь, путник?',
      'Расскажи и ты что-нибудь.']);
  if(tr.sociability<0.3&&s.length>140) s=s.slice(0,s.indexOf('.')+1);
  return s;
}
function greet(u){
  var rng=rngOf(u,'hi'), t=G.t, d=u.d;
  var when=t<0.29?'Рано ты на ногах.':t>0.72?'Поздно уже, темнеет.':'';
  var base;
  if(d.tr&&d.tr.aggression>0.66) base=pick(rng,['Чего тебе?','Не стой над душой.',
    'Ну, говори, зачем пришёл.']);
  else if(d.role==='trader') base=pick(rng,['Подходи, смотри, что привёз!',
    'Хочешь чего? Всё есть, всё продам.']);
  else if(d.role==='priest') base=pick(rng,['Мир тебе под оком '+god(rng)+'.',
    'Боги видят тебя, путник.']);
  else if(d.role==='chief') base=pick(rng,['Говори, с чем пришёл.',
    'Я слушаю. Коротко.']);
  else base=pick(rng,['Здравствуй, путник.','Мир тебе.','Добрый тебе путь.',
    'Не видел тебя раньше.']);
  return (base+' '+when).trim();
}
var ROLE_STORY={
  chief:['Я веду людей — и в спор, и в поле, и на войну.',
    'Моё слово здесь весит больше прочих.'],
  priest:['Я служу богам и читаю их волю по огню и птицам.',
    'Я стою между людьми и небом.'],
  warrior:['Моё дело — копьё и стена щитов.','Я охраняю этот город.'],
  trader:['Я вожу товар и меняю его с выгодой.','Мои руки помнят вес всякого добра.'],
  artisan:['Я делаю вещи своими руками — и они переживут меня.',
    'Ремесло кормит меня и мою семью.'],
  farmer:['Моя жизнь — земля, зерно и дожди.','Я кормлю этот город со своего поля.'],
  hunter:['Я знаю след любого зверя в округе.','Лук и терпение — вот моя жизнь.'],
  healer:['Я лечу травами и словом.','Ко мне несут и раны, и хвори, и страхи.'],
  scribe:['Я записываю то, что нельзя доверить памяти.','Я веду счёт зерну и дням.'],
  elder:['Я стар и помню больше, чем иные видели.','Моё дело — помнить и советовать.'],
  commoner:['Живу как все: работаю, пока светло.','Моя доля простая, зато честная.'],
  rebel:['Мне не по нраву, как тут всё устроено.','Я говорю вслух то, о чём другие молчат.']};
function answer(u,topic){
  var rng=rngOf(u,topic), d=u.d, s='';
  if(topic==='who'){
    s='Я '+d.name+', '+d.role_ru+'. ';
    s+=pick(rng,ROLE_STORY[d.role]||ROLE_STORY.commoner)+' ';
    if(d.age>55) s+=pick(rng,['Годы мои уже немалые.','Мало кто доживает до моих лет.'])+' ';
    else if(d.age<22) s+='Я ещё молод, но своё дело знаю. ';
    if(d.crafts&&d.crafts.length){
      var cr=d.crafts[0];
      s+=pick(rng,['Моё дело — '+cr[0]+', и рука у меня к нему привычная. ',
        'Всю жизнь моё ремесло — '+cr[0]+'. ',
        'Что умею, то умею: '+cr[0]+'. ']);
      if(cr[1]>0.6&&d.age>45) s+='Учился этому дольше, чем иные живут. ';
    }
    if(d.taught>0) s+='Кое-кого я и сам выучил. ';
    if(d.scars&&Object.keys(d.scars).length&&rng()<0.75){
      var sk=Object.keys(d.scars)[0];
      s+=pick(rng,['Через '+sk+' я прошёл, и это со мной осталось. ',
        'Меня не переучишь: я знаю, что такое '+sk+'. ']);
    }
    if(d.deeds&&d.deeds.length){ var dd=pick(rng,d.deeds);
      s+='Про меня в народе помнят: '+dd.t+' — это было в '+fmtYear(dd.y)+'.'; }
    else if(d.real) s+='Моё имя записано в книге людей этого мира.';
  }
  else if(topic==='news'){
    var evs=S.events||[];
    if(evs.length&&rng()<0.85){
      var e=pick(rng,evs); var ago=S.year-e.y;
      if(ago>70) s='Старики ещё рассказывают: '+e.t+' С тех пор минуло '+
        ago+' лет. ';
      else if(ago>8) s='У нас всё говорят о том, что '+
        ('было лет '+ago+' назад: ')+e.t+' ';
      else s='Вот последняя новость: '+e.t+' ';
      if(evs.length>1&&rng()<0.5){ var e2=pick(rng,evs);
        if(e2!==e) s+=pick(rng,['А ещё было: ','Помнят и другое: '])+e2.t; }
    } else {
      s=pick(rng,['На рынке всё дорожает, вот и все новости.',
        'Урожай нынче '+pick(rng,['добрый','скудный','как обычно'])+', о том и разговоры.',
        'Чужих вроде тебя стало больше на дорогах.',
        'Всё тихо, и слава богам.']);
    }
  }
  else if(topic==='faith'){
    var g2=god(rng);
    s=pick(rng,['Наш город держит '+g2+'. ','Я чту '+g2+', как чтили отцы. ',
      g2+' видит всех нас, и это не пустые слова. ']);
    if(S.gods&&S.gods.length>1&&rng()<0.6)
      s+='А ещё мы чтим '+pick(rng,S.gods.filter(function(x){return x!==g2;}))+'. ';
    if(d.beliefs&&d.beliefs.length){
      s+='Сам я живу с одной думой: '+pick(rng,d.beliefs)[0]+'.'; }
    if(d.tr&&d.tr.piety<0.3) s+=' Хотя, скажу тебе тихо, жертвы я ношу больше по привычке.';
  }
  else { // folk
    s=S.polity+' — это '+S.form_ru+'; мы '+S.mode_ru+'. ';
    s+=pick(rng,['Нас теперь '+S.polity_pop_ru+' душ. ',
      'Народу у нас — '+S.polity_pop_ru+', сосчитай попробуй. ']);
    if(S.capital_of&&S.capital_of!==S.name&&rng()<0.6)
      s+='Престольный город наш — '+S.capital_of+'. ';
    if(S.walls&&rng()<0.5) s+='Стены наши — гордость города. ';
    if(S.coastal&&rng()<0.5) s+='Море нас кормит и связывает с дальними берегами. ';
    else if(S.river&&rng()<0.5) s+='Река даёт нам воду и путь. ';
    s+=pick(rng,['Живём как умеем, но живём.','Худо-бедно, а свой очаг лучше чужого.',
      'Наши боги нас пока не оставили.']);
  }
  return styleUp(u,rng,s);
}

/* Anthropic API — только по ключу игрока */
function dossier(u){
  var d=u.d, out=[];
  out.push('Ты — '+d.name+', '+d.role_ru+' из народа '+S.polity+
    '. Ты живёшь в поселении '+S.name+' ('+S.tier+'), сейчас '+S.year_ru+
    ', эпоха: '+S.era+'. Тебе '+d.age+' лет. Пол: '+(d.sex? 'мужской':'женский')+'.');
  out.push('Твой народ: '+S.form_ru+', уклад — '+S.mode_ru+', всего вас '+
    S.polity_pop_ru+'. Боги народа: '+(S.gods||[]).join(', ')+'.');
  if(d.traits.length) out.push('Твои черты: '+d.traits.map(function(t){
    return t[0]+' ('+t[1]+')'; }).join(', ')+'.');
  if(d.beliefs.length) out.push('Твои убеждения: '+d.beliefs.map(function(b){
    return b[0]; }).join('; ')+'.');
  if(d.deeds&&d.deeds.length) out.push('Твои деяния: '+d.deeds.map(function(x){
    return fmtYear(x.y)+' — '+x.t; }).join('; ')+'.');
  // Прожитая жизнь — главное, что отличает тебя от любого другого человека.
  if(d.crafts&&d.crafts.length) out.push('Чему выучились твои руки за жизнь: '+
    d.crafts.map(function(c){ return c[0]+' ('+Math.round(c[1]*100)+' из 100); '; })
    .join('')+' Ты говоришь о своём деле уверенно и подробно, о чужом — как мирянин.');
  if(d.scars&&Object.keys(d.scars).length) out.push('Что ты пережил и что оставило '+
    'на тебе след навсегда: '+Object.keys(d.scars).map(function(k){
      return k+' ('+Math.round(d.scars[k]*100)+' из 100)'; }).join(', ')+
    '. Это влияет на твои решения до сих пор, даже когда всё хорошо.');
  if(d.memories&&d.memories.length) out.push('Ты лично помнишь: '+
    d.memories.map(function(m){ return fmtYear(m.y)+' — '+m.k; }).join('; ')+
    '. Об этом ты рассказываешь как очевидец, а не с чужих слов.');
  if(d.taught) out.push('Ты выучил '+d.taught+' учеников — своё умение ты передал.');
  else if(d.crafts&&d.crafts.length&&d.age>45) out.push(
    'Учеников у тебя нет: то, что ты умеешь, уйдёт с тобой. Ты об этом думаешь.');
  var evs=(S.events||[]).map(function(e){ return fmtYear(e.y)+' — '+e.t; });
  if(evs.length) out.push('События, которые помнит твой народ: '+evs.join(' '));
  out.push('Местность: '+S.biome_ru+(S.river?', рядом река':'')+
    (S.coastal?', у моря':'')+'. Сейчас '+dayWord(G.t)+'.');
  out.push('Правила: отвечай по-русски, 1–3 короткими предложениями, строго в характере. '+
    'Ты человек своего времени: не знаешь будущего, дальних стран и современных понятий. '+
    'Никогда не упоминай, что ты персонаж или модель. Говори живо, как на улице.');
  return out.join('\n');
}
function bindAPI(){
  EL.apiKey.addEventListener('input',function(){
    var on=EL.apiKey.value.trim().length>8;
    EL.apiMsg.disabled=!on; EL.apiSend.disabled=!on; });
  function send(){
    var key=EL.apiKey.value.trim(), msg=EL.apiMsg.value.trim();
    if(!key||!msg||!G.dialog) return;
    var u=G.dialog;
    addMsg('Вы',msg,true); EL.apiMsg.value='';
    G.chat.push({role:'user',content:msg});
    var hist=G.chat.slice(-10);
    fetch('https://api.anthropic.com/v1/messages',{
      method:'POST',
      headers:{ 'content-type':'application/json', 'x-api-key':key,
        'anthropic-version':'2023-06-01',
        'anthropic-dangerous-direct-browser-access':'true' },
      body:JSON.stringify({ model:'claude-haiku-4-5', max_tokens:300,
        system:dossier(u), messages:hist })
    }).then(function(r){
      if(!r.ok) return r.text().then(function(tx){
        throw new Error('API '+r.status+': '+tx.slice(0,220)); });
      return r.json();
    }).then(function(j){
      var tx=(j.content&&j.content[0]&&j.content[0].text)||'…';
      G.chat.push({role:'assistant',content:tx});
      addMsg(u.d.name,tx,false);
    }).catch(function(err){
      addMsg('ошибка',String(err.message||err),false,true);
    });
  }
  EL.apiSend.onclick=send;
  EL.apiMsg.addEventListener('keydown',function(e){
    if(e.code==='Enter') send(); e.stopPropagation(); });
  EL.apiKey.addEventListener('keydown',function(e){ e.stopPropagation(); });
}

/* ══════════════════ 8. сцена: сборка и цикл ══════════════════ */
function startScene(idx){
  S=PLAY.scenes[idx]; GAME.scene=idx;
  NZSEED=S.seed*17+3;
  EL.menu.style.display='none';
  EL.loading.style.display='flex';
  setTimeout(function(){ buildWorld(); },40);
}
function buildWorld(){
  G={on:true, t:parseFloat(Q.get('time')||0.34), spd:1, spdReal:1, el:0,
     yaw:0, pitch:0, third:false, mapOn:false, dialog:null, chat:[],
     player:{x:0,y:0,z:0,vy:0,grounded:true}, moving:false, drag:false};
  var renderer=new THREE.WebGLRenderer({canvas:EL.c3d, antialias:!DEBUG});
  renderer.setSize(innerWidth,innerHeight);
  renderer.setPixelRatio(Math.min(devicePixelRatio,DEBUG?1:1.6));
  renderer.shadowMap.enabled=Q.get('ns')!=='1';
  renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  var scene=new THREE.Scene();
  var camera=new THREE.PerspectiveCamera(71,innerWidth/innerHeight,0.1,2600);
  camera.rotation.order='YXZ';
  R3={renderer:renderer, scene:scene, camera:camera};
  buildSky(); buildTerrain(); buildTown(); scatterVeg();
  buildNPCs(); buildFires(); buildBirds(); buildMinimap();
  // аватар для вида от третьего лица
  var geos=npcGeos();
  var av=new THREE.Group();
  var avb=new THREE.Mesh(geos.body,new THREE.MeshLambertMaterial({vertexColors:true}));
  avb.material.color=new THREE.Color('#8a7a52');
  var avh=new THREE.Mesh(geos.head,new THREE.MeshLambertMaterial({vertexColors:true}));
  avh.material.color=new THREE.Color('#c9a27c'); avh.position.y=1.78;
  avb.castShadow=avh.castShadow=true;
  av.add(avb); av.add(avh); av.visible=false;
  scene.add(av); G.avatar=av;
  // старт: у ворот, лицом к центру
  var gate=(S.pois.gates&&S.pois.gates[0])||[0,150];
  var gp=S.pois.plaza||[0,0];
  var dx=gp[0]-gate[0], dz=gp[1]-gate[1], dl=Math.hypot(dx,dz)||1;
  G.player.x=gate[0]-dx/dl*24; G.player.z=gate[1]-dz/dl*24;
  G.player.y=groundH(G.player.x,G.player.z);
  G.yaw=Math.atan2(-dx/dl,-dz/dl);
  if(Q.get('px')!==null&&Q.get('px')!==undefined&&Q.get('px')!==''){
    G.player.x=parseFloat(Q.get('px')); G.player.z=parseFloat(Q.get('pz')||0);
    G.player.y=groundH(G.player.x,G.player.z); }
  if(Q.get('yaw')) G.yaw=parseFloat(Q.get('yaw'));
  // HUD
  EL.hud.style.display='block'; EL.hint.style.display='block';
  EL.dot.style.display='block'; EL.menuBtn.style.display='block';
  EL.hudPlace.textContent=S.name;
  EL.hint.innerHTML='<b>WASD</b> шаг · <b>Shift</b> бег · <b>E</b> говорить · '+
    '<b>T</b> время · <b>F</b> вид · <b>M</b> карта'+(DEBUG?' · <b>DEBUG</b>':'');
  if(DEBUG) EL.pause.style.display='none';
  else EL.pauseText.innerHTML='Щёлкните, чтобы вернуться к прогулке.<br>'+
    'Мышь — взгляд, WASD — шаг, E — разговор с жителем.';
  EL.loading.style.display='none';
  EL.fade.style.opacity='0';
  bindAPI();
  GAME.ready=true;
  requestAnimationFrame(loop);
}
var _lastT=0, _fpsAcc=0, _fpsN=0, _hudT=0;
function loop(ts){
  if(!G||!G.on) return;
  requestAnimationFrame(loop);
  var rawDt=(ts-_lastT)/1000||0.016;
  var dt=Math.min(0.05,rawDt); _lastT=ts;
  _fpsAcc+=rawDt; _fpsN++;
  if(_fpsAcc>0.6){ GAME.fps=Math.round(_fpsN/_fpsAcc*10)/10; _fpsAcc=0; _fpsN=0; }
  G.el+=dt;
  G.spdReal=G.spd;
  G.t=(G.t+dt/360*G.spd)%1;
  if(hintT>0){ hintT-=dt; if(hintT<=0&&!nearestNPC(3.1)) EL.talk.style.display='none'; }
  if(!G.dialog) updatePlayer(dt);
  updateNPCs(dt);
  updateSky(); updateFires(dt); updateBirds();
  _hudT-=dt; if(_hudT<=0){ _hudT=0.25; updateHUD(); updateMinimap(); }
  updateLabels();
  R3.renderer.render(R3.scene,R3.camera);
}

/* ══════════════════ 9. вход ══════════════════ */
GAME.setTime=function(t){ if(G){ G.t=t; } };
GAME.teleport=function(x,z,yaw){ if(G){ G.player.x=x; G.player.z=z;
  G.player.y=groundH(x,z); if(yaw!==undefined) G.yaw=yaw; } };
GAME.openDialog=function(i){ if(!G) return;
  if(i===undefined){ tryTalk(); return; }
  var u=G.units[i]; if(u){ GAME.teleport(u.x+1.2,u.z+1.2); openDialog(u); } };
GAME.openDialogReal=function(){ if(!G) return;
  var u=G.units.find(function(q){ return q.d.real&&q.vis; })||G.units[0];
  GAME.teleport(u.x+1.2,u.z+1.2); openDialog(u); };
GAME.closeDialog=closeDialog;
GAME.info=function(){ return R3? R3.renderer.info.render:null; };
GAME.npc=function(i){ if(!G) return null; var u=G.units[i];
  return u? {x:u.x,z:u.z,vis:u.vis,name:u.d.name,real:u.d.real}:null; };
GAME.someNPC=function(real){ if(!G) return null;
  var u=G.units.find(function(q){ return q.vis&&(!real||q.d.real); })||G.units[0];
  return {i:u.i,x:u.x,z:u.z,name:u.d.name}; };

buildMenu(); bindInput();
EL.fade.style.opacity='0';
var autos=Q.get('scene');
if(autos!==null&&autos!==''){ startScene(parseInt(autos)||0); }
})();
"""
