import * as THREE from 'three';
import {distance,occludes} from './district-math.js';
export function createResidentUI(sim,camera,getPlayer,pause,isPaused){
  const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const button=document.createElement('button');button.id='interact';button.hidden=true;document.body.append(button);
  const roomLabel=document.createElement('div');roomLabel.id='room-label';document.body.append(roomLabel);
  const notice=document.createElement('div');notice.id='interaction-notice';notice.hidden=true;document.body.append(notice);
  const dialog=document.createElement('dialog');dialog.id='resident-dialog';dialog.innerHTML='<button id="resident-close" aria-label="Close conversation">×</button><div id="resident-content"></div>';document.body.append(dialog);
  const bubbles=sim.agents.map(a=>{const e=document.createElement('div');e.className='resident-speech';e.hidden=true;document.body.append(e);return {a,e};});
  let current=null,last=0,until=0,wasPaused=false;
  function choose(){
    const p=getPlayer(),found=[];
    for(const d of sim.area.doors)if(distance(p,d)<2.5&&!sim.area.solids.some(c=>occludes(c,{...p,y:1.05},{...d,y:1.05})))found.push({kind:'door',item:d,distance:distance(p,d),label:(d.target>.1?'Close ':'Open ')+d.name+' door'});
    for(const o of sim.area.objects)if(distance(p,o)<2.25&&sim.nav.sight({...p,y:1.45},{...o,y:1.12}))found.push({kind:'object',item:o,distance:distance(p,o),label:(o.kind==='storage'?(o.target>.1?'Close ':'Open '):'Use ')+o.name});
    for(const a of sim.agents)if(distance(p,a)<2.65&&sim.nav.sight({...p,y:1.55},a))found.push({kind:'resident',item:a,distance:distance(p,a),label:'Talk to '+a.name});
    found.sort((a,b)=>a.distance-b.distance);return found[0]||null;
  }
  function message(text){notice.textContent=text;notice.hidden=false;until=performance.now()+2600;}
  function conversation(agent){
    const data=sim.talk(agent);if(!data)return false;
    wasPaused=isPaused();pause(true);
    $('resident-content').innerHTML='<div class="eyebrow">RECONSTRUCTED RESIDENT</div><h2>'+esc(data.name)+'</h2><p>'+esc(data.role)+' · Age '+data.age+'</p><p id="resident-answer">I am '+esc(data.name)+'. My home is '+esc(data.home)+'.</p><div class="resident-topics"><button data-topic="work">What are you doing?</button><button data-topic="seen">What have you seen?</button><button data-topic="home">Your home</button></div><p class="resident-note">'+esc(data.note)+'</p>';
    $('resident-content').onclick=e=>{const b=e.target.closest('[data-topic]');if(!b)return;const answer=b.dataset.topic==='seen'?(data.memories.join(' ')||'I have not yet witnessed another local action.'):b.dataset.topic==='home'?'I use '+data.home+'. You may enter through its doorway.':'My current activity is '+data.state+'. I move between home, work and meeting places.';$('resident-answer').textContent=answer;};
    dialog.showModal();return true;
  }
  function interact(){if(isPaused())return false;current=choose();if(!current){message('Move closer to a visible person, door or work surface.');return false;}
    if(current.kind==='door'){const r=sim.doorRequest(current.item,sim.player,current.item.target<.1);message(r.ok?(r.open?'The door opens.':'The door closes.'):r.reason);return r.ok;}
    if(current.kind==='object'){message(sim.interactObject(current.item));return true;}
    return conversation(current.item);
  }
  button.onclick=interact;$('resident-close').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>pause(wasPaused));
  document.addEventListener('keydown',e=>{if(e.code==='KeyE'&&!dialog.open){e.preventDefault();interact();}});
  function update(){
    const now=performance.now();if(now-last<120)return;last=now;
    const player=getPlayer();current=choose();button.hidden=!current||isPaused();if(current)button.textContent='E · '+current.label;
    const room=sim.area.roomAt(player);roomLabel.textContent=room?room.name+' · Interior':sim.area.config.name+' · Outdoors';
    if(now>until)notice.hidden=true;
    for(const {a,e}of bubbles){
      const visible=a.speechUntil>sim.time&&distance(a,player)<8&&sim.nav.sight({...player,y:1.65},a);
      const p=new THREE.Vector3(a.x,1.95,a.z).project(camera);e.hidden=!visible||p.z>1||Math.abs(p.x)>1||Math.abs(p.y)>1;
      if(!e.hidden){e.textContent=a.name+': '+a.speech;e.style.left=(p.x*.5+.5)*innerWidth+'px';e.style.top=(-p.y*.5+.5)*innerHeight+'px';}
    }
  }
  return {update,interact,inspect:()=>({target:current?{kind:current.kind,id:current.item.id,label:current.label}:null,dialogOpen:dialog.open})};
}
