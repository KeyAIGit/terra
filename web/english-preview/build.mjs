import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {gzipSync,gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
const here=path.dirname(fileURLToPath(import.meta.url));
const out=path.resolve(here,'dist');
const cache=process.argv.find(a=>a.startsWith('--cache='))?.slice(8);
const sha=b=>createHash('sha256').update(b).digest('hex');
const base='https://d2ol7oe51mr4n9.cloudfront.net/user_3G1EoKpPdtVgILUsyI2EdcfEGyE/';
const originals={walk:['038b2f5a-79fd-4222-a148-e1ae1a1ebf46.html','29b4e734b064f5ea2b6dc3c6f7bdc5336247182d12c1a2e1fc6b6af37d171332'],planet:['f7e044a1-6fb4-41c3-8142-04490cbf3b54.html','3f816f25d4bd1eecb7f4b6ade9e4b04d57747673b293d1c4626b09b7da915bff'],people:['e51caab7-635aab7.html','']};
originals.people=['e51caab7-635a-4fa1-9414-150ad5faade1.html','3cce30af2d2e8fb7f279815ce4a44755adadddb938cc2aa63ceb8b3991fbae2b'];
const names=['localization.js','localization-extra.js','walk-patch.js','app.js'];
const code=Object.fromEntries(await Promise.all(names.map(async n=>[n,await fs.readFile(path.join(here,n),'utf8')])));
for(const[n,s]of Object.entries(code))new vm.Script(s,{filename:n});
const template=await fs.readFile(path.join(here,'index.html'),'utf8'),css=await fs.readFile(path.join(here,'style.css'),'utf8');
const manifest={version:'0.2.0',sourceFiles:{},assets:{},buildChecks:{}};
for(const n of [...names,'index.html','style.css'])manifest.sourceFiles[n]=sha(await fs.readFile(path.join(here,n)));
async function bytes(url,local){
 if(cache&&local){try{return await fs.readFile(path.join(cache,local));}catch(e){if(e.code!=='ENOENT')throw e;}}
 const response=await fetch(url,{signal:AbortSignal.timeout(90000)});if(!response.ok)throw Error(url+' HTTP '+response.status);return Buffer.from(await response.arrayBuffer());
}
const embedded={},raw={};
for(const[name,[file,expected]]of Object.entries(originals)){
 const url=base+file,b=await bytes(url,'original/'+name+'.html');if(sha(b)!==expected)throw Error('Source integrity mismatch: '+name);
 embedded[url]=gzipSync(b,{level:9}).toString('base64');raw[name]=b.toString('utf8');manifest.assets[url]={bytes:b.length,sha256:expected};console.log('Verified source',name,b.length);
}
const scriptTags=s=>[...s.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(x=>x[1]);
const value=s=>JSON.parse(s.slice(s.indexOf('=')+1).trim().replace(/;$/,''));
const archive=JSON.parse(gunzipSync(Buffer.from(value(scriptTags(raw.planet)[2]),'base64')));
const box={Intl,console,Set};vm.createContext(box);vm.runInContext(code['localization.js']+'\n'+code['localization-extra.js']+'\nthis.E=TerraEnglish;',box);
const events=archive.events.filter(e=>box.E.tr(e.t).includes('awaiting'));
const deeds=archive.people.flatMap(p=>p.ds).filter(ds=>box.E.tr(ds[2]).includes('awaiting'));
for(const p of archive.people)box.E.tr(p.e);
if(events.length||deeds.length||box.E.unresolved.size)throw Error('Untranslated archive records remain.');
manifest.buildChecks={javascriptSyntax:true,frames:archive.frames.length,events:archive.events.length,people:archive.people.length,eventTranslationMissing:events.length,deedTranslationMissing:deeds.length};
const artBase=code['app.js'].match(/const ARTBASE='([^']+)'/)[1];
const artEntries=[...code['app.js'].matchAll(/([A-Za-z]+):ARTBASE\+'([^']+)'/g)];
let offlineApp=code['app.js'];
for(const[,name,file]of artEntries){const url=artBase+file,b=await bytes(url,'art/'+name+'.png');if(b.length<1000||b.subarray(0,8).toString('hex')!=='89504e470d0a1a0a')throw Error('Invalid artwork: '+name);manifest.assets[url]={bytes:b.length,sha256:sha(b)};offlineApp=offlineApp.replace("ARTBASE+'"+file+"'",JSON.stringify('data:image/png;base64,'+b.toString('base64')));console.log('Embedded artwork',name,b.length);}
if(artEntries.length!==7)throw Error('Expected seven generated artworks.');
const adapter=`(()=>{const contents=${JSON.stringify(embedded)},cache=new Map(),originalFetch=window.fetch.bind(window);window.fetch=async function(input,options){const url=typeof input==='string'?input:input.url;if(!Object.prototype.hasOwnProperty.call(contents,url))return originalFetch(input,options);if(!cache.has(url)){const bytes=Uint8Array.from(atob(contents[url]),c=>c.charCodeAt(0));cache.set(url,new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());}return new Response(await cache.get(url),{status:200,headers:{'Content-Type':'text/html; charset=utf-8'}});};window.TERRA_OFFLINE=true;})();`;
const tag=s=>'<script>'+s.replace(/<\/script/gi,'<\\/script')+'</script>';
function bundle(offline){let html=template.replace('<link rel="stylesheet" href="style.css">','<style>'+css+'</style>');for(const n of names)html=html.replace('<script src="'+n+'"></script>',()=>tag((offline&&n===names[0]?adapter+'\n':'')+(offline&&n==='app.js'?offlineApp:code[n])));if(offline)html=html.replace('The first visit retrieves the original published assets over the internet.','This standalone edition includes the original published assets and all seven generated artworks. No internet connection is required for exploration.');return html;}
await fs.mkdir(out,{recursive:true});
for(const[filename,offline]of [['Terra_World_English_Preview.html',true],['Terra_World_Online_Preview.html',false]]){const html=bundle(offline);await fs.writeFile(path.join(out,filename),html);manifest[filename]={bytes:Buffer.byteLength(html),sha256:sha(html)};}
await fs.writeFile(path.join(out,'BUILD_MANIFEST.json'),JSON.stringify(manifest,null,2));
for(const n of ['README.md','QA_REPORT.json']){try{await fs.copyFile(path.join(here,n),path.join(out,n));}catch(e){if(e.code!=='ENOENT')throw e;}}
console.log(JSON.stringify(manifest.buildChecks));console.log('Built',out,manifest.Terra_World_English_Preview);
