import {fields,coordinates,more,closeMore,openInspector,band} from './fixtures';
import {test,expect,type Page} from './fixtures';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../outputs/spx007b/',import.meta.url)),output=root+'completion-registration/';await mkdir(output,{recursive:true});
const samples=JSON.parse(await readFile(root+'completion_registration_samples.json','utf8'));
async function capture(page:Page,id:string,index:number,suffix=''){
 await closeMore(page);
 await page.waitForFunction(index=>{const s=window.__sky!.engine.getCutoutStatus();return s.loaded&&s.kind==='epoch'&&s.frameIndex===index},index);await page.waitForTimeout(250);
 const value=await page.evaluate(({id,index,points})=>{const sky=window.__sky!,target=sky.targets.find(t=>t.id===id)!,frame=target.sequence!.frames[index];return {frame,camera:sky.engine.snapshot(),cutout:sky.engine.getCutoutStatus(),samples:points.map((p:{sky:[number,number];mirrorSky:[number,number]})=>({...p,screen:(()=>{const q=sky.engine.project(p.sky),r=document.querySelector('.sky-canvas')!.getBoundingClientRect();return q?[q[0]+r.left,q[1]+r.top]:null})(),mirrorScreen:(()=>{const q=sky.engine.project(p.mirrorSky),r=document.querySelector('.sky-canvas')!.getBoundingClientRect();return q?[q[0]+r.left,q[1]+r.top]:null})()}))}},{id,index,points:samples[id][index]});
 const name=id+'_frame'+index+suffix;await page.screenshot({path:output+name+'.png'});await writeFile(output+name+'_screen.json',JSON.stringify(value,null,2));
}
test('all ten new prepared epochs and four generated frames render their actual registered FITS content',async({page})=>{
 const requests:string[]=[];page.on('request',r=>requests.push(r.url()));await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/explorer');await page.waitForFunction(()=>!!window.__sky);
 for(const [id,name] of [['wise0855','WISE 0855'],['r_dra','R Draconis']]){
  await fields(page);await page.getByRole('navigation',{name:'Prepared fields navigation'}).getByRole('button',{name:new RegExp('^'+name)}).click();
  await more(page);
  await page.waitForFunction(id=>window.__analysis?.targetId===id&&window.__analysis.prepared,id);await page.getByLabel('Observation group').selectOption('inspection');await page.waitForFunction(()=>window.__analysis!.prepared&&window.__analysis!.groupId==='inspection');
  const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());
  for(let index=0;index<5;index++){await page.getByRole('button',{name:new RegExp(`^Select observation ${index+1}:`)}).click();await capture(page,id,index);expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);}
  await page.mouse.move(700,420);await page.mouse.down();await page.mouse.move(725,440,{steps:8});await page.mouse.up();await capture(page,id,4,'_panned');
  await page.setViewportSize({width:1200,height:900});await page.waitForFunction(()=>window.__sky!.engine.snapshot().size[0]===1200);await capture(page,id,4,'_resized');
  await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);await page.setViewportSize({width:1440,height:1000});
 }
 expect(requests.filter(u=>/\/TAP\b|\/ibe\/data\/spherex\//i.test(u))).toEqual([]);
 await page.goto('/?ra=331.12&dec=-56.78&fov=0.05&detector=6');await page.waitForFunction(()=>!!window.__sky);await page.getByRole('button',{name:'Search existing local FITS coverage only',exact:true}).click();await expect(page.locator('.availability-results')).toContainText('6 real available');
 await page.getByRole('button',{name:'Prepare real timeline locally',exact:true}).click();await page.getByRole('button',{name:'Explore Timeline',exact:true}).click();await page.waitForFunction(()=>window.__analysis?.targetId.startsWith('region_')&&window.__analysis.prepared);
  await more(page);
 const id=await page.evaluate(()=>window.__analysis!.targetId);await page.getByLabel('Observation group').selectOption('inspection');await page.waitForFunction(()=>window.__analysis!.prepared&&window.__analysis!.groupId==='inspection');
 const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());
 for(let index=0;index<4;index++){await page.getByRole('button',{name:new RegExp(`^Select observation ${index+1}:`)}).click();await capture(page,id,index);expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);}
 await page.mouse.move(700,420);await page.mouse.down();await page.mouse.move(725,440,{steps:8});await page.mouse.up();await capture(page,id,3,'_panned');await page.setViewportSize({width:1200,height:900});await page.waitForFunction(()=>window.__sky!.engine.snapshot().size[0]===1200);await capture(page,id,3,'_resized');
 expect(await page.locator('.aladin-container').count()).toBe(1);expect((await page.evaluate(()=>window.__sky!.engine.getDiagnostics())).layers.length).toBeLessThanOrEqual(12);
 await writeFile(output+'browser.json',JSON.stringify({realNewStaticEpochs:10,realDynamicEpochs:4,captures:20,oneMap:true,cacheLimit:12,passed:true},null,2));
});
