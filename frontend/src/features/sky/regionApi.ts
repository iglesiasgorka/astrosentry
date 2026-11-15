import {API_BASE,apiHeaders,setDemoCode,rememberAssetAccess,anonymousAccess,needsDemoSession,setDemoSession,forgetDemoSession,configureProcessing,processingKnown,hasOperatorCode} from '../../data/apiConfig';
import {validateCatalog} from '../../data/catalog';
import type {SkyTarget} from '../../types/sky';
import type {Region} from './coordinates';
export interface AvailableObservation {id:string;timestampUtc:string;mjd:number;detector:string;release:string;processingVersion:string;visit:number;wavelengthUm:number|null}
export interface Availability {id:string;parameters:Region;count:number;visitCount:number;observations:AvailableObservation[];source:string;cache?:{status:string;archiveRetrievedAtUtc?:string|null;storedAtUtc?:string;origin:string}}
export interface PreparationJob {id:string;status:'preparing'|'ready'|'error'|'canceled'|'expired';message:string;target?:SkyTarget}
const cache=new Map<string,Availability>();
export function availabilityQuery(p:Region){
  return `SELECT 'https://irsa.ipac.caltech.edu/' || a.uri || '?center=${p.ra},${p.dec}d&size=${p.size}' AS uri, a.uri AS artifact_uri, p.time_bounds_lower, p.energy_bandpassname FROM spherex.artifact a JOIN spherex.plane p ON a.planeid = p.planeid WHERE 1 = CONTAINS(POINT('ICRS', ${p.ra}, ${p.dec}), p.poly) AND p.energy_bandpassname = 'SPHEREx-D${p.detector}' ORDER BY p.time_bounds_lower`;
}
/** Parse the documented VOTable TABLEDATA response, never guessing JSON contracts. */
export function parseAvailabilityVotable(text:string,p:Region):Availability{
  const doc=new DOMParser().parseFromString(text,'application/xml');
  if(doc.querySelector('parsererror'))throw new Error('IRSA returned invalid VOTable XML.');
  const infos=[...doc.getElementsByTagNameNS('*','INFO')];
  if(infos.some(n=>n.getAttribute('name')==='QUERY_STATUS'&&['ERROR','OVERFLOW'].includes(n.getAttribute('value')??'')))throw new Error('IRSA reported a query error or truncated results.');
  const table=doc.getElementsByTagNameNS('*','TABLE')[0];if(!table)throw new Error('IRSA returned no VOTable table.');
  const fields=[...table.getElementsByTagNameNS('*','FIELD')].map(n=>n.getAttribute('name'));
  if(!table.getElementsByTagNameNS('*','TABLEDATA').length)throw new Error('IRSA returned an unsupported VOTable encoding. Use the processing API; this is not a no-data result.');
  if(!['uri','time_bounds_lower','energy_bandpassname'].every(n=>fields.includes(n)))throw new Error('IRSA response is missing documented columns.');
  const chosen=new Map<string,{observation:AvailableObservation;rank:string}>();
  for(const row of [...table.getElementsByTagNameNS('*','TR')]){
    const cells=[...row.getElementsByTagNameNS('*','TD')].map(n=>n.textContent??''),value=(name:string)=>cells[fields.indexOf(name)];
    const url=new URL(value('uri')),match=url.pathname.match(/\/spherex\/(dr1|qr3|qr2)\/level2\/.*\/level2_(.+)D([1-6])_spx_(.+)\.fits$/),mjd=Number(value('time_bounds_lower'));
    if(url.hostname!=='irsa.ipac.caltech.edu'||!match||!value('time_bounds_lower').trim()||!Number.isFinite(mjd))throw new Error('Unrecognized observation identity or timestamp from IRSA.');
    const id=match[2],detector='SPHEREx-D'+match[3],key=id+detector;
    const rank=({dr1:3,qr3:2,qr2:1}[match[1]]??0)+':'+(match[4].match(/\d+/g)??[]).map(v=>v.padStart(10,'0')).join(':');
    const observation:AvailableObservation={id,timestampUtc:new Date((mjd-40587)*86400000).toISOString().replace(/Z$/,''),mjd,detector,release:match[1],processingVersion:match[4],visit:0,wavelengthUm:null};
    if(!chosen.has(key)||rank>chosen.get(key)!.rank)chosen.set(key,{observation,rank});
  }
  const observations=[...chosen.values()].map(r=>r.observation).sort((a,b)=>a.mjd-b.mjd);let visit=0,previous=-Infinity;
  for(const row of observations){if(row.mjd-previous>=1)visit++;row.visit=visit;previous=row.mjd;}
  if(observations.length>=5000)throw new Error('The query reached its row limit; narrow the region.');
  return {id:JSON.stringify(p),parameters:p,count:observations.length,visitCount:visit,observations,source:'Official IRSA TAP, browser VOTable query; availability is not processed imagery.'};
}
let sessionRequest:Promise<void>|null=null;
async function ensureSession(){
  if(!needsDemoSession())return;
  if(!sessionRequest)sessionRequest=(async()=>{
    const r=await fetch(API_BASE+'/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(10000)});
    const payload=await r.json();if(!r.ok)throw new Error(payload.error??'The public processing quota is unavailable. Static fields remain available.');
    setDemoSession(payload.session);
  })().finally(()=>{sessionRequest=null;});
  await sessionRequest;
}
async function jsonRequest(path:string,data?:unknown,signal?:AbortSignal,retry=true):Promise<any>{
  if(!API_BASE)throw new Error('A local processing API is not configured.');
  if(!processingKnown()&&!hasOperatorCode()){
    const health=await fetch(API_BASE+'/api/health',{signal:AbortSignal.any([signal??new AbortController().signal,AbortSignal.timeout(10000)])});
    if(!health.ok)throw new Error('Processing service is not ready. Static prepared fields remain available.');
    configureProcessing(await health.json());
  }
  await ensureSession();
  const r=await fetch(API_BASE+path,{method:data===undefined?'GET':'POST',headers:apiHeaders(data!==undefined),body:data===undefined?undefined:JSON.stringify(data),signal});
  const payload=await r.json();if(!r.ok){if(r.status===401){if(anonymousAccess()&&retry){forgetDemoSession();return jsonRequest(path,data,signal,false);}window.dispatchEvent(new Event('processing-locked'));}throw new Error(payload.error??`Processing service returned HTTP ${r.status}.`);}rememberAssetAccess(payload.assetAccess);return payload;
}
export async function unlockProcessing(code:string){setDemoCode(code);try{await jsonRequest('/api/access',{});}catch(error){setDemoCode('');throw error;}}
export async function refreshTargetAccess(target:SkyTarget){
  const path=target.assets.fits;
  if(path?.startsWith('dynamic/')){
    let job:PreparationJob;
    try{job=await getJob(path.split('/')[1],AbortSignal.timeout(10000));}
    catch(error){if(!anonymousAccess()||!target.preparation?.searchId)throw error;job=await prepareObservations(target.preparation.searchId,target.preparation.requestedCount??4,AbortSignal.timeout(10000));}
    if(job.status!=='ready')throw new Error(job.message);
  }
}
export async function findObservations(p:Region,signal:AbortSignal,localOnly=false):Promise<Availability>{
  const key=JSON.stringify(p)+':'+localOnly;if(cache.has(key)){const prior=cache.get(key)!;return {...prior,source:prior.source+' Reused from browser memory; original metadata provenance/date retained.'};}
  let result:Availability;
  if(API_BASE)result=await jsonRequest('/api/search',{...p,localOnly},signal);
  else{
    const url=new URL('https://irsa.ipac.caltech.edu/TAP/sync');url.search=new URLSearchParams({REQUEST:'doQuery',LANG:'ADQL',FORMAT:'votable',MAXREC:'5000',QUERY:availabilityQuery(p)}).toString();
    const r=await fetch(url,{signal:AbortSignal.any([signal,AbortSignal.timeout(45000)])});if(!r.ok)throw new Error(`IRSA metadata returned HTTP ${r.status}.`);
    const text=await r.text();if(text.length>8_000_000)throw new Error('Metadata response exceeds the display limit.');result=parseAvailabilityVotable(text,p);
  }
  if(cache.size>=10)cache.delete(cache.keys().next().value!);cache.set(key,result);return result;
}
export const prepareObservations=(searchId:string,count:number,signal:AbortSignal):Promise<PreparationJob>=>jsonRequest('/api/prepare',{searchId,count},signal);
export const getJob=(id:string,signal:AbortSignal):Promise<PreparationJob>=>jsonRequest('/api/jobs/'+id,undefined,signal);
export const cancelJob=(id:string)=>jsonRequest('/api/jobs/'+id+'/cancel',{}).catch(()=>{});
export function validatePreparedTarget(target:SkyTarget){return validateCatalog({version:1,targets:[target]}).targets[0]}
