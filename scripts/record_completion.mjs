/** Record an actual local demonstration; manual marks are explicitly UI annotations. */
import {chromium,expect} from '../frontend/node_modules/@playwright/test/index.mjs';
import {mkdir,writeFile,copyFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const output=fileURLToPath(new URL('../outputs/spx006/',import.meta.url));await mkdir(output+'recording',{recursive:true});
const executablePath=process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH??(existsSync('C:/Program Files/Google/Chrome/Application/chrome.exe')?'C:/Program Files/Google/Chrome/Application/chrome.exe':undefined);
const browser=await chromium.launch({executablePath,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:output+'recording',size:{width:1152,height:800}}});
const page=await context.newPage(),video=page.video(),started=Date.now(),requests=[],errors=[],coarse=new Set();let firstImageMs=null;
page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>requests.push({url:r.url(),atMs:Date.now()-started}));
page.on('response',r=>{if(/\/Npix\d+_29\.png/.test(r.url())&&r.status()===200){firstImageMs??=Date.now()-started;if(r.url().includes('/Norder0/'))coarse.add(r.url().match(/Npix\d+_29/)[0])}});
let metrics;
try{
 await page.goto(process.argv[2]??'http://127.0.0.1:5180');await page.waitForFunction(()=>!!window.__sky);const engineReadyMs=Date.now()-started;
 await expect.poll(()=>coarse.size,{timeout:45000}).toBe(12);const twelveCoarseMs=Date.now()-started;await page.waitForTimeout(900);await page.screenshot({path:output+'final_global.png'});
 await page.getByRole('button',{name:'Example: WISE 0855',exact:true}).click();await page.getByRole('button',{name:'Locate in Sky',exact:true}).click();await page.waitForTimeout(1900);await page.screenshot({path:output+'coordinate_example.png'});
 const open=async name=>{await page.getByRole('button',{name:'6 prepared fields',exact:true}).click();await page.getByRole('navigation',{name:'Prepared fields navigation'}).getByRole('button',{name:new RegExp('^'+name)}).click();await page.waitForFunction(()=>window.__analysis?.prepared&&window.__sky.engine.getCutoutStatus().loaded)};
 const back=async()=>{await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky.engine.getCamera().fov>359.99)};
 await open('WISE 0855');await page.getByRole('button',{name:'Motion Inspector',exact:true}).click();await page.waitForTimeout(1200);await page.getByRole('button',{name:'Close Motion Inspector'}).click();await back();
 const firstStart=requests.length,t1=Date.now();await open('Epsilon');const firstVisitMs=Date.now()-t1;const camera=await page.evaluate(()=>window.__sky.engine.getCamera());
 await page.getByLabel('Playback speed',{exact:true}).selectOption('400');await page.getByRole('button',{name:'Play observations',exact:true}).click();await page.waitForTimeout(1800);await page.getByRole('button',{name:'Pause playback',exact:true}).click();
 await page.getByRole('button',{name:'Blink A/B',exact:true}).click();await page.waitForTimeout(1600);await page.getByRole('button',{name:'Stop blink',exact:true}).click();await page.getByRole('button',{name:'Motion Inspector',exact:true}).click();await page.waitForTimeout(1000);await page.getByRole('button',{name:'Close Motion Inspector'}).click();
 await page.getByRole('button',{name:'Difference B minus A',exact:true}).click();await page.waitForFunction(()=>window.__sky.engine.getCutoutStatus().kind==='difference'&&window.__sky.engine.getCutoutStatus().loaded);await page.waitForTimeout(1200);await page.getByRole('button',{name:'Show epoch A',exact:true}).click();
 await page.getByRole('button',{name:'Mark Candidate',exact:true}).click();const inspector=page.getByRole('region',{name:'Candidate Inspector'});await inspector.getByRole('button',{name:'Start with epoch A',exact:true}).click();
 for(const slot of ['A','B']){await expect(inspector.getByRole('status')).toContainText('Click a valid observed source in epoch '+slot);const p=await page.evaluate(()=>{const target=window.__sky.targets.find(t=>t.id==='epsilon_indi_b'),frame=target.sequence.frames[window.__analysis.index],p=frame.measuredPosition;return window.__sky.engine.project([p.raDeg,p.decDeg])});await page.mouse.click(p[0],p[1]);}
 await page.getByLabel('Candidate notes',{exact:true}).fill('Recorded UI demonstration on real data. Manual annotation, not a discovery.');await inspector.getByRole('button',{name:'Save investigation',exact:true}).click();await page.waitForTimeout(900);
 const downloadPromise=page.waitForEvent('download');await inspector.getByRole('button',{name:'Export Markdown',exact:true}).click();await (await downloadPromise).saveAs(output+'candidate-example.md');await page.getByRole('button',{name:'Close Candidate Inspector'}).click();
 expect(await page.evaluate(()=>window.__sky.engine.getCamera())).toEqual(camera);const firstFits=requests.slice(firstStart).filter(r=>/\/data\/.*\.fits$/.test(r.url)).length;
 await back();const secondStart=requests.length,t2=Date.now();await open('Epsilon');const secondVisitMs=Date.now()-t2,secondFits=requests.slice(secondStart).filter(r=>/\/data\/.*\.fits$/.test(r.url)).length;expect(secondFits).toBe(0);
 await back();await page.getByRole('button',{name:'Start your first investigation',exact:true}).click();await page.getByRole('region',{name:'Guided Discovery'}).getByRole('button',{name:'Open real example',exact:true}).click();await page.waitForFunction(()=>window.__analysis?.prepared);await page.waitForTimeout(1000);await page.screenshot({path:output+'guided_example.png'});
 const diagnostics=await page.evaluate(()=>window.__sky.engine.getDiagnostics());expect(diagnostics.layers.length).toBeLessThanOrEqual(12);expect(await page.locator('.aladin-container').count()).toBe(1);expect(errors).toEqual([]);
 metrics={engineReadyMs,engineInitializationMs:diagnostics.initializationMs,firstImageResponseMs:firstImageMs,twelveCoarseResponseMs:twelveCoarseMs,firstVisitMs,secondVisitMs,firstAnalysisFitsHttpRequests:firstFits,revisitNavigationFitsHttpRequests:secondFits,loadedLayerCount:diagnostics.layers.length,cacheLimit:12,oneMap:true,noScientificArchiveRequests:requests.every(r=>!(/\/TAP\b|\/ibe\/data\/spherex\//i.test(r.url))),pageErrors:errors,notes:'Single fresh browser run with software WebGL. Full-sky coarse responses are not final useful detail. Visit timings include the same deliberate 2.5s flight and already warmed local layers; the first HTTP count spans the full analysis including Difference, while the revisit count covers navigation only. These are not identical analysis workloads or a quantified speedup. No comparison with historical hardware/network conditions.',passed:true};
 await writeFile(output+'performance.json',JSON.stringify(metrics,null,2));
}finally{await context.close();await browser.close();if(video)await copyFile(await video.path(),output+'challenge-tour.webm')}
console.log(JSON.stringify(metrics,null,2));
