import {build} from 'esbuild';import fs from 'node:fs/promises';import {fileURLToPath} from 'node:url';import path from 'node:path';import {createHash} from 'node:crypto';
const root=path.dirname(fileURLToPath(import.meta.url));const sha=b=>createHash('sha256').update(b).digest('hex');
await build({entryPoints:[root+'/main.js'],bundle:true,format:'iife',platform:'browser',target:'es2022',minify:true,outfile:root+'/courtyard.js',legalComments:'eof'});
const notices=await fs.readFile(root+'/THIRD_PARTY_LICENSES.txt','utf8');await fs.appendFile(root+'/courtyard.js','\n/*\n'+notices.replaceAll('*/','* /')+'\n*/\n');
const manifest=JSON.parse(await fs.readFile(root+'/ASSETS.json')),paths=new Set();for(const entry of manifest.assets){if(entry.maps)for(const f of Object.values(entry.maps))paths.add(f);if(entry.file)paths.add(entry.file);}
const packed={},runtime=[];for(const p of paths){if(!p.startsWith('assets/')||p.includes('..'))throw Error('Unsafe asset path');const b=await fs.readFile(root+'/'+p);const record=manifest.assets.find(a=>a.file===p)||manifest.files.find(a=>a.file===p);if(record?.sha256&&sha(b)!==record.sha256)throw Error('Asset hash mismatch: '+p);const mime=p.endsWith('.jpg')?'image/jpeg':p.endsWith('.png')?'image/png':p.endsWith('.webp')?'image/webp':p.endsWith('.glb')?'model/gltf-binary':'application/octet-stream';packed[p]='data:'+mime+';base64,'+b.toString('base64');runtime.push({path:p,bytes:b.length,sha256:sha(b)});}
manifest.runtimeFiles=runtime;manifest.runtimeBytes=runtime.reduce((a,f)=>a+f.bytes,0);await fs.writeFile(root+'/ASSETS.json',JSON.stringify(manifest,null,2));
const template=await fs.readFile(root+'/index.html','utf8'),css=await fs.readFile(root+'/courtyard.css','utf8'),js=await fs.readFile(root+'/courtyard.js','utf8');
const script=s=>'<script>'+s.replace(/<\/script/gi,'<\\/script')+'</script>';
const inline=script('window.COURTYARD_MANIFEST='+JSON.stringify(manifest)+';window.COURTYARD_ASSETS='+JSON.stringify(packed)+';')+script(js);
let html=template.replace(/<link rel="stylesheet" href="courtyard.css[^\"]*">/,'<style>'+css+'</style>').replace(/<script src="courtyard.js[^\"]*"><\/script>/,()=>inline);
if(html.includes('src="courtyard.js'))throw Error('Standalone script was not inlined');
await fs.mkdir(root+'/dist',{recursive:true});await fs.writeFile(root+'/dist/Terra_Courtyard.html',html);await fs.writeFile(root+'/dist/BUILD.json',JSON.stringify({version:'0.5.0',runtimeFiles:runtime,standalone:{bytes:Buffer.byteLength(html),sha256:sha(html)},rendererSha256:sha(js)},null,2));
console.log('Courtyard packaged',manifest.runtimeFiles.length,'files',manifest.runtimeBytes,'asset bytes;',Buffer.byteLength(html),'standalone bytes');
