import {test,expect,coordinates,fields,openInspector} from './fixtures';
import {fileURLToPath} from 'node:url';
import {mkdir} from 'node:fs/promises';
const out=fileURLToPath(new URL('../../outputs/landing_polish/',import.meta.url));
await mkdir(out,{recursive:true});
for(const viewport of [{width:1920,height:1080},{width:1366,height:768},{width:390,height:844}]){
  test(`home and explorer history ${viewport.width}`,async({page})=>{
    await page.setViewportSize(viewport);
    const scienceRequests:string[]=[];
    page.on('request',r=>{if(/\/data\/|\/hips\/|aladin.*\.js/.test(r.url()))scienceRequests.push(r.url());});
    await page.goto('/');await expect(page.locator('h1')).toHaveText('AstroSentry');
    await page.evaluate(()=>document.fonts.ready);
    await expect(page.getByRole('list',{name:'Explorer highlights'}).getByRole('listitem')).toHaveCount(3);
    expect(await page.locator('.landing').evaluate(n=>n.scrollWidth<=n.clientWidth&&n.scrollHeight<=n.clientHeight+1)).toBe(true);
    await page.waitForTimeout(500);expect(scienceRequests).toEqual([]);
    await expect(page.locator('.sky-canvas')).toHaveCount(0);
    await page.screenshot({path:out+`home-${viewport.width}.png`});
    if(viewport.width===390){
      await page.setViewportSize({width:390,height:420});
      await page.locator('.landing').evaluate(n=>{n.scrollTop=n.scrollHeight;});
      await expect(page.locator('.landing-footer')).toBeInViewport();
      await page.setViewportSize(viewport);
      await page.locator('.landing').evaluate(n=>{n.scrollTop=0;});
    }
    await page.getByRole('link',{name:'Start Exploring'}).click();await page.waitForFunction(()=>!!window.__sky);
    await expect(page).toHaveURL(/\/explorer$/);await expect(page.locator('.sky-canvas')).toHaveCount(1);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const home=page.getByRole('link',{name:'Home',exact:true});await expect(home).toBeVisible();
    const a=await home.boundingBox();expect(a!.x+a!.width).toBeLessThanOrEqual(viewport.width);
    await page.screenshot({path:out+`explorer-${viewport.width}.png`});
    await page.reload();await page.waitForFunction(()=>!!window.__sky);await expect(page.locator('.sky-canvas')).toHaveCount(1);
    await home.click();await expect(page.locator('.landing')).toBeVisible();
    await page.waitForFunction(()=>!window.__sky);await expect(page.locator('.sky-canvas')).toHaveCount(0);
    await page.goBack();await page.waitForFunction(()=>!!window.__sky);await expect(page).toHaveURL(/\/explorer$/);
    await page.goForward();await expect(page.locator('.landing')).toBeVisible();
    await page.emulateMedia({reducedMotion:'reduce'});
    expect(await page.locator('.landing').evaluate(n=>getComputedStyle(n).animationName)).toBe('none');
  });
}
test('legacy deep links and resume retain every parameter',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  const query='?ra=331.096331&dec=-56.800535&fov=0.15&detector=6&investigation=keep';
  await page.goto('/'+query);await page.waitForFunction(()=>!!window.__sky);
  await expect(page.getByLabel('Right Ascension',{exact:true})).toHaveValue('331.096331');
  await expect(page.getByLabel('Observation detector',{exact:true})).toHaveValue('6');
  await page.getByRole('link',{name:'Home',exact:true}).click();
  await page.getByRole('link',{name:'Start Exploring'}).click();await page.waitForFunction(()=>!!window.__sky);
  expect(new URL(page.url()).search).toBe(query);
  await page.reload();await page.waitForFunction(()=>!!window.__sky);
  await expect(page.getByLabel('Declination',{exact:true})).toHaveValue('-56.800535');
  await page.goto('/explorer/'+query);await page.waitForFunction(()=>!!window.__sky);
  await expect(page.getByLabel('Observation detector',{exact:true})).toHaveValue('6');
});
test('prepared tools and read-only backend replay remain independent of routing',async({page})=>{
  test.skip(!process.env.VITE_API_BASE_URL,'Separate static-mode run covers the backend-free configuration.');
  await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/explorer');await page.waitForFunction(()=>!!window.__sky);
  await coordinates(page);
  await page.getByLabel('Right Ascension',{exact:true}).fill('331.12');await page.getByLabel('Declination',{exact:true}).fill('-56.78');
  await page.getByRole('button',{name:'Search existing local FITS coverage only',exact:true}).click();
  await expect(page.locator('.availability-results')).toBeVisible();
  await page.getByRole('button',{name:'Prepare real timeline locally',exact:true}).click();
  await page.getByRole('button',{name:'Explore Timeline',exact:true}).click();
  await page.waitForFunction(()=>window.__analysis?.prepared&&window.__sky!.engine.getCutoutStatus().loaded);
  await page.evaluate(()=>window.__sky!.select('epsilon_indi_b'));
  await page.waitForFunction(()=>window.__analysis?.targetId==='epsilon_indi_b'&&window.__analysis.prepared&&window.__sky!.engine.getCutoutStatus().loaded);
  const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());
  await page.getByRole('button',{name:'Play observations',exact:true}).click();await page.waitForTimeout(1200);await page.getByRole('button',{name:'Pause playback',exact:true}).click();
  await page.getByRole('button',{name:'Blink A/B',exact:true}).click();await page.waitForTimeout(700);await page.getByRole('button',{name:'Stop blink',exact:true}).click();
  expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
  await page.getByRole('button',{name:'Difference B minus A',exact:true}).click();await expect(page.locator('.temporal-timeline')).toHaveAttribute('data-view','difference');
  await openInspector(page,'Candidate');await expect(page.locator('.candidate-inspector')).toBeVisible();
  await page.locator('.investigation-header').getByRole('button',{name:'Back to Sky',exact:true}).click();
  await fields(page);await page.getByRole('button',{name:'Start your first investigation',exact:true}).click();
  await expect(page.getByRole('region',{name:'Guided Discovery',exact:true})).toBeVisible();
  await page.screenshot({path:out+'tools-regression.png'});
});
test('spectral selection retains the existing camera and engine',async({page})=>{
  await page.goto('/explorer');await page.waitForFunction(()=>window.__sky?.engine.getSpectralStatus().available);
  const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());
  await page.evaluate(()=>{(window as any).__landingEngine=window.__sky!.engine;});
  await page.getByRole('slider',{name:'SPHEREx wavelength',exact:true}).fill('74');
  await page.waitForFunction(()=>window.__sky!.engine.getSpectralStatus().appliedFrame===76);
  expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
  expect(await page.evaluate(()=>window.__sky!.engine===(window as any).__landingEngine)).toBe(true);
});
test('static prepared fields survive an unavailable backend and rapid navigation',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.route('http://127.0.0.1:8765/**',r=>r.abort());
  await page.goto('/');await page.getByRole('link',{name:'Start Exploring'}).dblclick();await page.waitForFunction(()=>!!window.__sky);
  await expect(page.locator('.sky-canvas')).toHaveCount(1);
  await page.evaluate(()=>window.__sky!.select('epsilon_indi_b'));
  await page.waitForFunction(()=>window.__analysis?.prepared&&window.__sky!.engine.getCutoutStatus().loaded);
  await expect(page.getByRole('button',{name:'Play observations',exact:true})).toBeEnabled();
  await page.getByRole('link',{name:'Home',exact:true}).click();await expect(page.locator('.sky-canvas')).toHaveCount(0);
});
