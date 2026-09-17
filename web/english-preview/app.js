/* Terra World English Preview. No analytics, login, API-key storage or model calls. */
(() => {
'use strict';
const E=TerraEnglish,$=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fold=s=>String(s??'').normalize('NFD').replace(/\p{M}/gu,'').toLowerCase();
const BASE='https://d2ol7oe51mr4n9.cloudfront.net/user_3G1EoKpPdtVgILUsyI2EdcfEGyE/';
const SOURCE={walk:{file:'038b2f5a-79fd-4222-a148-e1ae1a1ebf46.html',sha:'29b4e734b064f5ea2b6dc3c6f7bdc5336247182d12c1a2e1fc6b6af37d171332'},planet:{file:'f7e044a1-6fb4-41c3-8142-04490cbf3b54.html',sha:'3f816f25d4bd1eecb7f4b6ade9e4b04d57747673b293d1c4626b09b7da915bff'},people:{file:'e51caab7-635a-4fa1-9414-150ad5faade1.html',sha:'3cce30af2d2e8fb7f279815ce4a44755adadddb938cc2aa63ceb8b3991fbae2b'}};
const ARTBASE='https://d8j0ntlcm91z4.cloudfront.net/user_3G1EoKpPdtVgILUsyI2EdcfEGyE/';
const ART={capital:ARTBASE+'hf_20260917_101154_e0ba14c9-8980-4ce9-a43c-b768bc7d9cb9.png',Ta:ARTBASE+'hf_20260917_101610_e104c084-3f7f-4f4f-89fe-2d9c45ee7822.png',Imif:ARTBASE+'hf_20260917_101716_3e5a1e14-1a95-4a23-a429-49369e7e08d2.png',Sithriru:ARTBASE+'hf_20260917_101002_dca1b8aa-b56c-4457-9196-398697dd2bea.png',Ana:ARTBASE+'hf_20260917_102519_bfc80db8-e418-4a28-af56-13290a20e23c.png',bronze:ARTBASE+'hf_20260917_103256_38abd2d8-a564-46ef-aa15-214177877894.png',neolithic:ARTBASE+'hf_20260917_103540_8e97070d-2146-42f6-a4b3-2f3732bea596.png'};
const SCENES=[{name:'Níhmīwū',id:'capital',year:500,era:'The river metropolis',polity:'Šène',description:'Through the gates of a river city. Stone walls, market awnings and the work of a vast agrarian society.'},{name:'Rikã̀žàval',id:'bronze',year:-1500,era:'At the forest\'s edge',polity:'Kuk',description:'A tropical river meets the coast. Workshops, courtyards and gardens gather around the water.'},{name:'Zirpuw',id:'neolithic',year:-6000,era:'Where a community begins',polity:'Sumadoto',description:'Reed roofs, gathered grain and a river through semiarid land. A small place in a much larger history.'}];
const FEATURED=[{n:'Ží',pn:'Xɔsɛ̀wé',b:434},{n:'Súflā́nā́',pn:'Mapos'},{n:'Tā',pn:'Kakluŋlasdul',art:'Ta'},{n:'Šī̀yããru',pn:'Šène'},{n:'Kú',pn:'Limraknoublaltan'},{n:'Imíf',pn:'Mulatuananpa',art:'Imif'},{n:'Šiþrìru',pn:'Layolus',art:'Sithriru'},{n:'Ana',pn:'Gatakanuk',art:'Ana'}];
let archive,walkData,portraits={},translatedEvents=[],people=[],preparedPlay,worldView,frameIndex=116,activeView='home',routeToken=0,eventLimit=80,peopleLimit=72,timelineTimer=null;
const pending=new Map(),verified=new Set(),errors=[];
const scripts=s=>[...s.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(x=>x[1]);
const assigned=s=>JSON.parse(s.slice(s.indexOf('=')+1).trim().replace(/;$/,''));
const unbase=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
function status(text){$('status').textContent=text;$('status').classList.toggle('hidden',!text);}
function fail(error){const text=error?.message||String(error);errors.push(text);$('error-message').textContent=text+' Your original world has not been modified.';$('error-box').classList.remove('hidden');status('');}
async function source(name){
 if(!pending.has(name))pending.set(name,(async()=>{const cfg=SOURCE[name];const r=await fetch(BASE+cfg.file,{signal:AbortSignal.timeout(60000),credentials:'omit'});if(!r.ok)throw Error(`Original ${name} archive returned HTTP ${r.status}.`);const bytes=await r.arrayBuffer();if(!crypto.subtle)throw Error('This browser cannot verify the source. Open the preview in current Chrome, Edge or Firefox.');const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');if(hash!==cfg.sha)throw Error(`The original ${name} file has changed. Its code was not executed.`);verified.add(name);return new TextDecoder().decode(bytes);})().catch(e=>{pending.delete(name);throw e;}));
 return pending.get(name);
}
async function loadWalk(){if(walkData)return walkData;const html=await source('walk');const ss=scripts(html);if(ss.length!==3)throw Error('Unexpected walk source format.');walkData={html,play:assigned(ss[1]),three:ss[0]};return walkData;}
let archivePromise;
async function loadArchive(){
 if(archive)return archive;if(archivePromise)return archivePromise;
 archivePromise=(async()=>{const html=await source('planet'),ss=scripts(html);if(ss.length!==4)throw Error('Unexpected planet source format.');const t=assigned(ss[1]),gz=unbase(assigned(ss[2]));if(typeof DecompressionStream==='undefined')throw Error('A newer browser with gzip decompression is needed.');const text=await new Response(new Blob([gz]).stream().pipeThrough(new DecompressionStream('gzip'))).text(),d=JSON.parse(text);
 if(d.frames.length!==117||d.events.length!==14000||d.people.length!==5060)throw Error('Archive record counts do not match this preview.');
 archive={t,d,three:ss[0]};frameIndex=d.frames.length-1;
 translatedEvents=d.events.map((e,i)=>({...e,text:E.tr(e.t),index:i})).sort((a,b)=>b.yr-a.yr||b.w-a.w);
 people=d.people.map((p,i)=>({...p,index:i,era:E.tr(p.e),deeds:(p.ds||[]).map(ds=>[ds[0],ds[1],E.tr(ds[2])])}));
 window.TERRA_PREVIEW.counts={frames:d.frames.length,events:d.events.length,people:d.people.length};return archive;
 })().catch(e=>{archivePromise=null;throw e;});return archivePromise;
}
async function loadPortraits(){
 if(Object.keys(portraits).length)return portraits;const doc=new DOMParser().parseFromString(await source('people'),'text/html');
 for(const card of doc.querySelectorAll('article.card')){const n=card.querySelector('h2')?.textContent?.trim(),img=card.querySelector('img')?.getAttribute('src');if(n&&img&&/^data:image\/(jpeg|png|webp);base64,/.test(img))portraits[fold(n)]=img;}
 for(const f of FEATURED)if(f.art&&ART[f.art])portraits[fold(f.n)]=ART[f.art];return portraits;
}
async function preparePlay(){
 if(preparedPlay)return preparedPlay;const [w,a]=await Promise.all([loadWalk(),loadArchive()]);
 const result=structuredClone(w.play),report=[];
 result.scenes.forEach((s,i)=>{const before=s.npcs.length; s.npcs=s.npcs.filter(n=>!n.real||a.d.people.some(p=>p.p===s.pid&&p.n===n.name&&p.b<=s.year&&p.d!==null&&p.d>=s.year));
 report.push({name:s.name,originalResidents:before,residents:s.npcs.length,excludedArchivedPeople:before-s.npcs.length});
 for(const field of ['form_ru','mode_ru','era','tier','biome_ru'])s[field]=E.tr(s[field]);
 s.title=SCENES[i].era;s.year_ru=E.year(s.year);s.pop_ru=E.number(s.pop);s.polity_pop_ru=E.number(s.polity_pop);
 s.desc=`${s.name} is a ${s.tier} of ${E.number(s.pop)} people in the ${s.form_ru} of ${s.polity}. Its society practices ${s.mode_ru}. This scene represents ${E.year(s.year)} in Terra's fictional chronology. The displayed residents and architecture are reconstructions.`;
 s.npcs=s.npcs.map(n=>({...n,role_ru:E.tr(n.role_ru),traits:n.traits.map(t=>[E.tr(t[0]),t[1]]),beliefs:n.beliefs.map(t=>[E.tr(t[0]),t[1]]),deeds:n.deeds.filter(d=>d.y<=s.year).map(d=>({...d,t:E.tr(d.t)}))}));
 s.events=(s.events||[]).filter(e=>e.y<=s.year).map(e=>({...e,t:E.tr(e.t)}));
 });preparedPlay=result;window.TERRA_PREVIEW.chronology=report;return result;
}
function home(){
 $('hero-art').src=ART.capital;
 $('destinations').innerHTML=SCENES.map((s,i)=>`<article class="destination"><button class="destination-image" data-walk="${i}" aria-label="Enter ${esc(s.name)}"><img src="${esc(ART[s.id]||ART.capital)}" alt="Illustrated interpretation of ${esc(s.name)}" loading="lazy"><span class="destination-index">0${i+1}</span><span class="destination-date">${E.year(s.year)}</span></button><div class="eyebrow">${esc(s.era)}</div><h3>${esc(s.name)}</h3><p class="description">${esc(s.description)}</p><button class="destination-link" data-walk="${i}">Walk this place <span>↗</span></button></article>`).join('');
 $('walk-scene').innerHTML=SCENES.map((s,i)=>`<option value="${i}">${esc(s.name)} · ${E.year(s.year)}</option>`).join('');
}
function ensureThree(bundle){if(window.THREE)return;const s=document.createElement('script');s.textContent=bundle;document.head.append(s);s.remove();if(!window.THREE)throw Error('The verified 3D library did not initialize.');}
function dataImage(base64){return base64.startsWith('data:')?base64:'data:image/png;base64,'+base64;}
function image(src){return new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(Error('An archived terrain image could not be decoded.'));i.src=src;});}
function owners(frame){const bytes=unbase(frame.cm),view=new DataView(bytes.buffer);if(bytes.length!==180*90*2)throw Error('Unexpected political map dimensions.');return Array.from({length:180*90},(_,i)=>view.getInt16(i*2,true));}
async function createWorldView(){
 const {t,d,three}=await loadArchive();ensureThree(three);
 const natural=await image(dataImage(t.tex.nat)),normal=await image(dataImage(t.tex.nrm));
 const textureCanvas=document.createElement('canvas');textureCanvas.width=t.tex.tw;textureCanvas.height=t.tex.th;
 const ctx=textureCanvas.getContext('2d'),small=document.createElement('canvas');small.width=t.world.w;small.height=t.world.h;const sx=small.getContext('2d');
 const flat=$('flat-map'),flatCtx=flat.getContext('2d');let mode='sphere',ownership=[],pols=new Map(),sphere,renderer,scene,camera,planet,drag=null,moved=false,angleY=-2.65,angleX=.12,zoom=3.05,raf;
 const texture=new THREE.CanvasTexture(textureCanvas);texture.colorSpace=THREE.SRGBColorSpace;
 function flatPaint(){const rect=$('planet-stage').getBoundingClientRect(),scale=Math.min(devicePixelRatio||1,1.6);flat.width=Math.max(1,Math.round(rect.width*scale));flat.height=Math.max(1,Math.round(rect.height*scale));flatCtx.fillStyle='#091923';flatCtx.fillRect(0,0,flat.width,flat.height);const f=Math.min(flat.width/textureCanvas.width,flat.height/textureCanvas.height);const w=textureCanvas.width*f,h=textureCanvas.height*f;flatCtx.drawImage(textureCanvas,(flat.width-w)/2,(flat.height-h)/2,w,h);}
 function resize(){const r=$('planet-stage').getBoundingClientRect();if(r.width<1||r.height<1)return;if(renderer){renderer.setSize(r.width,r.height,false);camera.aspect=r.width/r.height;camera.updateProjectionMatrix();}flatPaint();}
 function draw(){cancelAnimationFrame(raf);if(activeView!=='atlas')return;if(renderer&&mode==='sphere'){planet.rotation.set(angleX,angleY,0);camera.position.z=zoom;renderer.render(scene,camera);}raf=requestAnimationFrame(draw);}
 function projection(value){mode=value;$('globe').classList.toggle('hidden',value!=='sphere');flat.classList.toggle('hidden',value!=='flat');$('sphere-mode').classList.toggle('selected',value==='sphere');$('flat-mode').classList.toggle('selected',value==='flat');resize();draw();}
 try{
  renderer=new THREE.WebGLRenderer({canvas:$('globe'),antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.6));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.2;
  scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(40,1,.05,100);camera.position.z=zoom;
  const normalMap=new THREE.Texture(normal);normalMap.needsUpdate=true;
  sphere=new THREE.Mesh(new THREE.SphereGeometry(1,160,100),new THREE.MeshStandardMaterial({map:texture,normalMap,normalScale:new THREE.Vector2(.45,.45),roughness:.85}));
  planet=new THREE.Group();planet.add(sphere);scene.add(planet);
  const atmosphere=new THREE.Mesh(new THREE.SphereGeometry(1.032,64,40),new THREE.ShaderMaterial({transparent:true,side:THREE.BackSide,depthWrite:false,uniforms:{},vertexShader:'varying vec3 n; varying vec3 v; void main(){vec4 p=modelViewMatrix*vec4(position,1.); n=normalize(normalMatrix*normal);v=normalize(-p.xyz);gl_Position=projectionMatrix*p;}',fragmentShader:'varying vec3 n; varying vec3 v; void main(){float a=pow(1.-abs(dot(normalize(n),normalize(v))),3.);gl_FragColor=vec4(.19,.54,.67,a*.44);}'}));planet.add(atmosphere);
  scene.add(new THREE.HemisphereLight('#dcecff','#233a43',2.1));const sun=new THREE.DirectionalLight('#ffe4b5',3.1);sun.position.set(-3,3,5);scene.add(sun);
  const c=$('globe');c.style.touchAction='none';c.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY};moved=false;c.setPointerCapture(e.pointerId);});c.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>2)moved=true;angleY+=dx*.006;angleX=Math.max(-1.2,Math.min(1.2,angleX+dy*.006));drag={x:e.clientX,y:e.clientY};});c.addEventListener('pointerup',e=>{if(!moved){const r=c.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);const hit=ray.intersectObject(sphere)[0];if(hit?.uv)pickCell(Math.floor(hit.uv.x*180),Math.floor((1-hit.uv.y)*90));}drag=null;});c.addEventListener('pointercancel',()=>drag=null);c.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.min(5.3,Math.max(1.55,zoom+e.deltaY*.002));},{passive:false});
 }catch(error){console.warn('Globe unavailable; using the flat map.',error);$('sphere-mode').disabled=true;mode='flat';}
 flat.addEventListener('click',e=>{const r=flat.getBoundingClientRect(),f=Math.min(r.width/textureCanvas.width,r.height/textureCanvas.height),w=textureCanvas.width*f,h=textureCanvas.height*f;const x=(e.clientX-r.left-(r.width-w)/2)/w,y=(e.clientY-r.top-(r.height-h)/2)/h;if(x>=0&&x<1&&y>=0&&y<1)pickCell(Math.floor(x*180),Math.floor(y*90));});
 function pickCell(x,y){x=Math.max(0,Math.min(179,x));y=Math.max(0,Math.min(89,y));const p=pols.get(ownership[y*180+x]);if(p){$('polity-select').value=p.id;showPolity(p.id);}else{const biome=unbase(t.world.biome)[y*180+x];$('place-detail').innerHTML=`<div class="compass-mark">✧</div><h2>${esc(E.tr(t.dict.biomeNames[biome]||'Unclassified terrain'))}</h2><p>Grid cell ${x}, ${y}. No polity record is listed for this cell in the selected snapshot.</p>`;$('polity-select').value='';}}
 function update(){const f=d.frames[frameIndex];ownership=owners(f);pols=new Map(f.pol.map(p=>[p.id,p]));ctx.clearRect(0,0,textureCanvas.width,textureCanvas.height);ctx.drawImage(natural,0,0,textureCanvas.width,textureCanvas.height);
  if($('political-toggle').checked){const im=sx.createImageData(180,90);for(let i=0;i<ownership.length;i++){const p=pols.get(ownership[i]);if(!p)continue;const hex=p.c.slice(1);im.data[i*4]=parseInt(hex.slice(0,2),16);im.data[i*4+1]=parseInt(hex.slice(2,4),16);im.data[i*4+2]=parseInt(hex.slice(4,6),16);im.data[i*4+3]=110;}sx.putImageData(im,0,0);ctx.imageSmoothingEnabled=true;ctx.drawImage(small,0,0,textureCanvas.width,textureCanvas.height);}
  texture.needsUpdate=true;flatPaint();const selected=$('polity-select').value;$('polity-select').innerHTML='<option value="">Select a polity…</option>'+f.pol.slice().sort((a,b)=>a.n.localeCompare(b.n)).map(p=>`<option value="${p.id}">${esc(p.n)}</option>`).join('');if(pols.has(Number(selected))){$('polity-select').value=selected;showPolity(Number(selected));}else $('place-detail').innerHTML='<div class="compass-mark">✧</div><h2>A world of places.</h2><p>Select a territory or choose a polity above.</p>';
  $('map-summary').textContent=`${f.pol.length} listed polities · ${f.set.length} settlements`;
  const row=d.timeline.find(r=>r.yr===f.year);$('world-year').textContent=E.year(f.year);$('world-time').value=frameIndex;$('snapshot-info').innerHTML=`<b>${frameIndex+1} / ${d.frames.length}</b><span>archived snapshots</span><b>${E.short(row?.pop??t.head.pop_end)}</b><span>aggregate population</span>`;
 }
 function showPolity(id){const p=pols.get(Number(id));if(!p)return;$('place-detail').innerHTML=`<span class="chip" style="border-color:${esc(p.c)}">${esc(E.forms[p.f]||p.f)}</span><h2>${esc(p.n)}</h2><p>${esc(E.tr(p.e))} · ${E.year(d.frames[frameIndex].year)}</p><div class="detail-stats"><div><span>Population</span><b>${E.number(p.p)}</b></div><div><span>Capital</span><b>${esc(p.cap||'Not listed')}</b></div><div><span>Livelihood</span><b>${esc(E.modes[p.m]||p.m)}</b></div><div><span>Known technologies</span><b>${p.t}</b></div></div><h3>Recorded divinities</h3><p>${esc((p.g||[]).join(', ')||'None listed')}</p><p class="quiet-note">Model quantities, not facts about a real-world society.</p>`;}
 new ResizeObserver(resize).observe($('planet-stage'));$('map-empty').classList.add('hidden');$('polity-select').onchange=()=>showPolity($('polity-select').value);
 projection(mode);update();return {update,projection,draw,stop:()=>cancelAnimationFrame(raf),showPolity,inspect:()=>({mode,ownership:ownership.length,polities:pols.size,renderer:!!renderer,frame:frameIndex})};
}
function setFrame(index){if(!archive)return;frameIndex=Math.max(0,Math.min(archive.d.frames.length-1,Math.round(index)));worldView?.update();if(activeView==='chronicle'&&$('event-time-filter').checked)renderEvents();}
function renderEvents(){
 const term=fold($('event-search').value),kind=$('event-kind').value,year=archive.d.frames[frameIndex].year;
 const filtered=translatedEvents.filter(e=>(!kind||e.k===kind)&&(!$('event-time-filter').checked||e.yr<=year)&&(!term||fold(e.text+' '+(E.kinds[e.k]||e.k)).includes(term)));
 $('event-count').textContent=`${E.number(filtered.length)} records`;
 $('event-list').innerHTML=filtered.slice(0,eventLimit).map(e=>`<article class="event-row"><div class="event-year">${E.year(e.yr)}</div><div class="event-kind"><i class="event-dot" style="background:${esc(archive.t.dict.kindColors[e.k]||'#bda572')}"></i>${esc(E.kinds[e.k]||e.k)}</div><div class="event-text">${esc(e.text)}</div></article>`).join('')||'<div class="empty-state">No records match this search.</div>';
 $('events-more').classList.toggle('hidden',filtered.length<=eventLimit);
}
function featuredPerson(f){return people.find(p=>fold(p.n)===fold(f.n)&&fold(p.pn)===fold(f.pn)&&(f.b===undefined||p.b===f.b))||null;}
function renderPortraits(){
 $('portrait-grid').innerHTML=FEATURED.map(f=>{const p=featuredPerson(f),src=portraits[fold(f.n)];return `<button class="portrait-card" ${p?'data-person="'+p.index+'"':'disabled'}><div class="portrait-image">${src?`<img loading="lazy" src="${esc(src)}" alt="Illustrated portrait of ${esc(f.n)}">`:`<span class="initial">${esc(f.n[0])}</span>`}<span class="portrait-era">${esc(p?.era||'Archive')}</span></div><div class="portrait-meta"><h3>${esc(f.n)}</h3><span>${esc(f.pn)} · ${esc(p?.r==='chief'?'leader':p?.r||'Historical figure')}</span><p>${p?E.year(p.b)+' to '+E.year(p.d):'Biography unavailable in this export'}</p></div></button>`;}).join('');
}
function renderPeople(){const term=fold($('people-search').value),filtered=people.filter(p=>!term||fold(`${p.n} ${p.pn} ${p.r} ${p.era}`).includes(term));$('people-count').textContent=`${E.number(filtered.length)} notable-person records. Most records have no illustrated portrait.`;
 $('people-list').innerHTML=filtered.slice(0,peopleLimit).map(p=>`<button class="person-row" data-person="${p.index}"><span class="initial">${esc(p.n[0])}</span><span><span class="person-name">${esc(p.n)}</span><span class="person-sub">${esc(p.pn)} · ${esc(p.r==='chief'?'leader':p.r)}</span></span><span class="person-sub">${E.year(p.b)}</span><span>↗</span></button>`).join('')||'<div class="empty-state">No people match this search.</div>';$('people-more').classList.toggle('hidden',filtered.length<=peopleLimit);
}
function openPerson(index){const p=people.find(p=>p.index===Number(index));if(!p)return;const f=FEATURED.find(f=>fold(f.n)===fold(p.n)&&fold(f.pn)===fold(p.pn)&&(f.b===undefined||p.b===f.b)),src=f?portraits[fold(f.n)]:null;const traitNames={risk:'Risk-taking',conformity:'Conformity',diligence:'Diligence'},beliefNames={trust:'Our own people can be trusted',elsewhere:'Life is better elsewhere',danger:'Outsiders are dangerous',novelty:'New ideas can work',authority:'Authority is legitimate',divine:'Higher powers govern the world',scarcity:'Food may run short'};
 $('person-detail').innerHTML=`<div class="bio-layout"><div>${src?`<img class="bio-portrait" src="${esc(src)}" alt="Illustrated interpretation of ${esc(p.n)}">`:`<div class="bio-no-portrait">${esc(p.n[0])}</div>`}<p class="art-note">${src?'An artistic interpretation, not a photograph or a verified reconstruction of appearance.':'No portrait has been created for this record.'}</p></div><div class="bio-content"><div class="eyebrow">A LIFE IN THE ARCHIVE</div><h2>${esc(p.n)}</h2><p class="bio-meta">${esc(p.pn)} · ${esc(p.r==='chief'?'leader':p.r)} · ${esc(p.era)}</p><p>${E.year(p.b)} to ${E.year(p.d)} · Recorded age ${p.a}</p><h3>Recorded deeds</h3>${p.deeds.map(ds=>`<div class="deed"><span>${E.year(ds[0])}</span><p>${esc(ds[2])}</p></div>`).join('')||'<p>No individual deeds were included in this export.</p>'}<h3>Disposition in the model</h3><p>${(p.tr||[]).map(t=>esc(traitNames[t[0]]||t[0])+': '+Math.round(t[1]*100)+'%').join(' · ')}</p><h3>Recorded beliefs</h3><p>${(p.bl||[]).map(b=>esc(beliefNames[b[0]]||b[0])).join('<br>')}</p><p class="quiet-note">These are fictional simulation parameters, not psychological measurements. The archive may record a historical person outside the year of a walkable scene.</p></div></div>`;$('person-dialog').showModal();
}
async function startWalk(index,token){
 $('walk-loading').classList.remove('hidden');$('walk-progress').textContent='Loading the published world and checking its chronology.';$('walk-scene').value=index;
 const [w,play]=await Promise.all([loadWalk(),preparePlay()]);if(token!==routeToken)return;
 $('walk-progress').textContent='Building the settlement, materials and reconstructed residents.';
 const frame=$('walk-frame');frame.srcdoc=buildTerraWalkHTML(w.html,play,index);const start=performance.now();
 await new Promise((resolve,reject)=>{const timer=setInterval(()=>{if(token!==routeToken){clearInterval(timer);resolve();return;}try{const game=frame.contentWindow?.GAME;if(game?.ready){clearInterval(timer);if(game.errors?.length){reject(Error(game.errors.join('; ')));return;}$('walk-loading').classList.add('hidden');frame.contentWindow.focus();resolve();}else if(performance.now()-start>60000){clearInterval(timer);reject(Error('The settlement took too long to initialize. Reload or try another browser.'));}}catch(e){clearInterval(timer);reject(e);}},150);});
}
async function route(){
 const token=++routeToken,raw=location.hash.slice(1)||'home',parts=raw.split('/'),name=['home','atlas','chronicle','people','about','walk'].includes(parts[0])?parts[0]:'home';
 if(activeView==='walk'){try{$('walk-frame').contentWindow?.postMessage({type:'terra:stop'},'*');}catch{}$('walk-frame').srcdoc='';}
 activeView=name;worldView?.stop();clearInterval(timelineTimer);timelineTimer=null;$('time-play').textContent='▶';$('error-box').classList.add('hidden');
 document.querySelectorAll('.view').forEach(v=>v.classList.toggle('hidden',v.id!=='view-'+name));document.querySelectorAll('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===(name==='walk'?'home':name)));
 document.title='TERRA · '+({home:'A world with a past',atlas:'World atlas',chronicle:'The chronicle',people:'Faces in the archive',about:'About the world',walk:'Walk the world'}[name]);window.scrollTo(0,0);
 try{
  if(name==='home'||name==='about'){status('');return;}status(name==='walk'?'Opening the settlement…':'Loading the original world archive…');
  if(name==='walk'){await startWalk(Math.max(0,Math.min(2,Number(parts[1])||0)),token);}
  else if(name==='atlas'){await loadArchive();if(token!==routeToken)return;if(!worldView)worldView=await createWorldView();if(token!==routeToken){worldView.stop();return;}worldView.draw();}
  else if(name==='chronicle'){await loadArchive();if(token!==routeToken)return;if($('event-kind').options.length===1)$('event-kind').innerHTML+=[...new Set(translatedEvents.map(e=>e.k))].map(k=>`<option value="${esc(k)}">${esc(E.kinds[k]||k)}</option>`).join('');renderEvents();}
  else if(name==='people'){await Promise.all([loadArchive(),loadPortraits()]);if(token!==routeToken)return;renderPortraits();renderPeople();}
  if(token===routeToken)status('');
 }catch(e){if(token===routeToken)fail(e);}
}
function sendWalk(data){$('walk-frame').contentWindow?.postMessage(data,'*');}
window.TERRA_PREVIEW={version:'0.2.0',counts:null,chronology:null,inspect:()=>({view:activeView,sourceVerified:[...verified],errors:[...errors],untranslated:[...E.unresolved],world:worldView?.inspect()||null,portraits:Object.keys(portraits).length}),loadArchive,preparePlay,setFrame};
document.addEventListener('click',e=>{const walk=e.target.closest('[data-walk]');if(walk){location.hash='walk/'+walk.dataset.walk;return;}const p=e.target.closest('[data-person]');if(p)openPerson(p.dataset.person);const site=e.target.closest('[data-site]');if(site)sendWalk({type:'terra:site',site:site.dataset.site});});
window.addEventListener('hashchange',route);window.addEventListener('message',e=>{if(e.source===$('walk-frame').contentWindow&&e.data?.type==='terra-exit')location.hash='home';});
$('retry').onclick=route;$('close-person').onclick=()=>$('person-dialog').close();$('person-dialog').addEventListener('click',e=>{if(e.target===$('person-dialog'))$('person-dialog').close();});
$('event-search').oninput=$('event-kind').onchange=$('event-time-filter').onchange=()=>{eventLimit=80;if(archive)renderEvents();};$('events-more').onclick=()=>{eventLimit+=100;renderEvents();};
$('people-search').oninput=()=>{peopleLimit=72;if(archive)renderPeople();};$('people-more').onclick=()=>{peopleLimit+=100;renderPeople();};
$('world-time').oninput=e=>setFrame(Number(e.target.value));$('time-prev').onclick=()=>setFrame(frameIndex-1);$('time-next').onclick=()=>setFrame(frameIndex+1);$('time-play').onclick=()=>{if(!archive)return;if(timelineTimer){clearInterval(timelineTimer);timelineTimer=null;$('time-play').textContent='▶';}else{if(frameIndex===archive.d.frames.length-1)setFrame(0);$('time-play').textContent='Ⅱ';timelineTimer=setInterval(()=>{if(frameIndex>=archive.d.frames.length-1){clearInterval(timelineTimer);timelineTimer=null;$('time-play').textContent='▶';}else setFrame(frameIndex+1);},1000);}};
$('sphere-mode').onclick=()=>worldView?.projection('sphere');$('flat-mode').onclick=()=>worldView?.projection('flat');$('political-toggle').onchange=()=>worldView?.update();
$('walk-scene').onchange=e=>location.hash='walk/'+e.target.value;$('walk-light').onchange=e=>sendWalk({type:'terra:time',value:Number(e.target.value)});$('walk-fullscreen').onclick=()=>{$('walk-frame').requestFullscreen?.().catch(fail);};
home();route();
})();
