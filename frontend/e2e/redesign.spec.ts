import {test,expect,fields,coordinates,more,closeMore,openInspector,type Page} from './fixtures';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const out=fileURLToPath(new URL('../../outputs/spx007a/',import.meta.url));await mkdir(out,{recursive:true});
async function ready(page:Page){await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/');await page.waitForFunction(()=>!!window.__sky);}
async function choose(page:Page,name:string){await fields(page);await page.getByRole('navigation',{name:'Prepared fields navigation'}).getByRole('button',{name:new RegExp('^'+name)}).click();await page.waitForFunction(()=>!!window.__analysis?.prepared&&window.__sky!.engine.getCutoutStatus().loaded);await page.waitForTimeout(300);}
async function primaryBounds(page:Page){
  for(const name of ['Previous observation','Play observations','Next observation','Blink A/B','Difference B minus A','Mark Candidate']){
    const node=page.getByRole('button',{name,exact:true});const b=(await node.boundingBox())!,v=page.viewportSize()!;
    expect(b.x).toBeGreaterThanOrEqual(0);expect(b.x+b.width).toBeLessThanOrEqual(v.width);expect(b.y).toBeGreaterThanOrEqual(0);expect(b.y+b.height).toBeLessThanOrEqual(v.height);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
}

test('Explore has direct persistent coordinate entry, a collapsible field rail and keyboard dismissal',async({page})=>{
  await ready(page);await expect(page.getByRole('button',{name:'Start your first investigation',exact:true})).toBeVisible();await expect(page.getByRole('dialog',{name:'Coordinate Search'})).toBeHidden();
  await coordinates(page);await page.getByLabel('Right Ascension',{exact:true}).fill('08h55m10.831s');await page.getByLabel('Declination',{exact:true}).fill('-07d14m42.53s');await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'Open Coordinate Search'})).toBeFocused();await coordinates(page);await expect(page.getByLabel('Right Ascension',{exact:true})).toHaveValue('08h55m10.831s');
  await page.getByRole('button',{name:'Locate in Sky',exact:true}).click();await expect.poll(()=>page.evaluate(()=>window.__sky!.engine.getCamera().center[0])).toBeCloseTo(133.79512916666666,7);
  await page.keyboard.press('Escape');await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);
  await fields(page);await expect(page.getByRole('navigation',{name:'Prepared fields navigation'})).toContainText('Challenge Targets');await expect(page.getByRole('navigation',{name:'Prepared fields navigation'})).toContainText('Additional Fields');await page.getByRole('button',{name:'Collapse sidebar'}).click();await expect(page.getByRole('navigation',{name:'Prepared fields navigation'})).toHaveCount(0);
  await page.screenshot({path:out+'explore_collapsed.png'});await fields(page);await coordinates(page);await page.screenshot({path:out+'explore_coordinates.png'});
});

test('all six real fields have one inspector, appropriate tools and an unobstructed native footprint',async({page})=>{
  await page.setViewportSize({width:1536,height:864});await ready(page);const report=[];
  for(const [id,name] of [['epsilon_indi_b','Epsilon'],['wise0855','WISE'],['r_dra','R Draconis'],['rw_aur','RW Aurigae'],['barnard',"Barnard's Star"],['m101','M101']]){
    await choose(page,name);expect(await page.locator('.aladin-container').count()).toBe(1);expect(await page.locator('.unified-inspector').count()).toBe(1);
    const geometry=await page.evaluate(id=>{const e=window.__sky!.engine,t=window.__sky!.targets.find(t=>t.id===id)!,r=document.querySelector('.sky-canvas')!.getBoundingClientRect(),panel=document.querySelector('.unified-inspector')!.getBoundingClientRect();return {camera:e.getCamera(),size:e.snapshot().size,field:t.footprint.map(p=>e.project(p)!).map(p=>[p[0]+r.left,p[1]+r.top]),canvas:r.toJSON(),inspector:panel.toJSON()};},id);
    expect(geometry.size[1]).toBeGreaterThan(400);expect(Math.max(...geometry.field.map(p=>p[0]))).toBeLessThan(geometry.inspector.left-12);expect(Math.min(...geometry.field.map(p=>p[1]))).toBeGreaterThan(geometry.canvas.top+5);expect(Math.max(...geometry.field.map(p=>p[1]))).toBeLessThan(geometry.canvas.bottom-5);
    await page.screenshot({path:out+`investigate_${id}.png`});await page.getByRole('button',{name:'Next observation',exact:true}).click();await page.waitForTimeout(200);expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(geometry.camera);
    await openInspector(page,'Metadata');await expect(page.getByRole('region',{name:'Observation metadata'})).toContainText('Processing version');expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(geometry.camera);
    await openInspector(page,'Overview');await primaryBounds(page);report.push({id,...geometry});
  }
  await writeFile(out+'field_layouts.json',JSON.stringify(report,null,2));
});

test('a laptop investigation retains real playback, guarded Difference, readable motion and metadata in one inspector',async({page})=>{
  await page.setViewportSize({width:1366,height:768});await ready(page);await choose(page,'Epsilon');const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());
  await more(page);await page.getByLabel('Playback speed',{exact:true}).selectOption('400');await closeMore(page);await page.getByRole('button',{name:'Play observations'}).click();await page.waitForTimeout(900);await page.getByRole('button',{name:'Pause playback'}).click();await page.getByRole('button',{name:'Blink A/B',exact:true}).click();await page.waitForTimeout(900);await page.getByRole('button',{name:'Stop blink'}).click();
  await openInspector(page,'Motion');await expect(page.getByRole('region',{name:'Motion Inspector'})).toContainText('1.91982');await page.screenshot({path:out+'motion_laptop.png'});expect(await page.locator('.unified-inspector .target-preview').count()).toBe(0);
  await page.getByRole('button',{name:'Difference B minus A'}).click();await page.waitForFunction(()=>window.__sky!.engine.getCutoutStatus().kind==='difference'&&window.__sky!.engine.getCutoutStatus().loaded);await expect(page.getByRole('region',{name:'Difference inspection'})).toContainText('63.1%');await page.screenshot({path:out+'difference_laptop.png'});
  expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);await primaryBounds(page);await page.getByRole('button',{name:'Minimize analysis'}).click();await expect(page.locator('.unified-inspector')).toHaveCount(0);await page.getByRole('button',{name:'Expand analysis'}).click();expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
});

test('four responsive viewports keep the main actions on screen and one stable map instance',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(String(e)));await ready(page);
  for(const [width,height,label] of [[1920,1080,'desktop'],[1366,768,'laptop'],[1536,864,'wide_laptop'],[390,844,'mobile']] as const){
    await page.setViewportSize({width,height});await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);await page.waitForTimeout(300);await page.screenshot({path:out+`explore_${label}.png`});
    try{await choose(page,'Epsilon')}catch(error){await writeFile(out+'responsive_failure.json',JSON.stringify({label,errors,debug:await page.evaluate(()=>({state:window.__sky?.state,snapshot:window.__sky?.engine.snapshot(),cutout:window.__sky?.engine.getCutoutStatus(),analysis:window.__analysis}))},null,2));throw error;}await primaryBounds(page);await page.screenshot({path:out+`investigate_${label}.png`});
    await openInspector(page,'Motion');await page.screenshot({path:out+`inspector_${label}.png`});const rect=(await page.locator('.unified-inspector').boundingBox())!;expect(rect.y).toBeGreaterThanOrEqual(0);expect(rect.y+rect.height).toBeLessThanOrEqual(height);
    await page.keyboard.press('Escape');expect(await page.locator('.unified-inspector').count()).toBe(0);expect(await page.locator('.aladin-container').count()).toBe(1);
  }
});

test('a failed requested 2MASS survey retains the actual SPHEREx base and its spectral selection',async({page})=>{
  await ready(page);await page.waitForFunction(()=>window.__sky!.engine.getSpectralStatus().available);const initial=await page.evaluate(()=>window.__sky!.engine.getDiagnostics());
  await page.route('**/2MASS/K/properties',async route=>{await new Promise(r=>setTimeout(r,250));await route.fulfill({status:503,body:'Controlled unavailable metadata'});});
  await page.getByLabel('Background survey').selectOption('2mass');await expect(page.getByLabel('Background survey')).toHaveValue('spherex');await expect(page.locator('.survey-notice')).toContainText('Keeping the previous sky background');
  const after=await page.evaluate(()=>({diagnostics:window.__sky!.engine.getDiagnostics(),spectral:window.__sky!.engine.getSpectralStatus()}));expect(after.diagnostics.baseLayerId).toBe(initial.baseLayerId);expect(after.diagnostics.activeSurveyId).toBe('spherex');expect(after.spectral.available).toBe(true);await expect(page.getByRole('slider',{name:'SPHEREx wavelength'})).toBeVisible();
  await page.unroute('**/2MASS/K/properties');await page.route('**/2MASS/K/properties',route=>route.fulfill({status:200,body:'hips_service_url=https://alaskybis.cds.unistra.fr/2MASS/K\nhips_frame=equatorial\nhips_order=3\nhips_tile_format=jpeg\ndataproduct_type=image\nhips_version=1.4\nobs_title=2MASS K\ncreator_did=ivo://CDS/P/2MASS/K'}));await page.route('**/2MASS/K/Norder0/Dir0/Npix0.jpg',route=>route.fulfill({status:503,body:'Controlled unavailable coarse image'}));await page.getByLabel('Background survey').selectOption('2mass');await expect(page.locator('.survey-notice')).toContainText('Keeping the previous sky background');expect((await page.evaluate(()=>window.__sky!.engine.getDiagnostics())).baseLayerId).toBe(initial.baseLayerId);await page.screenshot({path:out+'survey_fallback.png'});
  await writeFile(out+'survey_fallback.json',JSON.stringify({before:initial,after,controlledMetadataAndImageFailure:true,noSuccessful2MassClaim:true,passed:true},null,2));
});


test('mobile candidate marking leaves the real source clickable and retains the fixed camera',async({page})=>{
  await page.setViewportSize({width:390,height:844});await ready(page);await choose(page,'Epsilon');const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());
  await page.getByRole('button',{name:'Mark Candidate',exact:true}).click();const panel=page.getByRole('region',{name:'Candidate Inspector'});await panel.getByRole('button',{name:'Start with epoch A'}).click();
  for(const slot of ['A','B']){
    await expect(panel.getByRole('status')).toContainText('Click a valid observed source in epoch '+slot);
    const point=await page.evaluate(()=>{const e=window.__sky!.engine,t=window.__sky!.targets.find(t=>t.id==='epsilon_indi_b')!,p=t.sequence!.frames[window.__analysis!.index].measuredPosition!,q=e.project([p.raDeg,p.decDeg])!,r=document.querySelector('.sky-canvas')!.getBoundingClientRect();return [q[0]+r.left,q[1]+r.top]});
    expect(await page.evaluate(([x,y])=>!!document.elementFromPoint(x,y)?.closest('.sky-canvas'),point)).toBe(true);
    await page.mouse.click(point[0],point[1]);
  }
  await expect(panel.getByRole('status')).toContainText('Both epochs marked');expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
  await page.getByLabel('Candidate notes',{exact:true}).fill('Mobile UI validation annotation on real data, not a discovery.');await panel.getByRole('button',{name:'Save investigation'}).click();await expect(panel).toContainText('Saved locally');await page.screenshot({path:out+'candidate_mobile.png'});
  await page.getByRole('button',{name:/^My Discoveries/}).click();await expect(page.getByRole('dialog',{name:'My Discoveries'})).toContainText('Unverified');await page.screenshot({path:out+'discoveries_mobile.png'});
});
