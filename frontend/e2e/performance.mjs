// Bounded live-service timing probe; tile responses are explicit network proxies.
import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const label=process.argv[2]??'after';
const baseURL=process.env.SPX_BASE_URL??'http://127.0.0.1:5174';
const output=new URL('../../outputs/spx003b/',import.meta.url);
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH??'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
await page.addInitScript(()=>{
  window.__rafTimes=[];window.__longTasks=[];
  let last=performance.now();function frame(now){window.__rafTimes.push(now-last);last=now;requestAnimationFrame(frame)}requestAnimationFrame(frame);
  new PerformanceObserver(list=>window.__longTasks.push(...list.getEntries().map(e=>e.duration))).observe({type:'longtask',buffered:true});
});
const started=Date.now(),requests=[],responses=[];
page.on('request',r=>requests.push({url:r.url(),ms:Date.now()-started}));
page.on('response',r=>responses.push({url:r.url(),status:r.status(),ms:Date.now()-started}));
await page.goto(baseURL);
await page.waitForFunction(()=>!!window.__sky,null,{timeout:45000});
const engineReadyMs=Date.now()-started;
await page.waitForFunction(()=>performance.getEntriesByType('resource').some(e=>e.name.includes('Npix')&&e.name.includes('_29.png')),null,{timeout:45000});
// Wait for all twelve low-order tiles or a bounded 20-second observation window.
const waitStart=Date.now();
while(Date.now()-waitStart<20000&&new Set(responses.filter(r=>r.status===200&&r.url.includes('/Norder0/')).map(r=>r.url.match(/Npix\d+_29/)?.[0])).size<12)await page.waitForTimeout(250);
await page.waitForTimeout(500);
await page.screenshot({path:new URL(`performance-${label}-global.png`,output).pathname.replace(/^\/([A-Za-z]:)/,'$1')});
const visits=[];
for(let visit=0;visit<2;visit++){
  const start=Date.now(),requestStart=requests.length;
  const before=await page.evaluate(()=>({...window.__reactMetrics,raf:window.__rafTimes.length}));
  await page.evaluate(()=>window.__sky.select('epsilon_indi_b'));
  await page.waitForFunction(()=>window.__sky.state.mode==='inspecting'&&window.__sky.engine.getCutoutStatus().loaded,null,{timeout:30000});
  const localReadyMs=Date.now()-start;
  // Bounded five seconds observes progressive high-order tile traffic, not final completeness.
  await page.waitForTimeout(5000);
  const after=await page.evaluate(index=>({react:window.__reactMetrics,raf:window.__rafTimes.slice(index),camera:window.__sky.engine.snapshot(),engine:window.__sky.engine.getDiagnostics?.()}),before.raf);
  const flightRequests=requests.slice(requestStart),hips=flightRequests.filter(r=>r.url.includes('/hips/'));
  const sorted=after.raf.slice().sort((a,b)=>a-b);
  visits.push({visit:visit+1,localReadyMs,reactCommits:after.react.commits-before.commits,reactDurationMs:after.react.durationMs-before.durationMs,rafP50Ms:sorted[Math.floor(sorted.length*.5)],rafP95Ms:sorted[Math.floor(sorted.length*.95)],hipsRequestCount:hips.length,localFitsRequests:flightRequests.filter(r=>r.url.endsWith('.fits')&&!r.url.includes('/hips/')).length,lastHipsResponseMs:Math.max(0,...responses.filter(r=>r.ms>=start-started&&r.url.includes('/Npix')).map(r=>r.ms-(start-started))),diagnostics:after.engine});
  await page.evaluate(()=>window.__sky.back());await page.waitForFunction(()=>window.__sky.engine.getCamera().fov>359.99);await page.waitForTimeout(300);
}
const tiles=responses.filter(r=>r.url.includes('/Npix')&&r.status===200);
const resources=await page.evaluate(()=>({resources:performance.getEntriesByType('resource').filter(e=>e.name.includes('/hips/')||e.name.endsWith('.fits')).map(e=>({name:e.name,duration:e.duration,transferSize:e.transferSize,encodedBodySize:e.encodedBodySize})),longTasks:window.__longTasks}));
await writeFile(new URL(`performance-${label}.json`,output),JSON.stringify({label,engineReadyMs,firstTileResponseMs:tiles[0]?.ms,allLowOrderResponseMs:responses.filter(r=>r.url.includes('/Norder0/')&&r.status===200).slice(0,13).at(-1)?.ms,visits,requests,responses,...resources,limits:'Single cold browser context, two visits; SwiftShader and live-network variability. Tile-response times are proxies, not exact GPU presentation or complete useful-detail time.'},null,2));
console.log(JSON.stringify({label,engineReadyMs,firstTileResponseMs:tiles[0]?.ms,visits},null,2));
await browser.close();
