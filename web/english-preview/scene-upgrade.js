/* Terra 0.3: presentation-only improvements for the immutable terra-1 archive.
   The function body is injected into the verified legacy renderer's closure. */
function terraSceneUpgrade(){
  var TERRA_SURFACE_CONTEXT='',terraTouch=null,terraMotion={held:false,x:0,y:0},terraQuality='auto';
  var terraMobile=matchMedia('(pointer:coarse)').matches;
  var terraAssets={};
  function terraCanvas(size,paint){var c=document.createElement('canvas');c.width=c.height=size;paint(c.getContext('2d'),size);var t=new THREE.CanvasTexture(c);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=R3?Math.min(8,R3.renderer.capabilities.getMaxAnisotropy()):4;return t;}
  // Texture generation is deterministic and does not modify terrain or history.
  groundTexture=function(){
    var t=terraCanvas(512,function(g,n){var r=mulberry(41017+S.seed);g.fillStyle='#bfb8a1';g.fillRect(0,0,n,n);
      for(var i=0;i<54000;i++){var v=150+r()*100;g.fillStyle='rgba('+v+','+(v*.98)+','+(v*.9)+','+(.08+r()*.21)+')';var x=r()*n,y=r()*n;g.fillRect(x,y,1+r()*2,1+r()*2);}
      for(var i=0;i<650;i++){g.fillStyle=r()>.55?'#b6ad98':'#d0c5ab';g.beginPath();g.ellipse(r()*n,r()*n,1+r()*2,.5+r()*1.3,r()*6,0,6.29);g.fill();}
    });t.repeat.set(170,170);return t;
  };
  var terraPut=Bag.prototype.put;
  Bag.prototype.put=function(geo,c,x,y,z,rx,ry,rz,sx,sy,sz,ao){
    var start=this.base;terraPut.apply(this,arguments);var k=0,tag=TERRA_SURFACE_CONTEXT;
    if(tag==='hut'||tag==='tent'||tag==='granary'){k=(geo===PRIM.cone||geo===PRIM.cone3)?4:1;}
    else if(['wall','gate','tower','temple','well','stela'].includes(tag))k=2;
    else if(['house','house2','yard'].includes(tag))k=1;
    if(geo===PRIM.prism)k=3;
    // Very narrow structural pieces and dark brown material are wood, not masonry.
    if((Math.max(c.r,c.g,c.b)<.21&&c.r>c.b*1.13)||(geo===PRIM.cyl&&sx<.3))k=5;
    if(tag==='market'||tag==='rack'||tag==='jetty'||tag==='boat'||tag==='pen')k=5;
    if(!this.terraKinds)this.terraKinds=new Array(start).fill(0);
    for(var j=start;j<this.base;j++)this.terraKinds.push(k);
  };
  var terraMesh=Bag.prototype.mesh;
  Bag.prototype.mesh=function(mat){var m=terraMesh.call(this,mat);if(mat.userData.terraSurfaces)m.geometry.setAttribute('terraKind',new THREE.Float32BufferAttribute(this.terraKinds||new Array(this.base).fill(0),1));return m;};
  terraMaterial=function(){
    var mat=new THREE.MeshStandardMaterial({vertexColors:true,roughness:.94});mat.userData.terraSurfaces=true;
    mat.onBeforeCompile=function(s){
      s.vertexShader='attribute float terraKind; varying float vTerraKind; varying vec3 vTerraPosition; varying vec3 vTerraNormal;\n'+s.vertexShader;
      s.vertexShader=s.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nvTerraKind=terraKind;vTerraPosition=position;vTerraNormal=normal;');
      s.fragmentShader='varying float vTerraKind; varying vec3 vTerraPosition; varying vec3 vTerraNormal;\nfloat thash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}\n'+s.fragmentShader;
      s.fragmentShader=s.fragmentShader.replace('#include <map_fragment>',`#include <map_fragment>
        vec3 tn=abs(normalize(vTerraNormal));vec2 uv=tn.y>.7?vTerraPosition.xz:(tn.x>tn.z?vTerraPosition.zy:vTerraPosition.xy);
        float grain=thash(floor(uv*210.)); float tone=1.;
        if(vTerraKind>1.5 && vTerraKind<2.5){
          vec2 b=uv*vec2(1.2,2.8);b.x+=mod(floor(b.y),2.)*.5;vec2 edge=min(fract(b),1.-fract(b));
          float seam=smoothstep(.012,.055,min(edge.x,edge.y));tone=mix(.7,.92+thash(floor(b))*.19,seam);
        }else if(vTerraKind>2.5 && vTerraKind<3.5){
          vec2 b=uv*vec2(3.0,3.3);b.x+=mod(floor(b.y),2.)*.5;
          tone=.79+.2*sin(fract(b.x)*3.14159);tone*=mix(.7,1.,smoothstep(.025,.09,fract(b.y)));
        }else if(vTerraKind>3.5 && vTerraKind<4.5){tone=.78+.24*thash(vec2(floor(uv.x*75.),floor(uv.y*5.)));}
        else if(vTerraKind>4.5){tone=.73+.26*thash(vec2(floor(uv.x*80.),floor(uv.y*.9)));}
        else if(vTerraKind>.5){tone=.96+.065*sin(uv.x*.73)*sin(uv.y*1.4);tone*=.91+.09*smoothstep(0.,2.,vTerraPosition.y-2.3);}
        diffuseColor.rgb*=tone*(.95+grain*.075);
      `);
    };mat.customProgramCacheKey=()=> 'terra-surfaces-03';return mat;
  };
  function terraStoneTexture(){return terraCanvas(512,function(g,n){var r=mulberry(9481);g.fillStyle='#8c8371';g.fillRect(0,0,n,n);for(var y=-1;y<10;y++)for(var x=-1;x<9;x++){var xx=x*70+(y%2)*35,yy=y*56;var v=169+r()*55;g.fillStyle='rgb('+v+','+(v*.96)+','+(v*.86)+')';g.beginPath();g.roundRect(xx+2,yy+2,66-r()*3,52-r()*3,3);g.fill();g.strokeStyle='#f7efd92b';g.stroke();for(var j=0;j<15;j++){g.fillStyle='#675f441b';g.fillRect(xx+r()*66,yy+r()*52,1+r()*9,1);}}});}
  function terraPaths(){
    var texture=terraStoneTexture();texture.repeat.set(1,1);var mat=new THREE.MeshStandardMaterial({map:texture,color:S.id==='capital'?'#e5d8b8':'#b9a887',roughness:1});
    var pos=[],uv=[],idx=[];function ribbon(x1,z1,x2,z2,width){var dx=x2-x1,dz=z2-z1,len=Math.hypot(dx,dz);if(len<1)return;var nx=-dz/len,nz=dx/len,steps=Math.ceil(len/2),base=pos.length/3;
      for(var j=0;j<=steps;j++){var t=j/steps;for(var side of [-1,1]){var x=x1+dx*t+nx*width*side/2,z=z1+dz*t+nz*width*side/2;pos.push(x,groundH(x,z)+.028,z);uv.push((side+1)*width/5,len*t/2.5);}}
      for(var j=0;j<steps;j++){var b=base+j*2;idx.push(b,b+1,b+2,b+1,b+3,b+2);}
    }
    if(S.id==='capital')for(var road of S.streets)ribbon(road[0],road[1],road[2],road[3],3.8);
    if(S.id==='capital'){var p=S.pois.plaza;for(var i=-8;i<=8;i++)ribbon(p[0]-13,p[1]+i*1.6,p[0]+13,p[1]+i*1.6,1.64);}
    if(pos.length){var geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));geo.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));geo.setIndex(idx);geo.computeVertexNormals();var m=new THREE.Mesh(geo,mat);m.receiveShadow=true;R3.scene.add(m);}else{mat.dispose();texture.dispose();}
  }
  // A deterministic, visibly denser canopy, with clear paths and preserved building footprints.
  function terraCanopy(){
    var rng=mulberry(S.seed*821+7),trunk=new Bag(),leaf=new Bag(),P=getPal(),tropical=S.biome===10||S.biome===12;
    TERRA_SURFACE_CONTEXT='vegetation';
    var count=0,leafGeo=new THREE.IcosahedronGeometry(.5,1),branchGeo=new THREE.CylinderGeometry(.05,.11,1,7);
    var landmarks=S.pois.plaza||[0,0],placements=[];
    function clear(x,z,near){if(groundH(x,z)<WATER_Y+1.1)return false;if(Math.hypot(x-landmarks[0],z-landmarks[1])<(near?17:23))return false;
      for(var st of S.streets)if(distToSeg(x,z,st)<6)return false;
      var q=pushOut(x,z,2.1);if(Math.hypot(q[0]-x,q[1]-z)>.01)return false;
      for(var b of S.buildings){if(['field','pen'].includes(b[0])&&Math.hypot(x-b[1],z-b[2])<Math.max(b[4],b[5])+5)return false;if(Math.hypot(x-b[1],z-b[2])<Math.max(4,Math.min(b[4],b[5])*.65+3))return false;}return true;
    }
    // Shaded edges around the town center, never in roads or inside structures.
    for(var i=0;i<80&&placements.length<13;i++){var a=i*2.4,r=23+rng()*24,x=landmarks[0]+Math.cos(a)*r,z=landmarks[1]+Math.sin(a)*r;if(clear(x,z,true)&&!placements.some(p=>Math.hypot(p[0]-x,p[1]-z)<8))placements.push([x,z,.85]);}
    for(var i=0;i<1200&&placements.length<(tropical?210:S.id==='neolithic'?65:135);i++){var a=rng()*6.283,r=95+rng()*420,x=Math.cos(a)*r,z=Math.sin(a)*r;if(clear(x,z,false))placements.push([x,z,1]);}
    for(var it of placements){var [x,z,scale]=it,y=groundH(x,z),h=(tropical?9:6)*( .8+rng()*.65)*scale,lean=(rng()-.5)*.15;
      trunk.put(PRIM.cyl,colVar(rng,P.trunk,.16),x,y+h*.42,z,lean,0,lean*.4,.38,h*.84,.38);
      for(var j=0;j<4;j++){var a=j*1.6+rng()*.7,len=h*(.26+rng()*.16),xx=x+Math.cos(a)*len*.43,zz=z+Math.sin(a)*len*.43;
        trunk.put(branchGeo,col(P.trunk),xx,y+h*.6,zz,Math.cos(a)*.7,0,Math.sin(a)*.7,1,len,1);
      }
      for(var j=0;j<13;j++){var a=rng()*6.28,r=rng()*h*.28,hh=h*(.72+rng()*.32);var c=colVar(rng,j%2?P.treeA:P.treeB,.2);
        leaf.put(leafGeo,c,x+Math.cos(a)*r,y+hh,z+Math.sin(a)*r,rng(),rng()*6,0,h*.48,h*(tropical?.23:.3),h*.44);
      }count++;
    }
    for(var [bag,mat] of [[trunk,new THREE.MeshStandardMaterial({vertexColors:true,roughness:1})],[leaf,new THREE.MeshStandardMaterial({vertexColors:true,roughness:.95})]]){var m=bag.mesh(mat);m.castShadow=true;m.receiveShadow=true;R3.scene.add(m);}
    leafGeo.dispose();branchGeo.dispose();GAME.canopyTrees=count;
  }
  function terraTownLife(){
    TERRA_SURFACE_CONTEXT='wood';var rng=mulberry(331+S.seed),bag=new Bag(),wood=col('#624831'),linen=col('#d8c396'),tint=col(S.color);G.terraCloths=[];
    var potGeo=new THREE.LatheGeometry([new THREE.Vector2(.12,0),new THREE.Vector2(.23,.10),new THREE.Vector2(.29,.4),new THREE.Vector2(.2,.65),new THREE.Vector2(.13,.8),new THREE.Vector2(.17,.84)],16);
    var ring=new THREE.TorusGeometry(.28,.026,5,20),barrel=new THREE.CylinderGeometry(.24,.30,.62,12),fruit=new THREE.SphereGeometry(.09,7,5);
    var nProps=0;
    for(var b of S.buildings){var [kind,x,z,rot,sx,sz,h]=b,y=groundH(x,z),ca=Math.cos(rot),sa=Math.sin(rot);
      function put(g,c,lx,ly,lz,scx,scy,scz){bag.put(g,c,x+ca*lx-sa*lz,y+ly,z+sa*lx+ca*lz,0,rot,0,scx,scy,scz);nProps++;}
      if(kind==='market'){
        for(var j=0;j<4;j++){var off=(j-1.5)*sx*.17;put(barrel,col('#927148'),off,1.15,0,1,.28,1);for(var k=0;k<7;k++)put(fruit,col(j%2?'#b47739':'#697a39'),off+(rng()-.5)*.37,1.3+rng()*.11,(rng()-.5)*.35,1,1,1);}
        for(var side of [-1,1]){put(potGeo,col('#b5774c'),side*sx*.44,.03,sz*.54,1.35,1.35,1.35);put(ring,linen,side*sx*.44,.04+.42,sz*.54,1.02,1.02,1.02);}
      }
      if(kind==='hut'||kind==='tent'){
        var edge=sx+1.25;
        put(barrel,col('#9e8156'),edge,.32,.85,1.45,1.05,1.45);
        for(var row=0;row<5;row++)put(ring,col(row%2?'#715d42':'#c6a56d'),edge,.12+row*.11,.85,1.4,1.4,1.4);
        put(PRIM.ico,col('#817869'),edge+.7,.16,-.65,1.2,.3,.83);
        put(PRIM.ico,col('#b0a18b'),edge+.74,.36,-.63,.35,.22,.29);
        put(potGeo,col('#9c7050'),edge,.015,-1.35,.73,.73,.73);
      }
      if((kind==='house'||kind==='house2')&&rng()<.5){
        put(PRIM.box,wood,sx*.5+.45,.47,sz*.37,.85,.13,1.75);
        for(var l of [-.6,.6])put(PRIM.cyl,wood,sx*.5+.45,.22,sz*.37+l,.085,.46,.085);
        put(potGeo,colVar(rng,'#b6754b',.18),sx*.5+.5,.55,sz*.4,.48,.48,.48);
        var lint=kind==='house2'?h*1.45:h*.83;put(PRIM.box,wood,0,lint,sz*.5+.1,sx*.7,.13,.13);
      }
      if(kind==='gate'||(kind==='temple'&&S.id!=='neolithic')){
        for(var side of [-1,1]){var xx=x+side*sx*.34,zz=z+sz*.52;
          bag.put(PRIM.cyl,wood,xx,y+h*.9,zz,0,0,0,.09,h*.46,.09);
          var geo=new THREE.PlaneGeometry(1.9,3.1,7,12);geo.translate(.95,-1.55,0);
          var m=new THREE.Mesh(geo,new THREE.MeshStandardMaterial({color:tint.clone().lerp(linen,.22),side:THREE.DoubleSide,roughness:1}));m.position.set(xx,y+h*1.07,zz);m.castShadow=true;R3.scene.add(m);G.terraCloths.push(m);
        }
      }
    }
    var props=bag.mesh(new THREE.MeshStandardMaterial({vertexColors:true,roughness:.93}));props.castShadow=true;props.receiveShadow=true;R3.scene.add(props);potGeo.dispose();ring.dispose();barrel.dispose();fruit.dispose();GAME.streetProps=nProps;
  }
  var terraOldDetails=terraDetails;
  terraDetails=function(){terraOldDetails();terraPaths();terraCanopy();terraTownLife();};
  // Individual heads retain the archived clothing palette; residents remain reconstructions.
  npcGeos=function(){
    var b=new Bag(),h=new Bag(),white=new THREE.Color(1,1,1),hair=col('#30251f'),dark=col('#493f35');
    var tunic=new THREE.CylinderGeometry(.24,.34,.72,12),sphere=new THREE.SphereGeometry(.5,14,10);
    b.put(tunic,white,0,1.03,0,0,0,0,1,1,1);b.put(PRIM.cyl,dark,0,.88,0,0,0,0,.61,.06,.52);
    b.put(sphere,white,0,1.34,0,0,0,0,.57,.3,.4);
    h.put(sphere,white,0,0,0,0,0,0,.37,.43,.36);
    h.put(sphere,hair,0,.10,-.055,0,0,0,.39,.31,.32);
    h.put(PRIM.cyl,white,0,-.24,0,0,0,0,.12,.17,.12);
    h.put(sphere,white,0,-.02,.176,0,0,0,.073,.115,.083);
    for(var side of [-1,1]){h.put(sphere,dark,side*.083,.04,.163,0,0,0,.035,.023,.026);h.put(sphere,white,side*.186,-.014,0,0,0,0,.064,.12,.052);}
    h.put(sphere,dark,0,-.105,.16,0,0,0,.082,.017,.017);
    var bm=b.mesh(new THREE.MeshBasicMaterial()).geometry,hm=h.mesh(new THREE.MeshBasicMaterial()).geometry;tunic.dispose();sphere.dispose();return {body:bm,head:hm};
  };
  var terraNPCBuild=buildNPCs;
  buildNPCs=function(){terraNPCBuild();var n=G.units.length;
    G.terraLimbs=new THREE.InstancedMesh(new THREE.CapsuleGeometry(.075,.50,3,8),new THREE.MeshStandardMaterial({roughness:1}),n*4);
    G.terraHands=new THREE.InstancedMesh(new THREE.SphereGeometry(.079,9,6),new THREE.MeshStandardMaterial({roughness:.92}),n*2);
    var c=new THREE.Color();for(var u of G.units){G.npcBody.getColorAt(u.i,c);for(var j=0;j<4;j++)G.terraLimbs.setColorAt(u.i*4+j,c.clone().multiplyScalar(j<2?.55:1));G.npcHead.getColorAt(u.i,c);for(var j=0;j<2;j++)G.terraHands.setColorAt(u.i*2+j,c);}
    G.terraLimbs.castShadow=G.terraHands.castShadow=true;R3.scene.add(G.terraLimbs,G.terraHands);
  };
  var terraNPCUpdate=updateNPCs,terraMat=new THREE.Matrix4(),terraQuat=new THREE.Quaternion(),terraVec=new THREE.Vector3(),terraScale=new THREE.Vector3(),terraEuler=new THREE.Euler();
  updateNPCs=function(dt){terraNPCUpdate(dt);if(!G.terraLimbs)return;
    for(var u of G.units){var yaw=-u.yaw+Math.PI/2,ca=Math.cos(yaw),sa=Math.sin(yaw),s=u.vis?u.scl:.0001,y=groundH(u.x,u.z),phase=G.el*7.2+u.ph,amp=u.moving?.4:.025;
      for(var j=0;j<4;j++){var side=j%2?1:-1,arms=j>=2,swing=Math.sin(phase+(j%2)*Math.PI)*amp*(arms?-1:1),lx=side*(arms?.32:.14),ly=(arms?1.10:.37)+(u.sit?-.2:0),lz=Math.sin(swing)*.23;
        terraEuler.set(swing,yaw,arms?-side*.08:0,'YXZ');terraQuat.setFromEuler(terraEuler);terraVec.set(u.x+(ca*lx+sa*lz)*s,y+ly*s,u.z+(-sa*lx+ca*lz)*s);terraScale.set(s,s*(arms?.86:1),s);terraMat.compose(terraVec,terraQuat,terraScale);G.terraLimbs.setMatrixAt(u.i*4+j,terraMat);
        if(arms){lz=Math.sin(swing)*.46;terraVec.set(u.x+(ca*lx+sa*lz)*s,y+(.78+(u.sit?-.2:0))*s,u.z+(-sa*lx+ca*lz)*s);terraScale.setScalar(s);terraMat.compose(terraVec,terraQuat,terraScale);G.terraHands.setMatrixAt(u.i*2+j-2,terraMat);}
      }
    }G.terraLimbs.instanceMatrix.needsUpdate=true;G.terraHands.instanceMatrix.needsUpdate=true;
  };
  function terraClearKeys(){for(var key in KEYS)KEYS[key]=false;terraMotion.held=false;if(G)G.drag=false;if(terraTouch){terraTouch.active=null;terraTouch.knob.style.transform='translate(0,0)';}}
  function terraPause(on){if(!G)return;G.paused=!!on;terraClearKeys();var el=document.getElementById('terra-pause');if(el)el.hidden=!G.paused;}
  function terraSetQuality(value){terraQuality=['auto','balanced','high'].includes(value)?value:'auto';var low=terraQuality==='balanced'||(terraQuality==='auto'&&terraMobile);R3.renderer.setPixelRatio(Math.min(devicePixelRatio||1,low?1:1.6));R3.renderer.shadowMap.enabled=!low;R3.renderer.setSize(innerWidth,innerHeight);GAME.quality=terraQuality;}
  function terraControls(){
    var css=document.createElement('style');css.textContent=`
      #c3d{touch-action:none}button{touch-action:manipulation}#hud{max-width:calc(100vw - 145px)}#hint{white-space:normal;text-align:center;width:max-content;max-width:90%}
      #terra-touch{position:fixed;inset:0;pointer-events:none;z-index:27;display:none}.terra-touch-active #terra-touch{display:block}
      #terra-stick{position:absolute;left:max(20px,env(safe-area-inset-left));bottom:max(27px,env(safe-area-inset-bottom));height:110px;width:110px;border:1px solid #e9e1c264;border-radius:50%;background:#17303c7a;pointer-events:auto;touch-action:none}
      #terra-stick:before{content:'MOVE';position:absolute;top:15px;left:0;right:0;text-align:center;font-size:8px;color:#eddfbd9c;letter-spacing:.14em}
      #terra-knob{width:44px;height:44px;position:absolute;top:32px;left:32px;border:1px solid #eedeba9c;background:#ddcba763;border-radius:50%;pointer-events:none}
      #terra-touch-actions{position:absolute;right:max(16px,env(safe-area-inset-right));bottom:max(25px,env(safe-area-inset-bottom));display:flex;gap:8px;align-items:center;pointer-events:auto}
      #terra-touch button,#terra-pause-button{background:#112932da;border:1px solid #d4c49870;color:#fff0d3;border-radius:6px;min-height:44px;padding:10px 13px;font-size:12px}
      #terra-touch-actions button:first-child{width:68px;height:68px;border-radius:50%;background:#d7bd83;color:#12232b;font-weight:650}
      #terra-pause-button{position:fixed;right:24px;top:70px;z-index:26;padding:5px 15px;min-height:35px;font-size:11px}
      #terra-pause{position:fixed;inset:0;z-index:39;background:#08171be8;backdrop-filter:blur(6px);display:grid;place-content:center;text-align:center;padding:24px}
      #terra-pause[hidden]{display:none}#terra-pause h2{font:38px Georgia}#terra-pause p{font-size:13px;color:#b5c7c4}#terra-resume{padding:14px 24px;background:#d7bd83;color:#10242a;border:0}
      .terra-touch-active #hint{bottom:157px;font-size:10px}.terra-touch-active #talk{bottom:199px}.terra-touch-active #hud{left:12px;top:12px;padding:12px}.terra-touch-active #hudPlace{font-size:21px}
      .terra-touch-active #hudLine,.terra-touch-active #hudTime{font-size:10px}.terra-touch-active #menuBtn{top:12px;right:12px}.terra-touch-active #terra-pause-button{top:59px;right:12px}
      .terra-touch-active #dlgBox{height:90vh;max-height:90vh}.terra-touch-active #dcard{width:36%;min-width:125px;padding:12px}.terra-touch-active .resident-mark{font-size:48px}.terra-touch-active #dmsgs{font-size:12px}.terra-touch-active #dtopics button{font-size:11px;padding:10px}
    @media(max-height:430px){.terra-touch-active #hint{display:none}.terra-touch-active #hud{padding:8px 12px}.terra-touch-active #hudPlace{font-size:18px}.terra-touch-active #talk{bottom:32px;max-width:40%;font-size:11px}}
    `;document.head.append(css);
    var div=document.createElement('div');div.id='terra-touch';div.innerHTML='<div id="terra-stick" role="button" tabindex="0" aria-label="Movement joystick"><div id="terra-knob"></div></div><div id="terra-touch-actions"><button id="terra-meet" aria-label="Meet nearby resident">Meet</button><button id="terra-map" aria-label="Toggle local map">Map</button></div>';document.body.append(div);
    document.body.classList.toggle('terra-touch-active',terraMobile);
    var pause=document.createElement('div');pause.id='terra-pause';pause.hidden=true;pause.innerHTML='<h2>A moment in time.</h2><p>The walk is paused. Nothing advances while you are away.</p><button id="terra-resume">Return to the world</button>';document.body.append(pause);
    var pb=document.createElement('button');pb.id='terra-pause-button';pb.textContent='Pause';document.body.append(pb);pb.onclick=()=>terraPause(true);document.getElementById('terra-resume').onclick=()=>{terraPause(false);EL.c3d.focus();};
    var stick=document.getElementById('terra-stick'),knob=document.getElementById('terra-knob');terraTouch={active:null,knob};
    function move(e){if(e.pointerId!==terraTouch.active)return;e.preventDefault();var r=stick.getBoundingClientRect(),x=(e.clientX-r.left-r.width/2)/35,y=(e.clientY-r.top-r.height/2)/35,m=Math.hypot(x,y);if(m>1){x/=m;y/=m;}KEYS.KeyW=y<-.22;KEYS.KeyS=y>.22;KEYS.KeyA=x<-.22;KEYS.KeyD=x>.22;knob.style.transform='translate('+(x*33)+'px,'+(y*33)+'px)';}
    stick.addEventListener('pointerdown',e=>{if(G.paused)return;terraTouch.active=e.pointerId;stick.setPointerCapture(e.pointerId);move(e);});stick.addEventListener('pointermove',move);for(var name of ['pointerup','pointercancel','lostpointercapture'])stick.addEventListener(name,()=>terraClearKeys());
    var look=null;EL.c3d.addEventListener('pointerdown',e=>{if(e.pointerType!=='touch'||G.dialog||G.paused)return;e.preventDefault();look={id:e.pointerId,x:e.clientX,y:e.clientY};EL.c3d.setPointerCapture(e.pointerId);});
    EL.c3d.addEventListener('pointermove',e=>{if(!look||look.id!==e.pointerId||G.paused||G.dialog)return;e.preventDefault();G.yaw-=(e.clientX-look.x)*.004;G.pitch=clamp(G.pitch-(e.clientY-look.y)*.004,-1.35,1.35);look={id:e.pointerId,x:e.clientX,y:e.clientY};});
    for(var name of ['pointerup','pointercancel'])EL.c3d.addEventListener(name,()=>look=null);
    document.getElementById('terra-meet').onclick=()=>{terraClearKeys();tryTalk();};document.getElementById('terra-map').onclick=()=>{G.mapOn=!G.mapOn;EL.map.style.display=G.mapOn?'block':'none';};
    // Pointer activation keeps touch buttons responsive after a captured camera gesture.
    var touchButton=null,lastTouchButton=null,lastTouchAt=0;
    document.addEventListener('pointerdown',e=>{if(e.pointerType!=='touch')return;var b=e.target.closest('button');touchButton=b?{button:b,id:e.pointerId,x:e.clientX,y:e.clientY}:null;},true);
    document.addEventListener('pointerup',e=>{if(e.pointerType!=='touch'||!touchButton||touchButton.id!==e.pointerId)return;var t=touchButton;touchButton=null;if(e.target.closest('button')!==t.button||Math.hypot(e.clientX-t.x,e.clientY-t.y)>14)return;lastTouchButton=t.button;lastTouchAt=performance.now();e.preventDefault();t.button.click();},true);
    document.addEventListener('pointercancel',()=>touchButton=null,true);
    document.addEventListener('click',e=>{if(e.isTrusted&&lastTouchButton&&e.detail!==0&&performance.now()-lastTouchAt<650){e.preventDefault();e.stopImmediatePropagation();}},true);
    window.addEventListener('blur',terraClearKeys);document.addEventListener('visibilitychange',()=>{if(document.hidden)terraPause(true);});
    document.addEventListener('keydown',e=>{if(e.code==='KeyP'&&!G.dialog)terraPause(!G.paused);});
    EL.hint.innerHTML=terraMobile?'Left circle to move · Drag the scene to look · Meet a nearby resident':'Drag to look · WASD to walk · E to meet · P to pause · M for map';
  }
  var terraLoop=loop;
  loop=function(ts){if(G?.paused){_lastT=ts;requestAnimationFrame(loop);return;}terraLoop(ts);if(G?.terraCloths)for(var m of G.terraCloths){var p=m.geometry.attributes.position;for(var i=0;i<p.count;i++){var x=p.getX(i),y=p.getY(i);p.setZ(i,Math.sin(x*2.5+G.el*1.2+y*.6)*.15*(x/1.9));}p.needsUpdate=true;}};
  var terraBuild=buildWorld;
  buildWorld=function(){terraBuild();G.paused=false;terraControls();terraSetQuality('auto');
    // Begin beside the center, not a several-minute walk outside the gate.
    var plaza=S.pois.plaza||[0,0];var safe=pushOut(plaza[0]+12,plaza[1]+22,.6);GAME.teleport(safe[0],safe[1],Math.atan2(safe[0]-plaza[0],safe[1]-plaza[1]));G.pitch=-.055;
  };
  var terraOpen=openDialog,terraClose=closeDialog;
  openDialog=function(u){terraClearKeys();terraOpen(u);};closeDialog=function(){terraClearKeys();terraClose();};GAME.closeDialog=closeDialog;
  var terraInspect=GAME.inspect;
  GAME.inspect=function(){return {...(terraInspect?.()||{}),version:'0.3.0',mobile:terraMobile,paused:!!G?.paused,quality:GAME.quality,canopyTrees:GAME.canopyTrees,streetProps:GAME.streetProps,articulatedResidents:G?.units?.length||0,yaw:G?.yaw,pitch:G?.pitch};};
  GAME.pause=terraPause;GAME.qualityPreset=terraSetQuality;
  window.addEventListener('message',function(e){if(e.source!==parent||!G||!e.data)return;var d=e.data;if(d.type==='terra:quality')terraSetQuality(d.value);if(d.type==='terra:pause')terraPause(d.value);if(d.type==='terra:touch'){terraMobile=!!d.value;document.body.classList.toggle('terra-touch-active',terraMobile);}});
}
