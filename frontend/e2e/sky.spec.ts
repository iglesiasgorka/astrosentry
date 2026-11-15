import {fields,coordinates,more,closeMore,openInspector,band} from './fixtures';
import { test,expect,type Page } from './fixtures';
import { readFile,writeFile,mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import type { LonLat } from '../src/types/sky';

const output=fileURLToPath(new URL('../../outputs/spx007b/regression/legacy/',import.meta.url));
await mkdir(output,{recursive:true});
const temporalSamples=JSON.parse(await readFile(new URL('../../outputs/spx007b/registration_samples.json',import.meta.url),'utf8')) as Record<string,Array<Array<{pixel:LonLat;sky:LonLat;value:number}>>>;
const samples=Object.fromEntries(Object.entries(temporalSamples).map(([id,frames])=>[id,frames[0]]));
async function ready(page:Page){await page.goto('/');await page.waitForFunction(()=>!!window.__sky);}
async function arrived(page:Page,id:string){await page.waitForFunction(key=>window.__sky?.state.mode==='inspecting'&&window.__sky.engine.getCutoutStatus().id===key&&window.__sky.engine.getCutoutStatus().loaded,id,{timeout:25000});await page.waitForTimeout(400);}
async function capture(page:Page,id:string,suffix=''){
 await closeMore(page);
  const data=await page.evaluate(({id,points})=>{
    const sky=window.__sky!;const target=sky.targets.find(t=>t.id===id)!;
    return {id,camera:sky.engine.snapshot(),cutout:sky.engine.getCutoutStatus(),target,
      centerScreen:sky.engine.project([target.center.raDeg,target.center.decDeg]),
      projectedCorners:target.footprint.map(point=>sky.engine.project(point)),
      samples:points.map(point=>({...point,screen:(()=>{const p=sky.engine.project(point.sky),r=document.querySelector('.sky-canvas')!.getBoundingClientRect();return p?[p[0]+r.left,p[1]+r.top]:null})()}))};
  },{id,points:samples[id]});
  expect(data.cutout.loaded).toBe(true);expect(data.cutout.nativeCenter).not.toBeNull();
  expect(Math.abs(data.cutout.nativeCenter![0]-data.target.center.raDeg)).toBeLessThan(1e-7);
  expect(Math.abs(data.cutout.nativeCenter![1]-data.target.center.decDeg)).toBeLessThan(1e-7);
  expect(data.projectedCorners.every(p=>p!==null)).toBe(true);
  const name=id+suffix;await page.screenshot({path:output+name+'.png'});
  await writeFile(output+name+'_screen.json',JSON.stringify(data,null,2));
}

test('real HiPS sky, three marker flights, registered FITS, navigation and return',async({page})=>{
  const urls:string[]=[],tiles:{url:string;status:number}[]=[],errors:string[]=[];
  page.on('request',request=>urls.push(request.url()));page.on('pageerror',error=>errors.push(String(error)));
  page.on('response',response=>{if(/SPHEREx.*Npix.*_29\.png/.test(response.url()))tiles.push({url:response.url(),status:response.status()});});
  await ready(page);await expect.poll(()=>tiles.filter(t=>t.status===200).length,{timeout:25000}).toBeGreaterThan(6);
  await expect.poll(()=>new Set(tiles.filter(t=>t.status===200&&t.url.includes('/Norder0/')).map(t=>t.url.match(/Npix\d+_29/)?.[0])).size,{timeout:25000}).toBe(12);
  await page.waitForTimeout(1200);
  await expect(page.locator('[data-target]')).toHaveCount(6);
  await page.screenshot({path:output+'global.png'});
  for(const [id,name] of [['epsilon_indi_b','Epsilon Indi B'],['m101','M101'],['barnard',"Barnard's Star"]]){
    await page.getByRole('button',{name:`Fly to ${name}`,exact:true}).click();
    await expect(page.locator('main.sky-experience')).toHaveAttribute('data-mode','flying');
    await page.waitForTimeout(350);
    expect(await page.evaluate(()=>window.__sky!.engine.getCamera().fov)).toBeLessThan(360);
    await arrived(page,id);await expect(page.getByRole('region',{name:`${name} inspection`})).toBeVisible();
    const center=await page.evaluate(()=>window.__sky!.engine.getCamera().center);
    const target=await page.evaluate(key=>window.__sky!.targets.find(t=>t.id===key)!,id);
    expect(center[0]).toBeCloseTo(target.center.raDeg,8);expect(center[1]).toBeCloseTo(target.center.decDeg,8);
    await capture(page,id);
    await page.mouse.move(700,420);await page.mouse.down();await page.mouse.move(765,450,{steps:14});await page.mouse.up();await page.waitForTimeout(300);
    await capture(page,id,'_panned');
    await page.setViewportSize({width:1200,height:900});await page.waitForFunction(()=>window.__sky!.engine.snapshot().size[0]===1200);
    await capture(page,id,'_resized');
    await page.getByRole('button',{name:'Hide layer',exact:true}).click();await expect(page.getByRole('button',{name:'Show layer',exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Show layer',exact:true}).click();
    await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();
    await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);
    expect(await page.evaluate(()=>window.__sky!.engine.getCutoutStatus().id)).toBeNull();
    await expect(page.locator('.target-preview')).toHaveCount(0);
    expect(await page.locator('.aladin-container').count()).toBe(1);
    await page.setViewportSize({width:1440,height:1000});await page.waitForTimeout(250);
  }
  expect(urls.filter(url=>/\/TAP\b|\/ibe\/data\/spherex\//i.test(url))).toEqual([]);
  expect(errors).toEqual([]);expect(tiles.every(tile=>tile.status===200)).toBe(true);
  await writeFile(output+'browser_network.json',JSON.stringify({tiles,urls,pageErrors:errors},null,2));
});

test('rapid field changes, interrupted return and reduced motion keep the latest target',async({page})=>{
  await ready(page);await page.getByRole('button',{name:'Fly to Epsilon Indi B',exact:true}).click();await page.waitForTimeout(180);
  await fields(page);
  await page.getByRole('navigation',{name:'Prepared fields navigation'}).getByRole('button',{name:/Barnard/}).click();
  await arrived(page,'barnard');await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForTimeout(100);
  await fields(page);
  await page.getByRole('navigation',{name:'Prepared fields navigation'}).getByRole('button',{name:/M101/}).click();
  await arrived(page,'m101');expect(await page.locator('.aladin-container').count()).toBe(1);
  await page.screenshot({path:output+'interrupted_flight.png'});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();
  await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);
  await page.getByRole('button',{name:'Fly to Epsilon Indi B',exact:true}).click();
  await page.waitForFunction(()=>window.__sky!.state.mode==='inspecting',null,{timeout:1500});
  await arrived(page,'epsilon_indi_b');
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);
  await page.screenshot({path:output+'mobile.png'});
});

test('offline HiPS keeps local cutouts available and FITS errors stay honest',async({page})=>{
  await page.route('https://**/*',route=>route.abort('internetdisconnected'));
  await page.route('**/data/barnard/frames/*.fits',route=>route.fulfill({status:404,body:'Deliberate browser failure test'}));
  await ready(page);await expect(page.locator('.survey-notice')).toContainText('Local SPHEREx fields are still available.',{timeout:20000});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.getByRole('button',{name:'Fly to M101',exact:true}).click();await arrived(page,'m101');
  await page.screenshot({path:output+'offline_local_m101.png'});
  await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();
  await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);
  await page.getByRole('button',{name:"Fly to Barnard's Star",exact:true}).click();
  await expect(page.locator('.honest-fallback')).toContainText('Local inspection only.');
  expect(await page.evaluate(()=>window.__sky!.engine.getCutoutStatus().loaded)).toBe(false);
  await page.screenshot({path:output+'fits_error.png'});
});
