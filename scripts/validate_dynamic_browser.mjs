/** Real loopback API and real new FITS, never a replayed success or image fixture. */
import {chromium,expect} from '../frontend/node_modules/@playwright/test/index.mjs';
import {mkdir,readFile,writeFile,copyFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const out=fileURLToPath(new URL('../outputs/spx007b/',import.meta.url));await mkdir(out+'live-registration',{recursive:true});await mkdir(out+'recording',{recursive:true});
const samples=JSON.parse(await readFile(out+'live_samples.json','utf8'));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const run=out+'browser/live-'+new Date().toISOString().replace(/[:.]/g,'-')+'/';await mkdir(run,{recursive:true});
const context=await browser.newContext({viewport:{width:1536,height:864},recordVideo:{dir:run,size:{width:1280,height:720}}}),page=await context.newPage(),video=page.video();
const errors=[],requests=[],signatures=[];page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>requests.push({url:r.url(),method:r.method(),body:r.postData()}));
let passed=false;
try{
 const health=await (await context.request.get('http://127.0.0.1:8766/api/health')).json();expect(health.attemptsUsed).toBe(10);
 await page.goto('http://127.0.0.1:5184');await page.waitForFunction(()=>!!window.__sky);await page.evaluate(()=>{window.__firstEngine=window.__sky.engine});
 await page.getByRole('button',{name:'Open Coordinate Search'}).click();await page.getByLabel('Right Ascension',{exact:true}).fill('304.693508808');await page.getByLabel('Declination',{exact:true}).fill('42.4436872991');await page.getByLabel('Requested field width').selectOption('0.05');await page.getByLabel('Observation detector').selectOption('2');
 const searched=page.waitForResponse(r=>r.url().endsWith('/api/search'));await page.getByRole('button',{name:'Find Observations',exact:true}).click();const result=await (await searched).json();expect(result.count).toBe(57);expect(result.source).toContain('SIA2');expect(result.parameters.ra).toBe(304.693508808);
 await expect(page.locator('.availability-results')).toContainText('57 real available observations');await page.screenshot({path:out+'dynamic_search.png'});
 await page.getByLabel('Maximum preparation observations').selectOption('4');await page.getByRole('button',{name:'Prepare real timeline locally'}).click();await expect(page.getByRole('button',{name:'Explore Timeline',exact:true})).toBeVisible({timeout:120000});await page.screenshot({path:out+'dynamic_ready.png'});await page.getByRole('button',{name:'Explore Timeline',exact:true}).click();
 await page.waitForFunction(()=>window.__analysis?.prepared&&window.__sky.engine.getCutoutStatus().loaded);const camera=await page.evaluate(()=>window.__sky.engine.getCamera());
 expect(await page.locator('.aladin-container').count()).toBe(1);expect(await page.evaluate(()=>window.__firstEngine===window.__sky.engine)).toBe(true);
 const summary=await page.evaluate(()=>{const t=window.__sky.targets.find(t=>t.id===window.__analysis.targetId);return {id:t.id,sequence:t.sequence,dimensions:t.dimensions}});
 expect(summary.sequence.frames).toHaveLength(4);expect(summary.dimensions.width).toBe(30);expect(summary.sequence.motion).toBeNull();expect(summary.sequence.frames.every(f=>f.expectedPosition===null&&f.measuredPosition===null)).toBe(true);
 await page.getByRole('button',{name:'Play observations'}).click();await page.waitForTimeout(1700);await page.getByRole('button',{name:'Pause playback'}).click();await page.getByRole('button',{name:'Blink A/B',exact:true}).click();await page.waitForTimeout(1800);await page.getByRole('button',{name:'Stop blink'}).click();expect(await page.evaluate(()=>window.__sky.engine.getCamera())).toEqual(camera);
 await page.getByRole('tab',{name:'Metadata',exact:true}).click();await expect(page.getByRole('region',{name:'Observation metadata'})).toContainText('DR1');await page.screenshot({path:out+'dynamic_metadata.png'});await page.getByRole('tab',{name:'Overview',exact:true}).click();
 await page.locator('.timeline-options summary').click();await page.getByLabel('Observation group').selectOption('inspection');await page.locator('.timeline-options summary').click();await page.waitForFunction(()=>window.__analysis.prepared&&window.__analysis.frameIds.length===4);
 for(let i=0;i<4;i++){
  await page.getByRole('button',{name:new RegExp(`^Select observation ${i+1}:`)}).click();await page.waitForFunction(i=>window.__sky.engine.getCutoutStatus().loaded&&window.__sky.engine.getCutoutStatus().frameId===window.__analysis.frameIds[i],i);await page.waitForTimeout(450);
  const id=await page.evaluate(()=>window.__sky.engine.getCutoutStatus().frameId);
  const capture=await page.evaluate(points=>{const e=window.__sky.engine,t=window.__sky.targets.find(t=>t.id===window.__analysis.targetId),frame=t.sequence.frames.find(f=>f.id===e.getCutoutStatus().frameId),r=document.querySelector('.sky-canvas').getBoundingClientRect();return {frame,camera:e.snapshot(),cutout:e.getCutoutStatus(),samples:points.map(p=>{const q=e.project(p.sky);return {...p,screen:q?[q[0]+r.left,q[1]+r.top]:null}})}},samples[id]);
  await page.screenshot({path:out+`live-registration/frame${i}.png`});await writeFile(out+`live-registration/frame${i}_screen.json`,JSON.stringify(capture,null,2));
  signatures.push(await page.evaluate(()=>{const source=document.querySelector('.aladin-imageCanvas')??document.querySelector('.aladin-container canvas'),c=document.createElement('canvas');c.width=100;c.height=100;const ctx=c.getContext('2d');ctx.drawImage(source,source.width*.35,source.height*.25,source.width*.3,source.height*.5,0,0,100,100);return [...ctx.getImageData(0,0,100,100).data]}));expect(await page.evaluate(()=>window.__sky.engine.getCamera())).toEqual(camera);
 }
 await expect(page.getByRole('button',{name:'Difference B minus A',exact:true})).toBeDisabled();
 await page.locator('.timeline-options summary').click();await page.getByLabel('Observation group').selectOption('compatible');await page.locator('.timeline-options summary').click();
 for(let i=1;i<signatures.length;i++)expect(signatures[i].filter((v,j)=>j%4!==3&&Math.abs(v-signatures[i-1][j])>2).length).toBeGreaterThan(50);
 const after=await (await context.request.get('http://127.0.0.1:8766/api/health')).json();expect(after.attemptsUsed).toBe(health.attemptsUsed);expect(errors).toEqual([]);expect(requests.filter(r=>/\/TAP\b|\/SIA\?|\/ibe\/data\/spherex\//i.test(r.url))).toEqual([]);
 await page.screenshot({path:out+'dynamic_investigate.png'});passed=true;
 await writeFile(out+'dynamic_browser.json',JSON.stringify({passed:true,realApi:true,fixtures:false,metadataCache:'Successful live SIA2 search, reused by exact parameters',result,summary,camera,healthBefore:health,healthAfter:after,pageErrors:errors,requests,canvasSignatures:signatures,fixedCamera:true,oneEngine:true,noDynamicDifference:true},null,2));
}finally{await context.close();await browser.close();await copyFile(await video.path(),out+(passed?'dynamic-playback.webm':'dynamic-incomplete.webm'))}
console.log('Real new-region search, preparation, four rendered epochs, Play/Blink and metadata passed.');
