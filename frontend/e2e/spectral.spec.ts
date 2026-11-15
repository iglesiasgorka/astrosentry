import {fields,coordinates,more,closeMore,openInspector,band} from './fixtures';
import {test,expect,type Page} from './fixtures';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import type {SpectralChannel} from '../src/features/sky/surveys';
const SPECTRAL_CHANNELS=JSON.parse(await readFile(new URL('../src/features/sky/spherex-cube.json',import.meta.url),'utf8')).channels as SpectralChannel[];
const directory=fileURLToPath(new URL('../../outputs/spx007b/',import.meta.url));
await mkdir(directory,{recursive:true});
const tilePattern=/\/Norder(\d+)\/Dir\d+\/Npix(\d+)_(\d+)\.png/;
async function ready(page:Page){await page.goto('/explorer');await page.waitForFunction(()=>window.__sky?.engine.getSpectralStatus().available);await expect(page.getByRole('slider',{name:'SPHEREx wavelength'})).toBeEnabled();}
async function applied(page:Page,index:number){await page.waitForFunction(index=>window.__sky?.engine.getSpectralStatus().appliedFrame===index&&window.__sky.engine.getSpectralStatus().phase==='progressive',index);}
async function slider(page:Page,index:number){const position=SPECTRAL_CHANNELS.findIndex(c=>c.frameIndex===index);await page.getByRole('slider',{name:'SPHEREx wavelength'}).fill(String(position));await applied(page,index);}
async function layout(page:Page,name:string){
  const result=await page.evaluate(()=>{const panel=document.querySelector('.spectral-explorer')!.getBoundingClientRect(),sky=window.__sky!;return {viewport:sky.engine.snapshot().size,panel:panel.toJSON(),markers:sky.targets.map(t=>({id:t.id,point:sky.engine.project([t.center.raDeg,t.center.decDeg]),hidden:document.querySelector<HTMLButtonElement>(`[data-target="${t.id}"]`)?.hidden}))};});
  for(const marker of result.markers){const p=marker.point!;if(p[0]>result.panel.left&&p[0]<result.panel.right&&p[1]>result.panel.top&&p[1]<result.panel.bottom)expect(marker.hidden,marker.id+' occluded anchor must be contextually hidden; field index remains equivalent').toBe(true);}
  await writeFile(directory+name+'_layout.json',JSON.stringify(result,null,2));
}

test('official channels across all six bands really change the same sky and preserve temporal analysis',async({page})=>{
  const requests:string[]=[],errors:string[]=[],tiles:{url:string;status:number;frame:number;order:number;pixel:number}[]=[];
  page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(String(e)));
  page.on('response',r=>{const match=r.url().match(tilePattern);if(match)tiles.push({url:r.url(),status:r.status(),order:Number(match[1]),pixel:Number(match[2]),frame:Number(match[3])});});
  const fullSky=async(index:number)=>{await expect.poll(()=>new Set(tiles.filter(t=>t.status===200&&t.order===0&&t.frame===index).map(t=>t.pixel)).size,{timeout:45000}).toBe(12);await page.waitForTimeout(450);};
  await ready(page);await fullSky(29);await expect(page.getByLabel('Spectral Explorer')).toHaveAttribute('data-requested-frame','29');
  await expect(page.locator('.spectral-explorer output')).toHaveText('1.481 μm');
  const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());
  await page.waitForTimeout(1600);await layout(page,'global');await page.screenshot({path:directory+'spectral_global.png'});
  const signatures:{frame:number;pixels:number[]}[]=[];
  const capture=async(index:number)=>{
    await page.screenshot({path:directory+`spectral_frame${index}.png`});
    // Actual WebGL canvas, excluding labels/panels; a label-only change cannot pass.
    const pixels=await page.evaluate(async()=>{const source=document.querySelector<HTMLCanvasElement>('.aladin-imageCanvas')??document.querySelector<HTMLCanvasElement>('.aladin-container canvas')!;const c=document.createElement('canvas');c.width=100;c.height=32;const ctx=c.getContext('2d')!;ctx.drawImage(source,0,source.height*.2,source.width,source.height*.4,0,0,100,32);return [...ctx.getImageData(0,0,100,32).data];});
    signatures.push({frame:index,pixels});
  };
  for(const index of [8,29,42,59,76,93]){
  await band(page);
    await page.getByRole('button',{name:new RegExp(`^Show band ${Math.floor(index/17)+1}:`)}).click();await applied(page,index);await fullSky(index);await capture(index);
    expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);expect(await page.locator('.aladin-container').count()).toBe(1);expect(await page.locator('[data-target]')).toHaveCount(6);
  }
  for(let i=1;i<signatures.length;i++){const a=signatures[i-1].pixels,b=signatures[i].pixels;expect(a.filter((v,j)=>j%4!==3&&Math.abs(v-b[j])>2).length).toBeGreaterThan(50);}
  // The first channel after the two blanks keeps index 52, not index 50.
  await slider(page,52);await fullSky(52);await capture(52);
  await page.setViewportSize({width:1366,height:768});await page.waitForFunction(()=>window.__sky!.engine.snapshot().size[0]===1366);await page.waitForTimeout(700);await layout(page,'laptop');await page.screenshot({path:directory+'spectral_laptop.png'});
  await page.getByRole('button',{name:'Zoom in',exact:true}).click();await page.getByRole('button',{name:'Zoom in',exact:true}).click();
  const zoomed=await page.evaluate(()=>window.__sky!.engine.getCamera());await slider(page,101);await page.waitForTimeout(1000);expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(zoomed);await page.screenshot({path:directory+'spectral_zoomed101.png'});
  // Pointer drag: even when held at an intermediate position no new channel is requested.
  const control=page.getByRole('slider',{name:'SPHEREx wavelength'}),box=(await control.boundingBox())!,start=requests.length;
  await page.mouse.move(box.x+box.width-5,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width*.15,box.y+box.height/2,{steps:15});await page.waitForTimeout(450);
  expect(requests.slice(start).filter(url=>tilePattern.test(url)&&!url.endsWith('_101.png'))).toEqual([]);
  await page.mouse.move(box.x+box.width*.65,box.y+box.height/2,{steps:15});const finalIndex=await control.inputValue();await page.mouse.up();await applied(page,SPECTRAL_CHANNELS[Number(finalIndex)].frameIndex);
  await slider(page,93);await applied(page,93);
  await fields(page);await page.getByRole('navigation',{name:'Prepared fields navigation'}).getByRole('button',{name:/Epsilon/}).click();
  await page.waitForFunction(()=>window.__analysis?.prepared&&window.__analysis.targetId==='epsilon_indi_b');await expect(page.getByLabel('Spectral Explorer')).toBeHidden();
  const scientificCamera=await page.evaluate(()=>window.__sky!.engine.getCamera());
  await page.getByRole('button',{name:'Blink A/B',exact:true}).click();await page.waitForTimeout(1000);await page.getByRole('button',{name:'Stop blink',exact:true}).click();
  await page.getByRole('button',{name:'Difference B minus A',exact:true}).click();await page.waitForFunction(()=>window.__sky!.engine.getCutoutStatus().kind==='difference'&&window.__sky!.engine.getCutoutStatus().loaded);
  expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(scientificCamera);expect(await page.evaluate(()=>window.__sky!.engine.getSpectralStatus().appliedFrame)).toBe(93);
  await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);await expect(page.getByRole('slider',{name:'SPHEREx wavelength'})).toHaveValue('91');
  expect(await page.evaluate(()=>window.__sky!.engine.getSpectralStatus().appliedFrame)).toBe(93);
  await page.setViewportSize({width:390,height:844});await page.waitForFunction(()=>window.__sky!.engine.snapshot().size[0]===390);await page.waitForTimeout(500);await layout(page,'mobile');await page.screenshot({path:directory+'spectral_mobile.png'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect(errors).toEqual([]);expect(requests.filter(url=>/\/TAP\b|\/ibe\/data\/spherex\//i.test(url))).toEqual([]);expect(tiles.some(t=>[50,51].includes(t.frame))).toBe(false);
  await writeFile(directory+'spectral_network.json',JSON.stringify({requests,tiles,pageErrors:errors,verifiedFrames:[8,29,42,52,59,76,93,101],canvasSignatures:signatures,passed:true},null,2));
});

test('rapid changes, failed availability and an incompatible survey keep the last channel honest',async({page})=>{
  await ready(page);
  // A late result is ignored after a newer request even if the server completes it.
  await page.route('**/Norder0/Dir0/Npix0_8.png',async route=>{await new Promise(r=>setTimeout(r,650));await route.continue().catch(()=>{});});
  await page.evaluate(()=>{void window.__sky!.engine.setSpectralFrame(8)});await page.waitForTimeout(40);await page.evaluate(()=>window.__sky!.engine.setSpectralFrame(76));await applied(page,76);await page.waitForTimeout(750);expect(await page.evaluate(()=>window.__sky!.engine.getSpectralStatus().appliedFrame)).toBe(76);
  await band(page);
  await page.route('**/Norder0/Dir0/Npix0_59.png',r=>r.fulfill({status:503,body:'Deliberate channel failure'}));await page.getByRole('button',{name:/^Show band 4:/}).click();
  await expect(page.locator('.spectral-status')).toContainText('previous map channel is retained');expect(await page.evaluate(()=>window.__sky!.engine.getSpectralStatus().appliedFrame)).toBe(76);
  await page.screenshot({path:directory+'spectral_error.png'});await page.getByRole('button',{name:'Return to last channel',exact:true}).click();await applied(page,76);
  await band(page);
  await page.unroute('**/Norder0/Dir0/Npix0_59.png');await page.getByRole('button',{name:/^Show band 4:/}).click();await applied(page,59);
  // Explicit metadata and image failures exercise honest rollback, not successful live 2MASS availability.
  await page.route('**/2MASS/K/properties',async route=>{await route.fulfill({status:200,body:'hips_service_url=https://alaskybis.cds.unistra.fr/2MASS/K\nhips_frame=equatorial\nhips_order=3\nhips_tile_width=512\nhips_tile_format=jpeg\ndataproduct_type=image\nhips_version=1.4\nobs_title=2MASS K\ncreator_did=ivo://CDS/P/2MASS/K'});});
  await page.route('**/2MASS/K/Norder0/Dir0/Npix0.jpg',r=>r.fulfill({status:503,body:'Controlled unavailable 2MASS image'}));
  await page.getByLabel('Background survey').selectOption('2mass');await expect(page.locator('.survey-notice')).toContainText('Keeping the previous sky background.');
  const state=await page.evaluate(()=>window.__sky!.engine.getSpectralStatus());expect(state.available).toBe(true);await expect(page.getByLabel('Background survey')).toHaveValue('spherex');
  await page.getByLabel('Background survey').selectOption('spherex');await page.waitForFunction(()=>window.__sky!.engine.getSpectralStatus().available);await applied(page,59);await expect(page.getByRole('slider',{name:'SPHEREx wavelength'})).toBeVisible();
});
