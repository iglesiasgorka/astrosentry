import {test,expect} from '@playwright/test';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const directory=fileURLToPath(new URL('../../outputs/spx005/',import.meta.url));
await mkdir(directory,{recursive:true});
const samples=JSON.parse(await readFile(directory+'registration_samples.json','utf8'));

test('fourth diagnostic field uses three real registered epochs without fictional brightness points',async({page})=>{
  const requests:string[]=[],errors:string[]=[];page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('/');await page.waitForFunction(()=>!!window.__sky);
  await expect(page.getByRole('button',{name:'4 prepared fields'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Fly to RW Aurigae',exact:true})).toBeVisible();
  await page.waitForTimeout(3500);await page.screenshot({path:directory+'global.png'});
  await page.getByRole('button',{name:'Fly to RW Aurigae',exact:true}).click();
  await page.waitForFunction(()=>window.__analysis?.targetId==='rw_aur'&&window.__analysis.prepared&&window.__sky!.engine.getCutoutStatus().loaded);
  const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());
  const capture=async(index:number,suffix='')=>{
    await page.waitForFunction(index=>window.__sky!.engine.getCutoutStatus().loaded&&window.__sky!.engine.getCutoutStatus().frameIndex===index,index);await page.waitForTimeout(250);
    const data=await page.evaluate(({index,points})=>{const sky=window.__sky!,target=sky.targets.find(t=>t.id==='rw_aur')!,frame=target.sequence!.frames[index];return {frame,camera:sky.engine.snapshot(),cutout:sky.engine.getCutoutStatus(),samples:points.map((p:{sky:[number,number]})=>({...p,screen:sky.engine.project(p.sky)}))};},{index,points:samples.rw_aur[index]});
    const target=await page.evaluate(()=>window.__sky!.targets.find(t=>t.id==='rw_aur')!);
    expect(data.cutout.nativeCenter![0]).toBeCloseTo(target.center.raDeg,7);expect(data.cutout.nativeCenter![1]).toBeCloseTo(target.center.decDeg,7);
    expect(data.cutout.cuts).toEqual([target.sequence!.display.vmin,target.sequence!.display.vmax]);
    await page.screenshot({path:directory+`rw_aur_frame${index}${suffix}.png`});await writeFile(directory+`rw_aur_frame${index}${suffix}_screen.json`,JSON.stringify(data,null,2));
  };
  for(let index=0;index<3;index++){await page.getByRole('button',{name:new RegExp(`^Select observation ${index+1}:`)}).click();await capture(index);expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);}
  const fitsBefore=requests.filter(url=>url.includes('/data/rw_aur/')&&url.endsWith('.fits')).length;
  await page.getByRole('button',{name:'Brightness Inspector',exact:true}).click();
  const inspector=page.getByRole('region',{name:'Brightness Inspector'});
  await expect(inspector).toContainText('No accepted brightness measurements');await expect(inspector).toContainText('0 / 3');expect(await page.locator('.brightness-point').count()).toBe(0);
  await page.getByRole('button',{name:/^Select brightness epoch 1:/}).click();
  await page.waitForFunction(()=>window.__analysis!.index===0);await expect(page.getByRole('button',{name:/^Select observation 1:/})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:/^Select brightness epoch 3:/}).press('Enter');await page.waitForFunction(()=>window.__analysis!.index===2);
  await page.screenshot({path:directory+'brightness_inspector.png'});
  await page.getByLabel('Playback speed',{exact:true}).selectOption('400');await page.getByRole('button',{name:'Play observations',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.__analysis!.index)).toBe(1);await page.getByRole('button',{name:'Pause playback',exact:true}).click();
  await page.getByLabel('Observation A',{exact:true}).selectOption('0');await page.getByLabel('Observation B',{exact:true}).selectOption('2');await page.getByRole('button',{name:'Blink A/B',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.__analysis!.index)).toBe(2);await page.getByRole('button',{name:'Stop blink',exact:true}).click();
  expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
  expect(requests.filter(url=>url.includes('/data/rw_aur/')&&url.endsWith('.fits')).length).toBe(fitsBefore);
  await page.getByRole('button',{name:'Close Brightness Inspector'}).click();await page.getByRole('button',{name:/^Select observation 3:/}).click();
  await page.mouse.move(700,420);await page.mouse.down();await page.mouse.move(730,440,{steps:10});await page.mouse.up();await capture(2,'_panned');
  await page.setViewportSize({width:1200,height:850});await page.waitForTimeout(200);await capture(2,'_resized');
  expect((await page.evaluate(()=>window.__sky!.engine.getDiagnostics())).layers.length).toBeLessThanOrEqual(12);
  await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);
  for(const [id,name] of [['epsilon_indi_b','Epsilon Indi B'],['m101','M101'],['barnard',"Barnard's Star"]]){
    await page.getByRole('button',{name:`Fly to ${name}`,exact:true}).click();
    await page.waitForFunction(id=>window.__analysis?.targetId===id&&window.__analysis.prepared&&window.__sky!.engine.getCutoutStatus().loaded,id);
    await page.getByRole('button',{name:'Next observation',exact:true}).click();await page.waitForFunction(()=>window.__sky!.engine.getCutoutStatus().frameIndex===window.__analysis!.b);
    await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);
  }
  expect((await page.evaluate(()=>window.__sky!.engine.getDiagnostics())).layers).toHaveLength(9);
  expect(await page.locator('.aladin-container').count()).toBe(1);expect(errors).toEqual([]);expect(requests.filter(url=>/\/TAP\b|\/ibe\/data\/spherex\//i.test(url))).toEqual([]);
  await writeFile(directory+'browser_network.json',JSON.stringify({requests,pageErrors:errors,passed:true},null,2));
});

test('missing brightness epoch is reported honestly and never creates a flux point',async({page})=>{
  await page.route('https://**/*',r=>r.abort());await page.route('**/data/rw_aur/frames/*0645*.fits',r=>r.fulfill({status:404,body:'Deliberate missing epoch test'}));
  await page.goto('/');await page.waitForFunction(()=>!!window.__sky);await page.emulateMedia({reducedMotion:'reduce'});
  await page.getByRole('button',{name:'Fly to RW Aurigae',exact:true}).click();await page.waitForFunction(()=>window.__sky!.engine.getCutoutStatus().loaded);
  await page.getByRole('button',{name:/^Select observation 3:/}).click();await expect(page.locator('.honest-fallback')).toContainText('Local inspection only.');
  await page.getByRole('button',{name:'Brightness Inspector',exact:true}).click();expect(await page.locator('.brightness-point').count()).toBe(0);await expect(page.getByRole('region',{name:'Brightness Inspector'})).toContainText('No accepted brightness measurements');
  await page.screenshot({path:directory+'missing_epoch.png'});
});
