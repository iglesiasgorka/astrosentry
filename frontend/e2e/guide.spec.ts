import {fields,coordinates,more,closeMore,openInspector,band} from './fixtures';
import {test,expect} from './fixtures';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const output=fileURLToPath(new URL('../../outputs/spx007b/',import.meta.url));await mkdir(output,{recursive:true});
test('a short guide opens real epochs without replacing the sky on desktop and mobile',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/explorer');await page.waitForFunction(()=>!!window.__sky);
 await page.screenshot({path:output+'final_global.png'});
 await page.getByRole('button',{name:'Start your first investigation',exact:true}).click();const guide=page.getByRole('region',{name:'Guided Discovery'});
 await expect(guide).toContainText('2025-04-29');await expect(guide).toContainText('2025-09-28');
 await guide.getByRole('button',{name:'Open real example',exact:true}).click();await page.waitForFunction(()=>window.__analysis?.prepared&&window.__sky!.engine.getCutoutStatus().loaded);
 const camera=await page.evaluate(()=>window.__sky!.engine.getCamera());await expect(guide).toContainText('Compare dates');
 await page.getByRole('button',{name:'Play observations',exact:true}).click();await page.waitForTimeout(1100);await page.getByRole('button',{name:'Pause playback',exact:true}).click();
 await guide.getByRole('button',{name:'Next guide step',exact:true}).click();await expect(guide).toContainText('1.920');await expect(guide).toContainText('0.31');
 await guide.getByRole('button',{name:'Minimize guide',exact:true}).click();await page.getByRole('button',{name:'Blink A/B',exact:true}).click();await page.waitForTimeout(1100);await page.getByRole('button',{name:'Stop blink',exact:true}).click();await guide.getByRole('button',{name:'Expand guide',exact:true}).click();
 await guide.getByRole('button',{name:'Next guide step',exact:true}).click();await page.getByRole('button',{name:'Difference B minus A',exact:true}).click();await page.waitForFunction(()=>window.__sky!.engine.getCutoutStatus().kind==='difference'&&window.__sky!.engine.getCutoutStatus().loaded);await page.screenshot({path:output+'guided_difference.png'});
 await guide.getByRole('button',{name:'Next guide step',exact:true}).click();await expect(guide).toContainText('not fitted centroids');expect(await page.evaluate(()=>window.__sky!.engine.getCamera())).toEqual(camera);
 await guide.getByRole('button',{name:'Finish guide',exact:true}).click();await expect(guide).toHaveCount(0);
 await page.getByRole('button',{name:'Back to Sky',exact:true}).last().click();await page.waitForFunction(()=>window.__sky!.engine.getCamera().fov>359.99);
 for(const [name,width,height] of [['laptop',1366,768],['mobile',390,844]] as const){await page.setViewportSize({width,height});await page.waitForFunction(width=>window.__sky!.engine.snapshot().size[0]===width,width);await page.waitForTimeout(300);await page.screenshot({path:output+`final_${name}.png`});expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);await page.getByRole('button',{name:'Start your first investigation',exact:true}).click();await page.screenshot({path:output+`guide_${name}.png`});await guide.getByRole('button',{name:'Close guide',exact:true}).click();}
 expect(await page.locator('.aladin-container').count()).toBe(1);expect(errors).toEqual([]);
 await writeFile(output+'guide_browser.json',JSON.stringify({realHistoricalExample:true,playBlinkDifference:true,fixedCamera:true,oneMap:true,desktopAndMobile:true,pageErrors:errors,passed:true},null,2));
});
