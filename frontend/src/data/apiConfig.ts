/** A configured processing service is optional; static map/fields remain independent. */
function configuredBase(){
  const raw=import.meta.env.VITE_API_BASE_URL?.trim();if(!raw)return null;
  try{const url=new URL(raw);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)return null;return url.href.replace(/\/$/,'');}catch{return null;}
}
export const API_BASE=configuredBase();

// Credentials and short-lived asset capabilities deliberately remain in memory.
let demoCode='';
let demoSession='';
let accessMode:string|null=null;
export function processingKnown(){return accessMode!==null;}
export function hasOperatorCode(){return !!demoCode;}
export function configureProcessing(health:{accessMode?:string}){accessMode=health.accessMode??'protected';}
export function anonymousAccess(){return accessMode==='anonymous-cached'&&!demoCode;}
export function setDemoSession(token:string){demoSession=token;}
export function needsDemoSession(){return anonymousAccess()&&!demoSession;}
export function forgetDemoSession(){demoSession='';}
const tickets=new Map<string,string>();
export function setDemoCode(value:string){demoCode=value;}
export function apiHeaders(json=false):Record<string,string>{return {...(json?{'Content-Type':'application/json'}:{}),...(demoCode?{Authorization:'Bearer '+demoCode}:demoSession?{Authorization:'Demo '+demoSession}:{})};}
export function rememberAssetAccess(value:unknown){
  if(!value||typeof value!=='object')return;
  const access=value as {jobId?:unknown;ticket?:unknown};
  if(typeof access.jobId==='string'&&/^[a-f0-9]{20}$/.test(access.jobId)&&typeof access.ticket==='string'&&/^\d+\.[a-f0-9]{64}$/.test(access.ticket)){
    if(tickets.size>=20)tickets.delete(tickets.keys().next().value!);tickets.set(access.jobId,access.ticket);
  }
}
export function dynamicAssetUrl(path:string){
  if(!API_BASE)throw new Error('This prepared region requires its processing service.');
  const token=tickets.get(path.split('/')[1]);
  return API_BASE+'/assets/'+path+(token?'?ticket='+encodeURIComponent(token):'');
}
