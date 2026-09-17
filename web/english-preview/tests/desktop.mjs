import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const root=process.env.TERRA_WORKSPACE||process.cwd();
const report={edition:'offline',checks:[],scenes:[],pageErrors:[],network:[]};
function pass(name,details){report.checks.push({name,pass:true,details});console.log('PASS',name,details??'');}
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},offline:true});const page=await context.newPage();
page.on('pageerror',e=>report.pageErrors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))report.network.push(r.url())});
const url='file:///'+root+'/source/web/english-preview/dist/Terra_World_03.html';
const go=async hash=>{await page.evaluate(h=>location.hash=h,hash);await page.waitForTimeout(50);};
try{
await page.goto(url);await page.waitForFunction(()=>document.querySelector('#hero-art').naturalWidth>0);assert(await page.evaluate(()=>TERRA_OFFLINE));pass('offline-home');
await page.screenshot({path:root+'/qa/v03-home.png',fullPage:true});
await go('atlas');await page.waitForFunction(()=>TERRA_PREVIEW.inspect().world,{},{timeout:60000});pass('globe-renderer',await page.evaluate(()=>TERRA_PREVIEW.inspect().world));
await page.selectOption('#polity-select',{index:2});assert((await page.locator('#place-detail h2').textContent()).length>0);pass('polity-inspector');
await page.evaluate(()=>TERRA_PREVIEW.setFrame(0));assert((await page.locator('#world-year').textContent()).includes('11,990'));await page.evaluate(()=>TERRA_PREVIEW.setFrame(116));pass('timeline-first-and-last');
await page.click('#flat-mode');assert.equal(await page.evaluate(()=>TERRA_PREVIEW.inspect().world.mode),'flat');pass('flat-map');await page.click('#sphere-mode');
await page.screenshot({path:root+'/qa/v03-atlas.png',fullPage:true});
await go('chronicle');await page.waitForSelector('.event-row');assert.equal(await page.locator('.event-row').count(),80);await page.fill('#event-search','discovery');await page.fill('#event-search','');await page.selectOption('#event-kind','discovery');assert((await page.locator('#event-count').textContent()).includes('records'));pass('chronicle-search-and-filter');
await page.screenshot({path:root+'/qa/v03-chronicle.png'});
await go('people');await page.waitForFunction(()=>document.querySelectorAll('.portrait-card img').length===8&&[...document.querySelectorAll('.portrait-card img')].every(i=>i.complete&&i.naturalWidth>0),{},{timeout:20000});pass('all-eight-portraits');
await page.locator('.portrait-card').first().click();assert((await page.locator('#person-detail').textContent()).includes('434 CE to 476 CE'));await page.click('#close-person');pass('biography-identity-and-dates');
await page.fill('#people-search','Mulatuananpa');assert((await page.locator('#people-list').textContent()).includes('Mulatuananpa'));await page.fill('#people-search','');pass('people-search');await page.screenshot({path:root+'/qa/v03-people.png',fullPage:true});
for(let index=0;index<3;index++){
 await go('walk/'+index);await page.waitForFunction(()=>document.querySelector('#walk-frame').contentWindow?.GAME?.ready,{},{timeout:30000});await page.waitForTimeout(2000);
 const frame=page.frames().find(f=>f.parentFrame());assert(frame);const state=await frame.evaluate(()=>GAME.inspect());assert.equal(state.archivedNPCs,0);assert.equal(state.npcCount,[34,30,23][index]);assert.equal(state.grass,2600);assert.deepEqual(state.errors,[]);
 const before=await frame.evaluate(()=>({...GAME.inspect().player}));await frame.locator('#c3d').click({position:{x:600,y:400}});await page.keyboard.down('w');await page.waitForTimeout(600);await page.keyboard.up('w');const after=await frame.evaluate(()=>({...GAME.inspect().player}));assert(Math.hypot(after.x-before.x,after.z-before.z)>1);pass('walk-'+index+'-movement');
 await page.selectOption('#walk-light','0.73');await page.waitForTimeout(150);assert((await frame.evaluate(()=>GAME.inspect().time))>.72);await page.selectOption('#walk-light','0.41');pass('walk-'+index+'-lighting');
 await page.click('[data-site="plaza"]');await page.waitForTimeout(200);const plaza=await frame.evaluate(()=>GAME.inspect().player);assert(Math.abs(plaza.x-9)<1);pass('walk-'+index+'-landmark');
 await frame.evaluate(()=>{const n=GAME.someNPC();GAME.teleport(n.x+1.2,n.z+1.2,0)});await frame.locator('#c3d').click({position:{x:600,y:400}});await page.keyboard.press('e');await frame.waitForSelector('#dlg',{state:'visible',timeout:5000});assert((await frame.locator('#dcard').textContent()).includes('RECONSTRUCTED RESIDENT'));await frame.locator('#dtopics button').nth(1).click();assert((await frame.locator('.msg').count())>=3);assert(!/[А-Яа-яЁё]/.test(await frame.locator('body').innerText()));pass('walk-'+index+'-dialogue');
 await page.screenshot({path:root+'/qa/v03-dialogue-'+index+'.png'});await frame.locator('#dclose').click();await page.click('[data-site="plaza"]');await page.waitForTimeout(300);await page.screenshot({path:root+'/qa/v03-walk-'+index+'.png'});
 report.scenes.push({...state,fps:await frame.evaluate(()=>GAME.fps)});pass('walk-'+index+'-render');
}
await go('home');await page.setViewportSize({width:390,height:844});await page.screenshot({path:root+'/qa/v03-mobile-home.png',fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));pass('mobile-home-no-overflow');
await go('people');await page.waitForSelector('.portrait-card');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));pass('mobile-gallery-no-overflow');await page.screenshot({path:root+'/qa/v03-mobile-people.png'});
const final=await page.evaluate(()=>TERRA_PREVIEW.inspect());assert.deepEqual(final.errors,[]);assert.deepEqual(final.untranslated,[]);assert.deepEqual(report.pageErrors,[]);assert.deepEqual(report.network,[]);pass('no-browser-errors-or-untranslated-records');pass('zero-network-requests-in-offline-edition');report.final=final;report.pass=true;
}catch(e){report.pass=false;report.failure=e.stack;console.error('FAIL',e.stack);}finally{await fs.writeFile(root+'/qa/QA03_BASE.json',JSON.stringify(report,null,2));await browser.close();}
if(!report.pass)process.exitCode=1;
