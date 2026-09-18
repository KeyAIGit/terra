import {DISTRICTS} from './district-config.js';
export function setupDistrictInterface(config,go,pause){
  const $=id=>document.getElementById(id);
  document.title='Terra World · '+config.name;
  $('hud').querySelector('.wordmark span').textContent=config.name+' · '+config.date;
  $('hud').querySelector('h1').textContent=config.title;
  $('hud').querySelector('p').textContent='Enter homes, meet residents and observe local life.';
  $('loading-title').textContent='Entering '+config.name;
  $('loading').querySelector('.eyebrow').textContent=config.name+' · '+config.date;
  const select=document.createElement('select');
  select.id='district-select';select.setAttribute('aria-label','Choose a district');
  for(const d of Object.values(DISTRICTS)){
    const option=document.createElement('option');option.value=d.id;
    option.textContent=d.name+' · '+d.date;select.append(option);
  }
  select.value=config.id;$('controls').prepend(select);select.onchange=()=>go(select.value);
  const names=['District entrance','Meeting place',config.id==='capital'?'Fountain':'Central clearing','House entrances'];
  names.forEach((name,i)=>$('places').options[i].textContent=name);
  $('hint').textContent='Drag to look · WASD to walk · E to interact · P to pause · H to hide controls';
  const paragraphs=$('info').querySelectorAll('p');
  $('info').querySelector('h2').textContent=config.name;
  paragraphs[0].textContent=config.description;
  paragraphs[1].textContent='Five furnished interiors and six reconstructed adult residents use local navigation, daily routines, geometric line of sight and short event memories. Conversations are scripted. This is not vision from camera images and does not call a language model.';
  paragraphs[2].textContent='People can open doors, work, visit homes and exchange short lines. The original world archive remains unchanged. Visual detail and character animation are still works in progress.';
}
