/** Record real existing data and explicitly unverified demonstration annotations. */
import {chromium,expect} from '../frontend/node_modules/@playwright/test/index.mjs';
import {mkdir,writeFile,copyFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const out=fileURLToPath(new URL('../outputs/spx007a/',import.meta.url));
await mkdir(out+'recording',{recursive:true});
const executablePath=process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH??(existsSync('C:/Program Files/Google/Chrome/Application/chrome.exe')?'C:/Program Files/Google/Chrome/Application/chrome.exe':undefined);
const browser=await chromium.launch({executablePath,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context=await browser.newContext({viewport:{width:1536,height:864},recordVideo:{dir:out+'recording',size:{width:1280,height:720}}});
const page=await context.newPage(),video=page.video(),errors=[],requests=[],coarse=new Set(),began=Date.now();
page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>requests.push(r.url()));
page.on('response',r=>{if(r.status()===200&&r.url().includes('/Norder0/')){const m=r.url().match(/Npix\d+_29\.png/);if(m)coarse.add(m[0])}});
const shot=name=>page.screenshot({path:out+name+'.png'});
const open=async name=>{const nav=page.getByRole('navigation',{name:'Prepared fields navigation'});if(!await nav.isVisible())await page.getByRole('button',{name:'6 prepared fields',exact:true}).click();await nav.getByRole('button',{name:new RegExp('^'+name)}).click();await page.waitForFunction(()=>window.__analysis?.prepared&&window.__sky.engine.getCutoutStatus().loaded);await page.waitForTimeout(350)};
const tab=name=>page.getByRole('tab',{name,exact:true}).click();
const back=async()=>{await page.getByRole('button',{name:'Back to Sky',exact:true}).first().click();await page.waitForFunction(()=>window.__sky.engine.getCamera().fov>359.99);await page.waitForTimeout(100)};
let complete=false;
try{
  await page.goto(process.argv[2]??'http://127.0.0.1:5182');await page.waitForFunction(()=>!!window.__sky);await expect.poll(()=>coarse.size,{timeout:45000}).toBe(12);await page.waitForTimeout(700);await shot('explore_final');
  for(const [width,height,name] of [[1920,1080,'desktop'],[1366,768,'laptop'],[390,844,'mobile'],[1536,864,'wide_laptop']]){
    await page.setViewportSize({width,height});await page.waitForTimeout(500);await shot('explore_loaded_'+name);
  }
  await page.getByRole('button',{name:'Open Coordinate Search'}).click();await page.getByRole('button',{name:'Example: WISE 0855',exact:true}).click();await shot('coordinates_final');await page.getByRole('button',{name:'Locate in Sky',exact:true}).click();await page.waitForTimeout(1900);await page.keyboard.press('Escape');
  await open('Epsilon');const camera=await page.evaluate(()=>window.__sky.engine.getCamera());await shot('investigate_final');
  await tab('Motion');await shot('motion_final');await page.waitForTimeout(800);
  await page.getByRole('button',{name:'Play observations',exact:true}).click();await page.waitForTimeout(1900);await page.getByRole('button',{name:'Pause playback'}).click();await page.getByRole('button',{name:'Blink A/B',exact:true}).click();await page.waitForTimeout(1500);await page.getByRole('button',{name:'Stop blink'}).click();
  await page.getByRole('button',{name:'Difference B minus A'}).click();await page.waitForFunction(()=>window.__sky.engine.getCutoutStatus().kind==='difference'&&window.__sky.engine.getCutoutStatus().loaded);await page.waitForTimeout(350);await shot('difference_final');
  await page.locator('.timeline-options summary').click();await page.getByRole('button',{name:'Show epoch A'}).click();await page.locator('.timeline-options summary').click();
  await page.getByRole('button',{name:'Mark Candidate',exact:true}).click();const candidate=page.getByRole('region',{name:'Candidate Inspector'});await candidate.getByRole('button',{name:'Start with epoch A'}).click();
  for(const slot of ['A','B']){
    await expect(candidate.getByRole('status')).toContainText('Click a valid observed source in epoch '+slot);
    const point=await page.evaluate(()=>{const e=window.__sky.engine,t=window.__sky.targets.find(t=>t.id==='epsilon_indi_b'),p=t.sequence.frames[window.__analysis.index].measuredPosition,q=e.project([p.raDeg,p.decDeg]),r=document.querySelector('.sky-canvas').getBoundingClientRect();return [q[0]+r.left,q[1]+r.top]});await page.mouse.click(point[0],point[1]);
  }
  await page.getByLabel('Candidate notes',{exact:true}).fill('Recorded interface demonstration on real observations. Unverified manual annotations, not a discovery.');await candidate.getByRole('button',{name:'Save investigation'}).click();await shot('candidate_final');
  const download=page.waitForEvent('download');await candidate.getByRole('button',{name:'Export JSON',exact:true}).click();await (await download).saveAs(out+'demo-candidate.json');
  await page.getByRole('button',{name:/^My Discoveries/}).click();await shot('discoveries_final');await page.waitForTimeout(600);await page.getByRole('button',{name:'Close My Discoveries'}).click();
  expect(await page.evaluate(()=>window.__sky.engine.getCamera())).toEqual(camera);
  await back();await open('WISE');await tab('Motion');await shot('wise_final');await page.waitForTimeout(600);await back();await open('R Draconis');await tab('Brightness');await shot('brightness_final');await page.waitForTimeout(600);
  await back();await page.getByRole('button',{name:'Start your first investigation',exact:true}).click();await page.getByRole('button',{name:'Open real example',exact:true}).click();await page.waitForFunction(()=>window.__analysis?.prepared);await shot('guide_final');await page.waitForTimeout(800);
  expect(await page.locator('.aladin-container').count()).toBe(1);expect(errors).toEqual([]);expect(requests.filter(u=>/\/TAP\b|\/ibe\/data\/spherex\//i.test(u))).toEqual([]);complete=true;
  await writeFile(out+'recording_checks.json',JSON.stringify({passed:true,realEpochs:true,manualDemoOnly:true,oneMap:true,fixedCameraDuringAnalysis:true,noScientificAcquisitionRequests:true,pageErrors:errors,durationMs:Date.now()-began},null,2));
}finally{
  await context.close();await browser.close();if(video)await copyFile(await video.path(),out+(complete?'product-experience.webm':'incomplete-recording.webm'));
}
console.log('Actual product experience recorded; all checks passed.');
