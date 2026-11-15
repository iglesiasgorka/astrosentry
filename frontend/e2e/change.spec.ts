import {fields,coordinates,more,closeMore,openInspector,band} from './fixtures';
import {test,expect,type Page} from './fixtures';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const directory=fileURLToPath(new URL('../../outputs/spx007b/',import.meta.url));
await mkdir(directory,{recursive:true});
const samples=JSON.parse(await readFile(directory+'registration_samples.json','utf8'));
const residualSamples=JSON.parse(await readFile(directory+'residual_samples.json','utf8'));
async function ready(page:Page){await page.goto('/');await page.waitForFunction(()=>!!window.__sky);await page.getByRole('button',{name:'Fly to Epsilon Indi B',exact:true}).click();await page.waitForFunction(()=>window.__analysis?.prepared&&window.__analysis.targetId==='epsilon_indi_b'&&window.__sky!.engine.getCutoutStatus().loaded);}
async function epochReady(page:Page,index:number){await page.waitForFunction(index=>{const status=window.__sky!.engine.getCutoutStatus();return status.loaded&&status.kind==='epoch'&&status.frameIndex===index;},index);await page.waitForTimeout(180);}
async function captureEpoch(page:Page,index:number){
 await closeMore(page);
  const data=await page.evaluate(({index,points})=>{const sky=window.__sky!,target=sky.targets.find(t=>t.id==='epsilon_indi_b')!;return {frame:target.sequence!.frames[index],camera:sky.engine.snapshot(),cutout:sky.engine.getCutoutStatus(),samples:points.map((p:{sky:[number,number]})=>({...p,screen:(()=>{const q=sky.engine.project(p.sky),r=document.querySelector('.sky-canvas')!.getBoundingClientRect();return q?[q[0]+r.left,q[1]+r.top]:null})()}))};},{index,points:samples.epsilon_indi_b[index]});
  await page.screenshot({path:directory+`extended_frame${index}.png`});await writeFile(directory+`extended_frame${index}_screen.json`,JSON.stringify(data,null,2));
}
async function captureDifference(page:Page,suffix=''){
 await closeMore(page);
  await page.waitForFunction(()=>window.__sky!.engine.getCutoutStatus().loaded&&window.__sky!.engine.getCutoutStatus().kind==='difference');await page.waitForTimeout(250);
  const data=await page.evaluate(points=>{const sky=window.__sky!,target=sky.targets.find(t=>t.id==='epsilon_indi_b')!,difference=target.sequence!.differences![0];return {difference,camera:sky.engine.snapshot(),cutout:sky.engine.getCutoutStatus(),projectedCorners:target.footprint.map(p=>sky.engine.project(p)),samples:points.map((p:{sky:[number,number]})=>({...p,screen:(()=>{const q=sky.engine.project(p.sky),r=document.querySelector('.sky-canvas')!.getBoundingClientRect();return q?[q[0]+r.left,q[1]+r.top]:null})()}))};},residualSamples['epsilon_indi_b:historical']);
  expect(data.cutout.cuts).toEqual([data.difference.display.vmin,data.difference.display.vmax]);expect(data.cutout.frameId).toBeNull();
  const name='difference'+suffix;await page.screenshot({path:directory+name+'.png'});await writeFile(directory+name+'_screen.json',JSON.stringify(data,null,2));
}

test('six D6 observations, guarded groups and a signed native residual share one fixed sky map',async({page})=>{
  const requests:string[]=[],errors:string[]=[];page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(String(e)));
  await ready(page);const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());
  await more(page);
  await expect(page.getByLabel('Observation group')).toHaveValue('d6-historical');
  await expect(page.locator('.comparison-group')).toContainText('6 available observations');
  await openInspector(page,'Motion');await expect(page.getByRole('region',{name:'Motion Inspector'})).toContainText('1.91982');await openInspector(page,'Overview');
  await more(page);
  await page.getByLabel('Observation group').selectOption('d6-all-inspection');await page.waitForFunction(()=>window.__analysis!.groupId==='d6-all-inspection'&&window.__analysis!.prepared);
  await expect(page.getByRole('button',{name:'Blink A/B',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'Difference B minus A',exact:true})).toBeDisabled();
  await expect(page.locator('.timeline-note')).toContainText('Inspection only');
  for(let index=0;index<6;index++){
    await page.getByRole('button',{name:new RegExp(`^Select observation ${index+1}:`)}).click();await epochReady(page,index);await captureEpoch(page,index);
    expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
    const actual=await page.evaluate(()=>({cuts:window.__sky!.engine.getCutoutStatus().cuts,display:window.__sky!.targets.find(t=>t.id==='epsilon_indi_b')!.sequence!.groups![1].display}));
    expect(actual.cuts).toEqual([actual.display.vmin,actual.display.vmax]);
  }
  await page.getByRole('button',{name:/^Select observation 2:/}).click();await epochReady(page,1);
  await openInspector(page,'Motion');
  await expect(page.getByRole('region',{name:'Motion Inspector'})).toContainText('No prepared displacement');await expect(page.getByRole('region',{name:'Motion Inspector'}).locator('.motion-values')).toHaveCount(0);
  await page.screenshot({path:directory+'additional_epoch_inspector.png'});await openInspector(page,'Overview');
  await more(page);
  await page.getByLabel('Playback speed',{exact:true}).selectOption('400');await page.getByRole('button',{name:'Play observations',exact:true}).click();await expect.poll(()=>page.evaluate(()=>window.__analysis!.index)).toBe(3);await page.getByRole('button',{name:'Pause playback',exact:true}).click();
  await more(page);
  await page.getByLabel('Observation group').selectOption('d6-historical');await page.waitForFunction(()=>window.__analysis!.prepared&&window.__analysis!.groupId==='d6-historical');await epochReady(page,0);
  await more(page);
  await page.getByRole('button',{name:'Show epoch B',exact:true}).click();await epochReady(page,3);await page.getByRole('button',{name:'Show epoch A',exact:true}).click();await epochReady(page,0);
  await page.getByRole('button',{name:'Blink A/B',exact:true}).click();await expect.poll(()=>page.evaluate(()=>window.__analysis!.index)).toBe(3);await page.getByRole('button',{name:'Stop blink',exact:true}).click();
  const localRequests=requests.filter(url=>url.includes('/data/epsilon_indi_b/frames/')&&url.endsWith('.fits')).length;
  await page.getByRole('button',{name:'Difference B minus A',exact:true}).click();await captureDifference(page);
  await expect(page.getByRole('region',{name:'Difference inspection'})).toContainText('63.1%');await expect(page.getByRole('region',{name:'Difference inspection'})).toContainText('2025-04-29');await expect(page.getByRole('region',{name:'Difference inspection'})).toContainText('2025-09-28');
  expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
  await page.mouse.move(700,420);await page.mouse.down();await page.mouse.move(735,445,{steps:10});await page.mouse.up();await captureDifference(page,'_panned');
  await page.setViewportSize({width:1150,height:850});await page.waitForTimeout(200);await captureDifference(page,'_resized');
  const panned=await page.evaluate(()=>window.__sky!.engine.getCamera());
  await more(page);
  await page.getByRole('button',{name:'Show epoch A',exact:true}).click();await epochReady(page,0);expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(panned);
  await more(page);
  await page.getByRole('button',{name:'Show epoch B',exact:true}).click();await epochReady(page,3);expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(panned);
  expect(requests.filter(url=>url.includes('/data/epsilon_indi_b/frames/')&&url.endsWith('.fits')).length).toBe(localRequests);
  expect((await page.evaluate(()=>window.__sky!.engine.getDiagnostics())).layers.length).toBeLessThanOrEqual(12);expect(await page.locator('.aladin-container').count()).toBe(1);
  expect(errors).toEqual([]);expect(requests.filter(url=>/\/TAP\b|\/ibe\/data\/spherex\//i.test(url))).toEqual([]);
  await writeFile(directory+'change_browser_network.json',JSON.stringify({requests,pageErrors:errors,passed:true},null,2));
});

test('missing residual fails honestly and returns immediately to the real epochs',async({page})=>{
  await page.route('https://**/*',r=>r.abort());await page.route('**/differences/historical.fits',r=>r.fulfill({status:404,body:'Deliberate missing residual'}));
  await page.emulateMedia({reducedMotion:'reduce'});await ready(page);
  await page.getByRole('button',{name:'Difference B minus A',exact:true}).click();await expect(page.getByRole('region',{name:'Difference inspection'})).toContainText('Residual unavailable');
  expect(await page.evaluate(()=>window.__sky!.engine.getCutoutStatus().loaded)).toBe(false);
  await more(page);
  await page.getByRole('button',{name:'Show epoch A',exact:true}).click();await epochReady(page,0);
  await expect(page.getByRole('region',{name:'Epsilon Indi B inspection'})).toBeVisible();
});
