import {fields,coordinates,more,closeMore,openInspector,band} from './fixtures';
import {test,expect} from './fixtures';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const output=fileURLToPath(new URL('../../outputs/spx007b/',import.meta.url));await mkdir(output,{recursive:true});
test('coordinates locate the exact challenge example and reopen a real cached fixed-grid region through read-only API fixtures',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/');await page.waitForFunction(()=>!!window.__sky);
  await coordinates(page);
  await page.getByRole('button',{name:'Example: WISE 0855',exact:true}).click();await page.getByRole('button',{name:'Locate in Sky',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.__sky!.engine.getCamera().center[0])).toBeCloseTo(133.79512916666666,7);
  expect((await page.evaluate(()=>window.__sky!.engine.getCamera())).center[1]).toBeCloseTo(-7.245147222222223,7);
  await page.getByLabel('Right Ascension',{exact:true}).fill('NaN');await page.getByRole('button',{name:'Locate in Sky',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Error');
  await page.getByLabel('Right Ascension',{exact:true}).fill('331.12');await page.getByLabel('Declination',{exact:true}).fill('-56.78');await page.getByLabel('Requested field width').selectOption('.05'.replace(/^\./,'0.'));
  await page.getByLabel('Observation detector').selectOption('6');
  await page.getByRole('button',{name:'Search existing local FITS coverage only',exact:true}).click();
  await expect(page.locator('.availability-results')).toContainText('Verified local original-FITS coverage subset');
  await expect(page.locator('.availability-results')).toContainText('6 real available observations');
  await page.screenshot({path:output+'coordinate_cache_search.png'});
  const before=await page.evaluate(()=>fetch('http://127.0.0.1:8765/api/health').then(r=>r.json()));
  await page.getByRole('button',{name:'Prepare real timeline locally',exact:true}).click();await expect(page.getByRole('button',{name:'Explore Timeline',exact:true})).toBeVisible({timeout:90000});
  await page.getByRole('button',{name:'Explore Timeline',exact:true}).click();await page.waitForFunction(()=>window.__analysis?.prepared&&window.__analysis.targetId.startsWith('region_')&&window.__sky!.engine.getCutoutStatus().loaded);
  const start=await page.evaluate(()=>({camera:window.__sky!.engine.getCamera(),target:window.__sky!.targets.find(t=>t.id===window.__analysis!.targetId)!}));
  expect(start.target.center).toEqual({raDeg:331.12,decDeg:-56.78});expect(start.target.dimensions).toEqual({width:30,height:30});expect(start.target.sequence!.motion).toBeNull();
  expect(start.target.sequence!.frames.every(f=>f.expectedPosition===null&&f.measuredPosition===null)).toBe(true);
  await page.screenshot({path:output+'dynamic_region.png'});await page.getByRole('button',{name:'Next observation',exact:true}).click();await page.waitForTimeout(350);
  expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(start.camera);expect(await page.locator('.aladin-container').count()).toBe(1);
  await page.getByRole('button',{name:'Play observations',exact:true}).click();await page.waitForTimeout(1100);await page.getByRole('button',{name:'Pause playback',exact:true}).click();
  expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(start.camera);
  const after=await page.evaluate(()=>fetch('http://127.0.0.1:8765/api/health').then(r=>r.json()));expect(after.attemptsUsed).toBe(before.attemptsUsed);
  await writeFile(output+'legacy_dynamic_browser.json',JSON.stringify({source:'Read-only replay of the real SPX-006 local-cache target; separate from the fresh SPX-007B flow',target:start.target,camera:start.camera,attemptsBefore:before.attemptsUsed,attemptsAfter:after.attemptsUsed,passed:true},null,2));
});
test('all five challenge targets and the additional field open real epochs with diagnostic inspectors',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/');await page.waitForFunction(()=>!!window.__sky);
  for(const [id,name] of [['wise0855','WISE 0855'],['r_dra','R Draconis'],['barnard',"Barnard's Star"],['epsilon_indi_b','Epsilon Indi B'],['rw_aur','RW Aurigae'],['m101','M101']]){
    await fields(page);await expect(page.getByRole('navigation',{name:'Prepared fields navigation'})).toContainText('Challenge Targets');
    await page.getByRole('navigation',{name:'Prepared fields navigation'}).getByRole('button',{name:new RegExp('^'+name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'))}).click();
    await page.waitForFunction(id=>window.__analysis?.targetId===id&&window.__analysis.prepared&&window.__sky!.engine.getCutoutStatus().loaded,id);
    const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());await page.screenshot({path:output+`challenge_${id}.png`});
    await page.getByRole('button',{name:'Next observation',exact:true}).click();await page.waitForTimeout(250);expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
    if(id==='wise0855'){await openInspector(page,'Motion');await expect(page.getByRole('region',{name:'Motion Inspector'})).toContainText('8.26640');await expect(page.getByRole('region',{name:'Motion Inspector'})).toContainText('Unavailable');expect(await page.locator('[data-mark^="measured-"]').count()).toBe(0);await page.screenshot({path:output+'wise0855_predictions.png'});await openInspector(page,'Overview');}
    if(id==='r_dra'){await expect(page.getByRole('button',{name:'Blink A/B',exact:true})).toBeDisabled();await openInspector(page,'Brightness');await expect(page.getByRole('region',{name:'Brightness Inspector'})).toContainText('No accepted');await page.screenshot({path:output+'r_dra_brightness.png'});await openInspector(page,'Overview');}
    await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);expect(await page.locator('.aladin-container').count()).toBe(1);
  }
});
