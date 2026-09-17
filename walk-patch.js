/* Visual adapter for the immutable published terra-1 browser walk.
 * This file does not change terrain heights, settlement positions or simulation history.
 */
function terraWalkExtension(){
  function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function dayWord(t){return t<.21||t>=.84?'Night':t<.29?'Dawn':t<.45?'Morning':t<.63?'Day':t<.72?'Evening':'Sunset';}
  function fmtYear(y){return y<0?Math.abs(y).toLocaleString('en-US')+' BCE':y.toLocaleString('en-US')+' CE';}
  function buildMenu(){}
  function bindAPI(){}
  function lvlWord(v){return v>.75?'Strong':v>.45?'Moderate':'Low';}
  function updateHUD(){
    EL.hudLine.textContent=S.polity+' · '+S.form_ru+' · '+S.year_ru;
    EL.hudTime.textContent=dayWord(G.t)+' · '+fmtClock(G.t)+(G.spd>1?' · '+G.spd+'×':'')+' · '+G.units.length+' reconstructed residents';
    var u=nearestNPC(3.1);
    if(u&&!G.dialog){EL.talk.innerHTML='<b>E</b> Meet '+esc(u.d.name);EL.talk.style.display='block';}
    else if(hintT<=0)EL.talk.style.display='none';
  }
  function fillCard(u){
    var d=u.d;
    EL.dcard.innerHTML='<div class="resident-mark">'+esc(d.name.slice(0,1))+'</div><div class="eyebrow">RECONSTRUCTED RESIDENT</div><h3>'+esc(d.name)+'</h3><div class="r">'+esc(d.role_ru)+' · Age '+d.age+'</div><p class="explain">An illustrative resident of this settlement, not an independently simulated historical person.</p><div class="sec">Disposition</div>'+d.traits.map(t=>'<div class="trait"><span>'+esc(t[0])+'</span><meter min="0" max="1" value="'+t[1]+'"></meter></div>').join('')+'<div class="sec">Beliefs in the scene</div>'+d.beliefs.map(b=>'<p class="belief">'+esc(b[0])+'</p>').join('');
  }
  function greet(u){return 'I am '+u.d.name+', a '+u.d.role_ru+' here in '+S.name+'. What would you like to know?';}
  function answer(u,topic){
    if(topic==='place')return S.desc;
    if(topic==='work')return 'Our livelihood is '+S.mode_ru+'. My role here is '+u.d.role_ru+'. '+({artisan:'Tools and useful objects pass through many hands before they reach a household.',farmer:'Water, soil and the timing of the seasons shape the work.',trader:'A market connects the needs of one household with the work of another.',priest:'The community gathers around its sacred places and shared beliefs.',chief:'Leadership brings demands from many households.'}[u.d.role]||'Every household depends on the work of others.');
    if(topic==='belief')return 'This community honors '+(S.gods||[]).join(', ')+'. '+(u.d.beliefs.length?'One belief represented in my character is: '+u.d.beliefs[0][0]+'.':'');
    if(topic==='land')return 'This settlement lies in '+S.biome_ru.toLowerCase()+'. '+(S.river?'The nearby river provides water and a route across the landscape. ':'')+(S.coastal?'The coast connects this community with the water. ':'')+'The landscape and settlement layout come from the published world export.';
    return 'The chronicle in the explorer contains the recorded events of this world.';
  }
  function addMsg(name,text,mine){var box=document.createElement('div');box.className='msg'+(mine?' me':'');var who=document.createElement('div');who.className='who';who.textContent=name;var body=document.createElement('div');body.className='txt';body.textContent=text;box.append(who,body);EL.dmsgs.append(box);EL.dmsgs.scrollTop=EL.dmsgs.scrollHeight;}
  function openDialog(u){
    G.dialog=u;G.chat=[];if(document.pointerLockElement)document.exitPointerLock();
    EL.pause.style.display='none';EL.dlg.style.display='flex';EL.dmsgs.innerHTML='';fillCard(u);addMsg(u.d.name,greet(u),false);
    EL.dtopics.innerHTML='';[['place','This place'],['work','Daily life'],['belief','Beliefs'],['land','The landscape']].forEach(([key,label])=>{var b=document.createElement('button');b.textContent=label;b.onclick=()=>{addMsg('You',label,true);addMsg(u.d.name,answer(u,key),false);};EL.dtopics.append(b);});
    EL.dclose.focus();
  }
  function closeDialog(){if(!G)return;G.dialog=null;EL.dlg.style.display='none';EL.pause.style.display='none';EL.c3d.focus();}
  function terraMaterial(){
    var cv=document.createElement('canvas');cv.width=cv.height=1024;var ctx=cv.getContext('2d'),rng=mulberry(S.seed*201+33);
    ctx.fillStyle='#adaba3';ctx.fillRect(0,0,1024,1024);
    for(var row=-1;row<9;row++)for(var colm=-1;colm<9;colm++){
      var x=colm*128+(row%2)*64,y=row*128,v=228+Math.floor(rng()*25);
      ctx.fillStyle='rgb('+v+','+v+','+v+')';ctx.fillRect(x+2,y+2,124,124);
      ctx.strokeStyle='rgba(255,255,255,.27)';ctx.strokeRect(x+4,y+4,120,120);
      for(var j=0;j<48;j++){var a=rng()*.075;ctx.fillStyle='rgba(32,28,20,'+a+')';ctx.fillRect(x+rng()*128,y+rng()*128,2+rng()*17,1+rng()*3);}
    }
    var image=ctx.getImageData(0,0,1024,1024);for(var i=0;i<image.data.length;i+=4){var noise=(rng()-.5)*12;for(var k=0;k<3;k++)image.data[i+k]=clamp(image.data[i+k]+noise,0,255);}ctx.putImageData(image,0,0);
    var tex=new THREE.CanvasTexture(cv);tex.wrapS=tex.wrapT=THREE.RepeatWrapping;tex.colorSpace=THREE.SRGBColorSpace;tex.anisotropy=Math.min(8,R3.renderer.capabilities.getMaxAnisotropy());
    var bump=tex.clone();bump.colorSpace=THREE.NoColorSpace;bump.needsUpdate=true;
    var m=new THREE.MeshStandardMaterial({map:tex,bumpMap:bump,bumpScale:.08,roughness:.91,vertexColors:true});m.userData.terraMasonry=true;return m;
  }
  var _terraMesh=Bag.prototype.mesh;
  Bag.prototype.mesh=function(mat){
    var mesh=_terraMesh.call(this,mat);if(!mat.userData.terraMasonry)return mesh;
    var p=mesh.geometry.attributes.position,n=mesh.geometry.attributes.normal,uv=new Float32Array(p.count*2);
    for(var i=0;i<p.count;i++){var nx=Math.abs(n.getX(i)),ny=Math.abs(n.getY(i)),nz=Math.abs(n.getZ(i));uv[i*2]=(nx>nz?p.getZ(i):p.getX(i))/4;uv[i*2+1]=(ny>.65?p.getZ(i):p.getY(i))/4;}
    mesh.geometry.setAttribute('uv',new THREE.BufferAttribute(uv,2));return mesh;
  };
  function terraArch(bag,c,x,y,z,rot,sx,h){
    var r=Math.max(1.8,sx*.42-2.75),o=r+1.25,shape=new THREE.Shape();
    shape.absarc(0,0,o,0,Math.PI,false);shape.lineTo(-r,0);shape.absarc(0,0,r,Math.PI,0,true);shape.closePath();
    var geo=new THREE.ExtrudeGeometry(shape,{depth:6,bevelEnabled:true,bevelThickness:.10,bevelSize:.08,bevelSegments:2,steps:1,curveSegments:22});geo.translate(0,0,-3);
    bag.put(geo,c,x,y+h*.51,z,0,rot,0,1,1,1);geo.dispose();
    bag.put(PRIM.box,c.clone().multiplyScalar(1.12),x,y+h*.51+o-.2,z,0,rot,0,1.35,1.4,6.35);
  }
  function terraDetails(){
    var rng=mulberry(S.seed*913+61),deco=new Bag(),clay=col('#c58b62'),stone=col(ERACOL[S.id].stoneT),wood=col(ERACOL[S.id].wood);
    var pot=new THREE.LatheGeometry([new THREE.Vector2(.11,0),new THREE.Vector2(.3,.12),new THREE.Vector2(.38,.45),new THREE.Vector2(.27,.67),new THREE.Vector2(.15,.8),new THREE.Vector2(.18,.84)],18);
    S.buildings.forEach(function(b,index){var [kind,x,z,rot,sx,sz,h]=b,y=groundH(x,z),dx=Math.cos(rot),dz=Math.sin(rot);
      if(['house','house2','hut'].includes(kind)&&index%2===0){var edge=kind==='hut'?sx+.55:sx/2+.5;
        for(var q=0;q<2;q++){var px=x+dx*edge-dz*(q*.8+.8),pz=z+dz*edge+dx*(q*.8+.8);deco.put(pot,colVar(rng,'#c58b62',.22),px,groundH(px,pz),pz,0,rng()*6.2,0,.7+rng()*.4,1,1);}
        if(kind!=='hut'){deco.put(PRIM.box,stone,x+dx*(sx/2+.09),y+2.22,z+dz*(sx/2+.09),0,rot,0,.23,.2,1.45);deco.put(PRIM.box,stone,x+dx*(sx/2+.09)-dz*.62,y+1.12,z+dz*(sx/2+.09)+dx*.62,0,rot,0,.22,2.2,.15);}
      }
      if(kind==='gate'){for(var side of [-1,1]){var xx=x+dx*sx*.42*side,zz=z+dz*sx*.42*side;deco.put(PRIM.box,stone,xx,y+h+.16,zz,0,rot,0,6,.32,7.4);for(var ly of [.1,.48,.91])deco.put(PRIM.box,stone.clone().multiplyScalar(.94),xx,y+h*ly,zz,0,rot,0,5.72,.18,7.2);}}
      if(kind==='market'){
        var g=new THREE.PlaneGeometry(sx*1.17,sz*1.2,10,8);g.rotateX(-Math.PI/2);var p=g.attributes.position;
        for(var j=0;j<p.count;j++)p.setY(j,.16*Math.cos(p.getX(j)*2.2)-.25*(1-Math.abs(p.getX(j))/(sx*.6)));g.computeVertexNormals();
        var material=new THREE.MeshStandardMaterial({color:col(S.color).lerp(new THREE.Color('#b98357'),index%3*.26),side:THREE.DoubleSide,roughness:1});
        var m=new THREE.Mesh(g,material);m.position.set(x,y+2.94,z);m.rotation.y=rot;m.castShadow=true;R3.scene.add(m);
      }
    });
    var dm=deco.mesh(new THREE.MeshStandardMaterial({vertexColors:true,roughness:.86}));dm.castShadow=true;dm.receiveShadow=true;R3.scene.add(dm);pot.dispose();
    var cv=document.createElement('canvas');cv.width=cv.height=128;var ctx=cv.getContext('2d');ctx.fillStyle='#fff';
    for(var q=0;q<6;q++){var x=18+q*18;ctx.beginPath();ctx.moveTo(x,128);ctx.quadraticCurveTo(x-13,64,x+(q%2?12:-9),5+q*4);ctx.quadraticCurveTo(x+4,78,x+9,128);ctx.fill();}
    var alpha=new THREE.CanvasTexture(cv),geo=new THREE.PlaneGeometry(1.2,1.0,1,3);geo.translate(0,.5,0);
    var mat=new THREE.MeshLambertMaterial({color:col(getPal().grass2).lerp(new THREE.Color('#becb76'),.28),alphaMap:alpha,alphaTest:.42,side:THREE.DoubleSide,depthWrite:true});
    var im=new THREE.InstancedMesh(geo,mat,2600),matrix=new THREE.Matrix4(),quat=new THREE.Quaternion(),position=new THREE.Vector3(),scale=new THREE.Vector3(),euler=new THREE.Euler();var count=0;
    for(var a=0;a<12000&&count<2600;a++){var x=(rng()-.5)*950,z=(rng()-.5)*950,y=groundH(x,z);if(y<WATER_Y+.65||Math.hypot(x,z)<90)continue;
      var clear=true;for(var st of S.streets)if(distToSeg(x,z,st)<6){clear=false;break;}if(!clear)continue;
      for(var b of S.buildings)if(Math.hypot(x-b[1],z-b[2])<Math.max(b[4],b[5])*.8+2){clear=false;break;}if(!clear)continue;
      position.set(x,y-.03,z);euler.set(0,rng()*6.28,0);quat.setFromEuler(euler);scale.setScalar(.65+rng()*.7);matrix.compose(position,quat,scale);im.setMatrixAt(count++,matrix);
    }
    im.count=count;im.instanceMatrix.needsUpdate=true;im.receiveShadow=true;R3.scene.add(im);GAME.detailGrass=count;
  }
  var _terraSky=updateSky;
  updateSky=function(){_terraSky();R3.scene.fog.near=95;R3.scene.fog.far*=1.65;R3.hemi.intensity*=1.06;};
  window.addEventListener('message',function(ev){
    if(ev.source!==parent||!G||!ev.data)return;var data=ev.data;
    if(data.type==='terra:time')G.t=clamp(Number(data.value)||.4,0,.999);
    if(data.type==='terra:site'){var target=data.site==='plaza'?S.pois.plaza:data.site==='temple'?S.pois.temple:data.site==='gate'?S.pois.gates?.[0]:null;if(target){GAME.teleport(target[0]+9,target[1]+16,0);G.yaw=Math.atan2(9,16);}}
    if(data.type==='terra:stop'){G.on=false;R3.renderer.dispose();}
  });
  GAME.inspect=function(){return G?{player:{...G.player},npcCount:G.units.length,archivedNPCs:G.units.filter(u=>u.d.real).length,grass:GAME.detailGrass,colliders:G.colliders.length,time:G.t,errors:GAME.errors,render:GAME.info()}:null;};
}
function buildTerraWalkHTML(source,play,index){
  const scripts=[...source.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
  if(scripts.length!==3||!scripts[2].includes('function buildWorld(){'))throw Error('The published walk format has changed. The preview did not execute it.');
  let app=scripts[2];
  const from=app.indexOf('function dossier(u){'),to=app.indexOf('function startScene(idx){');
  if(from<0||to<from)throw Error('Unexpected source layout.');app=app.slice(0,from)+app.slice(to);
  app=app.replace('new URLSearchParams(location.search)',`new URLSearchParams('scene=${index}&time=0.41&debug=1')`);
  app=app.replace('antialias:!DEBUG','antialias:true').replace('DEBUG?1:1.6','1.6');
  app=app.replace('renderer.shadowMap.type=THREE.PCFSoftShadowMap;','renderer.shadowMap.type=THREE.PCFSoftShadowMap; renderer.outputColorSpace=THREE.SRGBColorSpace; renderer.toneMapping=THREE.ACESFilmicToneMapping; renderer.toneMappingExposure=1.25;');
  app=app.replace('new THREE.CylinderGeometry(0.5,0.5,1,6)','new THREE.CylinderGeometry(0.5,0.5,1,16)').replace('new THREE.ConeGeometry(0.5,1,8)','new THREE.ConeGeometry(0.5,1,20)').replace('new THREE.SphereGeometry(0.5,7,5)','new THREE.SphereGeometry(0.5,14,10)');
  app=app.replace('bag.put(PRIM.box,gc,x,y+h*0.86,z,0,rot,0,sx,h*0.3,6);','terraArch(bag,gc,x,y,z,rot,sx,h);');
  app=app.replace('var mat=new THREE.MeshLambertMaterial({vertexColors:true});\n  var mesh=bag.mesh(mat); mesh.castShadow=true; mesh.receiveShadow=true;','var mat=terraMaterial();\n  var mesh=bag.mesh(mat); mesh.castShadow=true; mesh.receiveShadow=true;');
  app=app.replace('buildNPCs(); buildFires(); buildBirds(); buildMinimap();','buildNPCs(); buildFires(); buildBirds(); buildMinimap(); terraDetails();');
  app=app.replace(' gl_FragColor=vec4(c,1.0);}', ' gl_FragColor=vec4(c,1.0);\\n#include <colorspace_fragment>\\n}');
  app=app.replace("EL.menuBtn.onclick=function(){ location.href=location.pathname; };","EL.menuBtn.onclick=function(){ parent.postMessage({type:'terra-exit'},'*'); };");
  app=app.replace("(DEBUG?' · <b>DEBUG</b>':'')","''");
  const words={'Столбы предков':'Ancestral pillars','Святилище ':'Sanctuary of ','время ×':'Time ×','вид со спины':'Third-person view','вид от первого лица':'First-person view','шаг':'walk','бег':'run','говорить':'meet','время':'time','вид':'view','карта':'map','Щёлкните, чтобы вернуться к прогулке.':'Click to resume the walk.','Мышь — взгляд, WASD — шаг, E — разговор с жителем.':'Mouse to look, WASD to walk, E to meet a resident.','Щёлкните':'Click','пауза':'Paused'};
  for(const [ru,en]of Object.entries(words).sort((a,b)=>b[0].length-a[0].length))app=app.split(ru).join(en);
  const ext=terraWalkExtension.toString().slice(terraWalkExtension.toString().indexOf('{')+1,-1);
  const upgrade=terraSceneUpgrade.toString().slice(terraSceneUpgrade.toString().indexOf('{')+1,-1);
  const scenery04=terraScene04.toString().slice(terraScene04.toString().indexOf('{')+1,-1);
  app=app.replace('buildMenu(); bindInput();',ext+'\n'+upgrade+'\n'+scenery04+'\nbuildMenu(); bindInput();');
  app=app.replace('var t=b[0], x=b[1], z=b[2]', 'TERRA_SURFACE_CONTEXT=b[0]; var t=b[0], x=b[1], z=b[2]');
  const css=`*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#101c24;color:#f2eadc;font:14px system-ui,sans-serif}button{font:inherit;cursor:pointer}#c3d{position:fixed;inset:0;width:100%;height:100%;display:block;outline:none}#hud{position:fixed;left:24px;top:22px;z-index:20;pointer-events:none;padding:16px 20px;background:#10242bc9;border:1px solid #ffffff20;border-radius:4px;backdrop-filter:blur(12px)}#hudPlace{font:30px Georgia,serif}#hudLine,#hudTime{font-size:12px;color:#e2d8c6;margin-top:6px}#menuBtn{position:fixed;right:24px;top:22px;z-index:25;background:#10242bdc;color:#f5eddc;border:1px solid #ffffff40;padding:11px 17px;border-radius:3px}#hint{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);white-space:nowrap;z-index:22;background:#10242be6;border:1px solid #ffffff25;padding:10px 16px;border-radius:4px;font-size:12px}#dot{position:fixed;left:50%;top:50%;width:4px;height:4px;border-radius:50%;background:#fff9;z-index:20}#map{position:fixed;right:24px;top:77px;z-index:20;display:none;border:1px solid #f1dfbb66;border-radius:4px}#talk{position:fixed;bottom:95px;left:50%;transform:translateX(-50%);z-index:25;background:#142d35e8;padding:12px 22px;border:1px solid #c5a566;border-radius:3px;display:none}#talk b{color:#e4c88e;margin-right:10px}#pause{position:fixed;inset:0;background:#051418a0;z-index:35;display:none;align-items:center;justify-content:center;backdrop-filter:blur(3px)}#pauseText{background:#13272e;padding:30px;line-height:2;border:1px solid #bca67870;cursor:pointer}#loading{position:fixed;inset:0;background:#0c1b22;z-index:50;display:flex;align-items:center;justify-content:center;font:26px Georgia,serif}#fade,#menu{display:none!important}#dlg{position:fixed;inset:0;z-index:40;display:none;align-items:center;justify-content:center;background:#041116bc;backdrop-filter:blur(7px)}#dlgBox{width:min(920px,94vw);height:min(640px,88vh);display:flex;background:#11242d;border:1px solid #c8b38655;box-shadow:0 24px 120px #0008}#dcard{width:310px;padding:27px;border-right:1px solid #ffffff17;overflow:auto}#dright{flex:1;min-width:0;display:flex;flex-direction:column}#dmsgs{flex:1;overflow:auto;padding:25px;line-height:1.65}.msg{margin-bottom:20px}.who{font-size:11px;color:#bba779;letter-spacing:.12em;margin-bottom:5px}.txt{background:#ffffff08;padding:12px 15px;border-radius:4px}.me{text-align:right}#dtopics{padding:14px;display:flex;gap:8px;flex-wrap:wrap;border-top:1px solid #ffffff15}#dtopics button,#dclose{background:#ffffff09;border:1px solid #ffffff25;color:#f3e8d3;padding:10px 13px;border-radius:3px}#dclose{margin:0 14px 14px}#dapi{display:none}.resident-mark{font:76px Georgia,serif;color:#d1ba80;margin-bottom:15px;border-bottom:1px solid #ffffff20}.eyebrow,.sec{font-size:10px;letter-spacing:.14em;color:#c8b386}.sec{margin-top:24px}h3{font:29px Georgia,serif;margin:10px 0}.r{font-size:12px;color:#d1c3aa}.explain{font-size:12px;line-height:1.65;color:#8eabad}.trait{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px;font-size:12px}.trait meter{width:80px}.belief{font:italic 14px/1.6 Georgia,serif;color:#ddd0b6}button:focus-visible{outline:2px solid #e8ce8e;outline-offset:3px}@media(max-width:700px){#hud{left:10px;top:10px;padding:12px}#hudPlace{font-size:22px}#menuBtn{right:10px;top:10px;padding:8px}#hint{font-size:10px;max-width:96%;white-space:normal;width:90%;text-align:center}#dcard{width:38%;padding:16px}#dlgBox{height:92vh}#dmsgs{padding:14px}}`;
  const body=`<canvas id="c3d" tabindex="0" aria-label="Interactive 3D walk"></canvas><div id="hud"><div id="hudPlace"></div><div id="hudLine"></div><div id="hudTime"></div></div><button id="menuBtn">Exit walk</button><canvas id="map" width="230" height="230" aria-label="Local map"></canvas><div id="dot"></div><div id="talk"></div><div id="hint">Click to look around · WASD to walk · E to meet a resident</div><div id="menu"><div id="cards"></div><div id="menuFoot"></div></div><div id="pause"><div id="pauseText">Click to resume</div></div><div id="dlg"><div id="dlgBox"><div id="dcard"></div><div id="dright"><div id="dmsgs"></div><div id="dtopics"></div><div id="dapi"><input id="apiKey"><input id="apiMsg"><button id="apiSend"></button></div><button id="dclose">Back to the world · Esc</button></div></div></div><div id="loading">Entering ${play.scenes[index].name}…</div><div id="fade"></div>`;
  const script=s=>'<scr'+'ipt>'+s.replace(/<\/script/gi,'<\\/script')+'</scr'+'ipt>';
  return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Terra · '+play.scenes[index].name+'</title><style>'+css+'</style></head><body>'+body+script(scripts[0])+script('var PLAY='+JSON.stringify(play)+';')+script(app)+'</body></html>';
}
