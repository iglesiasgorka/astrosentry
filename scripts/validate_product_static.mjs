/** Verify the actual no-API frontend; controlled archive failures are UI tests only. */
import {chromium,expect} from '../frontend/node_modules/@playwright/test/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {existsSync} from 'node:fs';
const directory=fileURLToPath(new URL('../outputs/spx007a/',import.meta.url));await mkdir(directory,{recursive:true});
const url=process.argv[2]??'http://127.0.0.1:5173';
const executablePath=process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH??(existsSync('C:/Program Files/Google/Chrome/Application/chrome.exe')?'C:/Program Files/Google/Chrome/Application/chrome.exe':undefined);
const browser=await chromium.launch({executablePath,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage({viewport:{width:1366,height:768},reducedMotion:'reduce'}),api=[];
 page.on('request',r=>{if(r.url().includes('/api/'))api.push(r.url())});
 await page.goto(url+'/?ra=133.79512916666666&dec=-7.245147222222223&fov=0.15&detector=6');await page.waitForFunction(()=>!!window.__sky);
 await expect(page.locator('.processing-mode')).toContainText('Static mode');await expect(page.getByRole('button',{name:'Search existing local FITS coverage only'})).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>window.__sky.engine.getCamera().center[0])).toBeCloseTo(133.79512916666666,7);
 await page.route('**/TAP/sync?*',r=>r.fulfill({status:503,body:'Explicit controlled archive failure for UI validation'}));await page.getByRole('button',{name:'Find Observations',exact:true}).click();await expect(page.getByRole('alert')).toContainText('not a no-data result');await page.screenshot({path:directory+'static_archive_error.png'});
 await page.unroute('**/TAP/sync?*');
 const empty='<VOTABLE><RESOURCE><INFO name="QUERY_STATUS" value="OK"/><TABLE><FIELD name="uri"/><FIELD name="time_bounds_lower"/><FIELD name="energy_bandpassname"/><DATA><TABLEDATA/></DATA></TABLE></RESOURCE></VOTABLE>';
 await page.route('**/TAP/sync?*',r=>r.fulfill({status:200,contentType:'application/xml',body:empty}));await page.getByRole('button',{name:'Find Observations',exact:true}).click();await expect(page.locator('.availability-results')).toContainText('0 real available observations');
 await page.keyboard.press('Escape');if(!await page.getByRole('navigation',{name:'Prepared fields navigation'}).isVisible())await page.getByRole('button',{name:'6 prepared fields',exact:true}).click();await page.getByRole('navigation',{name:'Prepared fields navigation'}).getByRole('button',{name:/^Epsilon/}).click();await page.waitForFunction(()=>window.__analysis?.prepared&&window.__sky.engine.getCutoutStatus().loaded);
 const camera=await page.evaluate(()=>window.__sky.engine.getCamera());await page.getByRole('button',{name:'Next observation',exact:true}).click();await page.waitForTimeout(300);expect(await page.evaluate(()=>window.__sky.engine.getCamera())).toEqual(camera);await page.screenshot({path:directory+'static_no_backend.png'});expect(api).toEqual([]);
 await writeFile(directory+'static_mode_browser.json',JSON.stringify({staticConfiguration:true,deepLinkLocated:true,realPreparedEpochs:true,fixedCamera:true,noApiRequests:true,controlled503AndEmptyVotable:'UI fixtures only; not a successful live archive query or measured absence',passed:true},null,2));
 console.log('Static mode, URL coordinates, real epochs and controlled archive error/empty states passed.');
}finally{await browser.close()}
