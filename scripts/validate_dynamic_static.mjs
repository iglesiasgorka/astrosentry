/** Actual no-API fallback and small SPX-007B clarity changes on real local fields. */
import {chromium,expect} from '../frontend/node_modules/@playwright/test/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const out=fileURLToPath(new URL('../outputs/spx007b/',import.meta.url));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage({viewport:{width:1366,height:768},reducedMotion:'reduce'}),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>requests.push(r.url()));
 await page.goto('http://127.0.0.1:5182/?ra=304.693508808&dec=42.4436872991&fov=0.05&detector=2');await page.waitForFunction(()=>!!window.__sky);
 await expect(page.locator('.processing-mode')).toContainText('Creating a new sequence requires the processing service');await expect(page.getByRole('button',{name:'Find Observations',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'Prepare real timeline locally'})).toHaveCount(0);
 const link=new URL(await page.getByRole('link',{name:'Continue in IRSA Data Explorer ↗'}).getAttribute('href'));expect(link.searchParams.get('ra')).toBe('304.693508808');expect(link.searchParams.get('api')).toBe('spectral-images');
 await page.getByRole('button',{name:'Locate in Sky',exact:true}).click();await expect(page.getByLabel('Right Ascension',{exact:true})).toHaveValue('304.693509');await expect.poll(()=>page.evaluate(()=>window.__sky.engine.getCamera().center[0])).toBeCloseTo(304.693508808,9);expect(new URL(page.url()).searchParams.get('ra')).toBe('304.693508808');await page.screenshot({path:out+'static_newregion_fallback.png'});
 await page.keyboard.press('Escape');const fields=[];
 for(const name of ['Epsilon','WISE','R Draconis','RW Aurigae',"Barnard's Star",'M101']){
  const nav=page.getByRole('navigation',{name:'Prepared fields navigation'});if(!await nav.isVisible())await page.getByRole('button',{name:/^6 prepared fields$/}).click();await nav.getByRole('button',{name:new RegExp('^'+name)}).click();await page.waitForFunction(()=>window.__analysis?.prepared&&window.__sky.engine.getCutoutStatus().loaded);
  const before=await page.evaluate(()=>({camera:window.__sky.engine.getCamera(),frame:window.__sky.engine.getCutoutStatus().frameId}));await page.getByRole('button',{name:'Next observation',exact:true}).click();await page.waitForFunction(id=>window.__sky.engine.getCutoutStatus().loaded&&window.__sky.engine.getCutoutStatus().frameId!==id,before.frame);expect(await page.evaluate(()=>window.__sky.engine.getCamera())).toEqual(before.camera);fields.push(name);
  if(name==='Epsilon'){await page.getByRole('button',{name:'Difference B minus A',exact:true}).click();await page.waitForFunction(()=>window.__sky.engine.getCutoutStatus().loaded&&window.__sky.engine.getCutoutStatus().kind==='difference');await expect(page.locator('.residual-units')).toContainText(/MJy\s*\/\s*sr/);await page.locator('.residual-legend').scrollIntoViewIfNeeded();await expect(page.locator('.residual-units')).toBeInViewport();await page.screenshot({path:out+'difference_units_laptop.png'});}
 }
 await page.getByRole('button',{name:'Back to Sky',exact:true}).first().click();await page.waitForFunction(()=>window.__sky.engine.getCamera().fov>359.99);await expect(page.getByRole('heading',{name:'Spectral Explorer',exact:true})).toBeVisible();await page.setViewportSize({width:1536,height:864});await page.waitForTimeout(700);await page.screenshot({path:out+'spectral_title_desktop.png'});
 expect(requests.filter(u=>/\/api\/|\/TAP\b|\/SIA\?|\/ibe\/data\/spherex\//i.test(u))).toEqual([]);expect(errors).toEqual([]);expect(await page.locator('.aladin-container').count()).toBe(1);
 await writeFile(out+'static_fallback_browser.json',JSON.stringify({passed:true,actualNoApi:true,fields,fullPrecisionPreserved:true,externalArchiveLinkOnly:true,oneMap:true,pageErrors:errors,noScientificAcquisitions:true},null,2));console.log('Real static fallback, six fields, coordinate precision, units and title passed.');
}finally{await browser.close()}
