import fs from 'node:fs/promises';import {execFileSync} from 'node:child_process';import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url)),qa=process.env.TERRA_QA||root+'/qa-results';
await fs.mkdir(qa,{recursive:true});
let output='',status=0;
try{output=execFileSync(process.execPath,['--test','--test-reporter=tap',fileURLToPath(new URL('./release06-nav.mjs',import.meta.url))],{encoding:'utf8'});}
catch(e){output=String(e.stdout||'')+String(e.stderr||'');status=e.status||1;}
const count=Number(output.match(/^# tests (\d+)/m)?.[1]||0),failed=Number(output.match(/^# fail (\d+)/m)?.[1]||0);
const result={version:'0.6.0',pass:status===0&&failed===0&&count>=11,checks:Array.from({length:count},(_,i)=>({name:'navigation-and-perception-unit-'+(i+1),pass:status===0})),output};
await fs.writeFile(qa+'/QA_UNIT.json',JSON.stringify(result,null,2));console.log(output);
if(!result.pass)process.exitCode=1;
