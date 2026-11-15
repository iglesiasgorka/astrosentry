/** Actual cross-origin SIA2 check; metadata only, no fixtures or acquisition. */
import {chromium} from '../frontend/node_modules/@playwright/test/index.mjs';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage(),url='https://irsa.ipac.caltech.edu/SIA?'+new URLSearchParams({POS:'CIRCLE 304.693508808 42.4436872991 0.0002777777777777778',COLLECTION:'spherex_dr1',MAXREC:'1000'});
 const consoleErrors=[];page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
 await page.goto('http://127.0.0.1:5182');
 const result=await page.evaluate(async url=>{try{const r=await fetch(url,{signal:AbortSignal.timeout(40000)}),text=await r.text(),doc=new DOMParser().parseFromString(text,'application/xml');return {status:r.status,bytes:text.length,tableData:doc.getElementsByTagNameNS('*','TABLEDATA').length,rows:doc.getElementsByTagNameNS('*','TR').length,fields:[...doc.getElementsByTagNameNS('*','FIELD')].map(f=>f.getAttribute('name'))};}catch(e){return {error:String(e)}}},url);
 await writeFile(new URL('../outputs/spx007b/sia2_browser_cors.json',import.meta.url),JSON.stringify({url,origin:'http://127.0.0.1:5182',...result,consoleErrors},null,2));console.log(result);
}finally{await browser.close()}
