import {test,expect,type Page} from '@playwright/test';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import type {LonLat} from '../src/types/sky';
const directory=fileURLToPath(new URL('../../outputs/spx005/regression/',import.meta.url));
await mkdir(directory,{recursive:true});
const samples=JSON.parse(await readFile(new URL('../../outputs/spx005/registration_samples.json',import.meta.url),'utf8')) as Record<string,Array<Array<{pixel:LonLat;sky:LonLat;value:number}>>>;
async function ready(page:Page){await page.goto('/');await page.waitForFunction(()=>!!window.__sky);}
async function arrived(page:Page,id:string){await page.waitForFunction(id=>window.__analysis?.targetId===id&&window.__analysis.prepared&&window.__sky!.engine.getCutoutStatus().loaded,id,{timeout:30000});}
async function frameReady(page:Page,index:number){await page.waitForFunction(index=>{const sky=window.__sky!,analysis=window.__analysis!;const target=sky.targets.find(t=>t.id===analysis.targetId)!;return sky.engine.getCutoutStatus().loaded&&sky.engine.getCutoutStatus().frameId===analysis.frameIds[index];},index);await page.waitForTimeout(250);}
async function capture(page:Page,id:string,index:number,suffix=''){
  const logicalIndex=index; index=await page.evaluate(({id,index})=>{const sky=window.__sky!;return sky.targets.find(t=>t.id===id)!.sequence!.frames.findIndex(f=>f.id===window.__analysis!.frameIds[index]);},{id,index});
  const data=await page.evaluate(({id,index,points})=>{const sky=window.__sky!,target=sky.targets.find(t=>t.id===id)!,frame=target.sequence!.frames[index];
    return {id,index,frame,camera:sky.engine.snapshot(),cutout:sky.engine.getCutoutStatus(),corners:target.footprint.map(p=>sky.engine.project(p)),samples:points.map(point=>({...point,screen:sky.engine.project(point.sky)}))};
  },{id,index,points:samples[id][index]});
  const target=await page.evaluate(id=>window.__sky!.targets.find(t=>t.id===id)!,id);
  expect(data.cutout.frameId).toBe(data.frame.id);expect(data.cutout.cuts).toEqual([target.sequence!.display.vmin,target.sequence!.display.vmax]);
  expect(data.cutout.nativeCenter![0]).toBeCloseTo(target.center.raDeg,7);expect(data.cutout.nativeCenter![1]).toBeCloseTo(target.center.decDeg,7);
  const name=`${id}_frame${index}${suffix}`;await page.screenshot({path:directory+name+'.png'});await writeFile(directory+name+'_screen.json',JSON.stringify(data,null,2));
}
async function verifyMarks(page:Page){
  const differences=await page.evaluate(()=>{const sky=window.__sky!,target=sky.targets.find(t=>t.id===window.__analysis!.targetId)!;
    return window.__analysis!.motionFrameIds.map(id=>target.sequence!.frames.find(f=>f.id===id)!).flatMap((frame,index)=>['expected','measured'].flatMap(kind=>{const position=kind==='expected'?frame.expectedPosition:frame.measuredPosition;if(!position)return [];
      const expected=sky.engine.project([position.raDeg,position.decDeg])!,group=document.querySelector<SVGGElement>(`[data-mark="${kind}-${index}"]`)!;
      const matrix=group.transform.baseVal.consolidate()!.matrix;return [Math.hypot(matrix.e-expected[0],matrix.f-expected[1])];}));
  });expect(differences.length).toBeGreaterThan(0);expect(Math.max(...differences)).toBeLessThan(.05);
}

test('six actual epochs play and blink on one fixed WCS map with scientific inspectors',async({page})=>{
  const requests:string[]=[],errors:string[]=[],tiles:{url:string;status:number}[]=[];
  page.on('request',r=>requests.push(r.url()));page.on('pageerror',error=>errors.push(String(error)));
  page.on('response',r=>{if(r.url().includes('/Npix'))tiles.push({url:r.url(),status:r.status()})});
  await ready(page);
  await expect.poll(()=>new Set(tiles.filter(t=>t.status===200&&t.url.includes('/Norder0/')).map(t=>t.url.match(/Npix\d+_29/)?.[0])).size,{timeout:30000}).toBe(12);
  await page.waitForTimeout(600);await page.screenshot({path:directory+'global.png'});
  for(const [id,name] of [['epsilon_indi_b','Epsilon Indi B'],['m101','M101'],['barnard',"Barnard's Star"]]){
    await page.getByRole('button',{name:`Fly to ${name}`,exact:true}).click();await arrived(page,id);await frameReady(page,0);
    const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());await capture(page,id,0);
    const localStart=requests.length;
    await page.getByRole('button',{name:'Next observation',exact:true}).click();await frameReady(page,1);await capture(page,id,1);
    await page.getByRole('button',{name:'Previous observation',exact:true}).click();await frameReady(page,0);
    await page.getByLabel('Playback speed',{exact:true}).selectOption('400');
    await page.getByRole('button',{name:'Play observations',exact:true}).click();
    await expect.poll(()=>page.evaluate(()=>window.__analysis!.index===window.__analysis!.b)).toBe(true);
    await page.getByRole('button',{name:'Pause playback',exact:true}).click();
    const paused=await page.evaluate(()=>window.__analysis!.index);await page.waitForTimeout(600);expect(await page.evaluate(()=>window.__analysis!.index)).toBe(paused);
    await page.getByLabel('Observation A',{exact:true}).selectOption(String(await page.evaluate(()=>window.__analysis!.b)));await page.getByLabel('Observation B',{exact:true}).selectOption('0');
    await page.getByRole('button',{name:'Blink A/B',exact:true}).click();await expect.poll(()=>page.evaluate(()=>window.__analysis!.index)).toBe(0);
    await page.getByRole('button',{name:'Stop blink',exact:true}).click();
    expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
    const diagnostics=await page.evaluate(id=>window.__sky!.engine.getDiagnostics().layers.filter(l=>l.key.startsWith(id+':')),id);
    expect(diagnostics).toHaveLength(2);expect(diagnostics.every(l=>l.ready&&l.stretch==='asinh')).toBe(true);expect(diagnostics[0].cuts).toEqual(diagnostics[1].cuts);
    expect(requests.slice(localStart).filter(url=>url.includes('/data/')&&url.endsWith('.fits')&&!url.includes('/hips/'))).toEqual([]);
    if(id!=='m101'){
      await page.getByRole('button',{name:id==='barnard'?'Predicted positions':'Motion Inspector',exact:true}).click();await page.waitForTimeout(100);await verifyMarks(page);
      if(id==='epsilon_indi_b'){await expect(page.getByRole('region',{name:'Motion Inspector'})).toContainText('1.91982');await expect(page.getByRole('region',{name:'Motion Inspector'})).toContainText('0.16395');}
      else{expect(await page.locator('[data-mark^="measured-"]').count()).toBe(0);await expect(page.getByRole('region',{name:'Motion Inspector'})).toContainText('invalid and saturated');}
      await page.screenshot({path:directory+id+'_inspector.png'});
      await page.mouse.move(700,420);await page.mouse.down();await page.mouse.move(740,445,{steps:8});await page.mouse.up();await page.waitForTimeout(150);await verifyMarks(page);
      await page.setViewportSize({width:1200,height:900});await page.waitForTimeout(200);await verifyMarks(page);
      await page.getByRole('button',{name:'Close Motion Inspector'}).click();
    }else{await expect(page.getByRole('button',{name:'Motion Inspector',exact:true})).toHaveCount(0);await page.mouse.move(700,420);await page.mouse.down();await page.mouse.move(740,445,{steps:8});await page.mouse.up();}
    await page.getByRole('button',{name:/^Select observation 2:/}).click();await frameReady(page,1);await capture(page,id,1,'_panned');
    await page.setViewportSize({width:1150,height:850});await page.waitForTimeout(200);await capture(page,id,1,'_resized');
    await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);
    expect(await page.evaluate(()=>window.__analysis)).toBeUndefined();expect(await page.locator('.aladin-container').count()).toBe(1);
    await page.setViewportSize({width:1440,height:1000});await page.waitForTimeout(150);
  }
  expect(errors).toEqual([]);expect(requests.filter(url=>/\/TAP\b|\/ibe\/data\/spherex\//i.test(url))).toEqual([]);
  await writeFile(directory+'browser_network.json',JSON.stringify({requests,tiles,pageErrors:errors,passed:true},null,2));
});

test('playback cancels on navigation and failures never pretend to show another epoch',async({page})=>{
  await page.route('https://**/*',route=>route.abort());await ready(page);await page.emulateMedia({reducedMotion:'reduce'});
  await page.getByRole('button',{name:'Fly to Epsilon Indi B',exact:true}).click();await arrived(page,'epsilon_indi_b');
  await page.getByRole('button',{name:'Play observations',exact:true}).click();
  await page.getByRole('button',{name:'4 prepared fields'}).click();await page.getByRole('navigation',{name:'Prepared fields navigation'}).getByRole('button',{name:/M101/}).click();await arrived(page,'m101');
  expect(await page.evaluate(()=>window.__analysis!.mode)).toBe('paused');expect(await page.evaluate(()=>window.__analysis!.index)).toBe(0);
  await page.getByRole('button',{name:'Play observations',exact:true}).click();await page.getByRole('button',{name:'Minimize analysis',exact:true}).click();expect(await page.evaluate(()=>window.__analysis!.mode)).toBe('paused');
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:directory+'mobile_minimized.png'});
  await page.getByRole('button',{name:'Expand analysis',exact:true}).click();await page.screenshot({path:directory+'mobile_analysis.png'});
  await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);
  await page.route('**/data/barnard/frames/*0501*.fits',route=>route.fulfill({status:404,body:'Deliberate missing second epoch'}));
  await page.getByRole('button',{name:"Fly to Barnard's Star",exact:true}).click();
  await page.waitForFunction(()=>window.__sky!.engine.getCutoutStatus().loaded);
  await page.getByRole('button',{name:'Next observation',exact:true}).click();
  await expect(page.locator('.honest-fallback')).toContainText('Local inspection only.');expect(await page.evaluate(()=>window.__sky!.engine.getCutoutStatus().loaded)).toBe(false);
  await page.screenshot({path:directory+'missing_epoch.png'});
});
