/** Explicit controlled UI failure/empty fixtures, separate from real acquisition evidence. */
import {chromium,expect} from '../frontend/node_modules/@playwright/test/index.mjs';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const out=new URL('../outputs/spx007b/',import.meta.url);
try{
 const page=await browser.newPage({viewport:{width:1366,height:768},reducedMotion:'reduce'});let empty=false;
 await page.route('http://127.0.0.1:8766/api/search',route=>{
  const headers={'Access-Control-Allow-Origin':'http://127.0.0.1:5184','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'POST, OPTIONS'};
  if(route.request().method()==='OPTIONS')return route.fulfill({status:204,headers});
  const p=route.request().postDataJSON();return route.fulfill({status:empty?200:503,headers,contentType:'application/json',body:JSON.stringify(empty?{id:'0'.repeat(20),parameters:p,count:0,visitCount:0,observations:[],source:'Controlled empty fixture for UI validation only; not a measured absence from IRSA.'}:{error:'Controlled metadata service failure; this is not a no-data result.'})});
 });
 await page.goto('http://127.0.0.1:5184');await page.waitForFunction(()=>!!window.__sky);await page.getByRole('button',{name:'Open Coordinate Search'}).click();await page.getByLabel('Right Ascension',{exact:true}).fill('304.693508808');await page.getByLabel('Declination',{exact:true}).fill('42.4436872991');await page.getByRole('button',{name:'Find Observations',exact:true}).click();await expect(page.getByRole('alert')).toContainText('not a no-data result');await page.screenshot({path:new URL('controlled_service_error.png',out).pathname.replace(/^\/(\w:)/,'$1')});
 empty=true;await page.getByRole('button',{name:'Find Observations',exact:true}).click();await expect(page.locator('.availability-results')).toContainText('0 real available observations');await expect(page.getByRole('button',{name:'Prepare real timeline locally'})).toHaveCount(0);await page.screenshot({path:new URL('controlled_empty_response.png',out).pathname.replace(/^\/(\w:)/,'$1')});
 await writeFile(new URL('controlled_api_states.json',out),JSON.stringify({passed:true,fixtures:true,serviceErrorDistinctFromEmpty:true,noPreparationOnEmpty:true,scientificAcquisitions:0,notARealArchiveAbsenceClaim:true},null,2));console.log('Controlled UI service-error/empty distinction passed; no archive inference.');
}finally{await browser.close()}
