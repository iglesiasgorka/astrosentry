import {test as base,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve,sep} from 'node:path';
export {expect};
export type {Page} from '@playwright/test';
const project=fileURLToPath(new URL('../../',import.meta.url));

/** Read-only replay of prior real SPX-006 job data. No query, acquisition or job write. */
export const test=base.extend<{readonlyDynamic:void}>({readonlyDynamic:[async({page},use)=>{
  const publicJob=JSON.parse(await readFile(resolve(project,'outputs/spx006b/jobs/d2cc1ada1c28a2f19d2e/public.json'),'utf8'));
  const files=await import('node:fs/promises');
  const searches=await files.readdir(resolve(project,'outputs/spx006b/searches'));
  const records=await Promise.all(searches.filter(n=>n.endsWith('.json')).map(async n=>JSON.parse(await readFile(resolve(project,'outputs/spx006b/searches',n),'utf8'))));
  const cached=records.find(r=>r.parameters.ra===331.12&&r.parameters.dec===-56.78&&r.completeArchiveSearch===false);
  const {records:privateRecords,...availability}=cached;
  await page.route('http://127.0.0.1:8765/**',async route=>{
    const request=route.request(),url=new URL(request.url()),headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'GET, HEAD, POST, OPTIONS'};
    const json=(body:unknown,status=200)=>route.fulfill({status,headers,contentType:'application/json',body:JSON.stringify(body)});
    if(request.method()==='OPTIONS')return json({});
    if(url.pathname==='/api/health')return json({mode:'read-only-prior-job-fixture',attemptsUsed:8,acquisitionLimit:24});
    if(url.pathname==='/api/search'){
      const p=request.postDataJSON();if(p.localOnly&&p.ra===331.12&&p.dec===-56.78)return json(availability);
      return json({error:'SPX-007A does not run TAP or scientific preparation; this is a controlled UI error.'},502);
    }
    if(url.pathname==='/api/prepare'||url.pathname===`/api/jobs/${publicJob.id}`)return json(publicJob);
    if(url.pathname.endsWith('/cancel'))return json({status:'cancellation-requested'});
    if(url.pathname.startsWith('/assets/dynamic/')){
      const root=resolve(project,'outputs/spx006b/assets'),path=resolve(root,decodeURIComponent(url.pathname.slice('/assets/'.length)));
      if(!path.startsWith(root+sep))return json({error:'Unavailable'},404);
      return route.fulfill({status:200,headers,contentType:path.endsWith('.fits')?'application/fits':path.endsWith('.png')?'image/png':'application/json',body:await readFile(path)});
    }
    return json({error:'No fixture for this route'},404);
  });
  // This design phase explicitly forbids live TAP calls, including accidental test calls.
  await page.route('**/TAP/**',route=>route.abort('blockedbyclient'));
  await use();
},{auto:true}]});

export async function fields(page:import('@playwright/test').Page){
  const nav=page.getByRole('navigation',{name:'Prepared fields navigation'});
  if(!await nav.isVisible())await page.getByRole('button',{name:/^\d+ prepared fields$/}).click();
  await expect(nav).toBeVisible();
}
export async function coordinates(page:import('@playwright/test').Page){if(!await page.getByRole('dialog',{name:'Coordinate Search',exact:true}).isVisible())await page.getByRole('button',{name:'Open Coordinate Search'}).click();}
export async function more(page:import('@playwright/test').Page){const details=page.locator('.timeline-options');if(!await details.evaluate(n=>(n as HTMLDetailsElement).open))await details.locator('summary').click();}
export async function closeMore(page:import('@playwright/test').Page){const details=page.locator('.timeline-options');if(await details.evaluate(n=>(n as HTMLDetailsElement).open))await details.locator('summary').click();}
export async function openInspector(page:import('@playwright/test').Page,tab:string){await closeMore(page);if(await page.getByRole('button',{name:'Expand analysis',exact:true}).isVisible())await page.getByRole('button',{name:'Expand analysis',exact:true}).click();await page.getByRole('tab',{name:tab,exact:true}).click();}
export async function band(page:import('@playwright/test').Page){const details=page.locator('.spectral-band-picker');if(!await details.evaluate(n=>(n as HTMLDetailsElement).open))await details.locator('summary').click();}
