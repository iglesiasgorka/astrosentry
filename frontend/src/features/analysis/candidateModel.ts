import type {LonLat,Observation,SequenceFrame,SkyTarget} from '../../types/sky';
import {separationArcsec} from '../sky/coordinates';
export const CANDIDATE_KEY='spherex-explorer-candidates-v1';
export interface ManualPosition {raDeg:number;decDeg:number;xFits:number;yFits:number}
export interface CandidateEpoch {frameId:string;observation:Observation;position:ManualPosition;sourceUrl:string|null;sourceSha256:string|null;assets:SequenceFrame['assets'];quality:unknown}
export interface CandidateEvidence {version:1;id:string;createdUtc:string;targetId:string;targetName:string;classification:'Unverified — Requires review';measurementKind:string;notes:string;a:CandidateEpoch;b:CandidateEpoch;separationArcsec:number;elapsedDays:number;warnings:string[];targetSnapshot:SkyTarget}
/** Inverse TAN and linear FITS matrix on the validated, undistorted fixed grids. */
export function worldToFits(target:SkyTarget,point:LonLat):[number,number]{
  const h=target.wcsHeader,n=(key:string,fallback=0)=>Number(h[key]??fallback),d=Math.PI/180;
  if(String(h.CTYPE1)!=='RA---TAN'||String(h.CTYPE2)!=='DEC--TAN'||Object.keys(h).some(k=>/^A_\d|^B_\d/.test(k)))throw new Error('Manual marking requires the prepared undistorted TAN grid.');
  const ra=point[0]*d,dec=point[1]*d,ra0=n('CRVAL1')*d,dec0=n('CRVAL2')*d,delta=ra-ra0;
  const denominator=Math.sin(dec0)*Math.sin(dec)+Math.cos(dec0)*Math.cos(dec)*Math.cos(delta);
  if(denominator<=0)throw new Error('Position is outside the prepared projection.');
  const east=Math.cos(dec)*Math.sin(delta)/denominator/d,north=(Math.cos(dec0)*Math.sin(dec)-Math.sin(dec0)*Math.cos(dec)*Math.cos(delta))/denominator/d;
  const a=h.CD1_1===undefined?n('CDELT1')*n('PC1_1',1):n('CD1_1'),b=h.CD1_2===undefined?n('CDELT1')*n('PC1_2'):n('CD1_2');
  const c=h.CD2_1===undefined?n('CDELT2')*n('PC2_1'):n('CD2_1'),e=h.CD2_2===undefined?n('CDELT2')*n('PC2_2',1):n('CD2_2'),det=a*e-b*c;
  if(!Number.isFinite(det)||det===0)throw new Error('Invalid fixed-grid pixel transform.');
  return [(e*east-b*north)/det+n('CRPIX1')-1,(-c*east+a*north)/det+n('CRPIX2')-1];
}
export function validManualPixel(target:SkyTarget,point:LonLat,display:string,science:string|null):ManualPosition{
  const [x,y]=worldToFits(target,point),width=target.dimensions.width,height=target.dimensions.height;
  if(!Number.isFinite(x+y)||x<-.5||y<-.5||x>=width-.5||y>=height-.5)throw new Error('Mark inside the observed FITS footprint.');
  const offset=Math.round(y)*width+Math.round(x),bit=(packed:string)=>{const bytes=atob(packed);return ((bytes.charCodeAt(offset>>3)>>(offset%8))&1)===1;};
  if(!science||!bit(display)||!bit(science))throw new Error('This pixel is invalid or lacks conservative science coverage. Choose a valid observed source pixel.');
  return {raDeg:((point[0]%360)+360)%360,decDeg:point[1],xFits:x,yFits:y};
}
export function makeEvidence(target:SkyTarget,a:SequenceFrame,b:SequenceFrame,pa:ManualPosition,pb:ManualPosition,notes:string):CandidateEvidence{
  if(a.id===b.id)throw new Error('Two distinct observations are required.');
  const epoch=(frame:SequenceFrame,position:ManualPosition):CandidateEpoch=>({frameId:frame.id,observation:frame.observation,position,
    sourceUrl:frame.provenance?.sourceUrl??null,sourceSha256:frame.provenance?.sourceSha256??null,assets:frame.assets,
    quality:{annotationPixel:'Display and conservative science mask valid when manually marked; not a centroid fit.',frameDiagnostics:frame.quality??frame.masks}});
  return {version:1,id:crypto.randomUUID(),createdUtc:new Date().toISOString(),targetId:target.id,targetName:target.name,
    classification:'Unverified — Requires review',measurementKind:'Manual sky annotations, not fitted astrometric centroids, significant motion or a validated proper motion.',notes:notes.slice(0,2000),
    a:epoch(a,pa),b:epoch(b,pb),separationArcsec:separationArcsec([pa.raDeg,pa.decDeg],[pb.raDeg,pb.decDeg]),
    elapsedDays:Math.abs(Date.parse(b.observation.timestampUtc.replace(/Z$/,'')+'Z')-Date.parse(a.observation.timestampUtc.replace(/Z$/,'')+'Z'))/86400000,
    warnings:[...new Set([...target.warnings,...a.warnings,...b.warnings,target.id.startsWith('region_')?'Manual marks establish no source identity.':'The field contains a known target; a manual mark is not automatically identified with it or a new source.','Click precision and formatted coordinates do not establish astrometric accuracy or significance.','Stored locally only; not submitted to NASA or a scientific community.'])],targetSnapshot:target};
}
type Store=Pick<Storage,'getItem'|'setItem'>;
function validEvidence(r:CandidateEvidence){
  if(!r||r.version!==1||!r.id||!r.targetSnapshot||r.classification!=='Unverified — Requires review'||typeof r.notes!=='string'||r.notes.length>2000||!Number.isFinite(r.separationArcsec)||r.separationArcsec<0||!Number.isFinite(r.elapsedDays)||r.elapsedDays<=0||!Array.isArray(r.warnings))return false;
  return [r.a,r.b].every(e=>e&&e.frameId&&e.observation?.id&&e.position&&[e.position.raDeg,e.position.decDeg,e.position.xFits,e.position.yFits].every(Number.isFinite)&&e.position.raDeg>=0&&e.position.raDeg<360&&Math.abs(e.position.decDeg)<=90&&Object.values(e.assets??{}).every(path=>typeof path==='string'&&!/^(?:[a-z]+:|\/)|\\|(?:^|\/)\.\.(?:\/|$)/i.test(path)))&&r.a.frameId!==r.b.frameId;
}
export function readEvidence(storage:Store):{records:CandidateEvidence[];error:string|null}{
  try{const raw=storage.getItem(CANDIDATE_KEY);if(!raw)return {records:[],error:null};const data=JSON.parse(raw);
    if(data.version!==1||!Array.isArray(data.records)||data.records.length>20||data.records.some((r:CandidateEvidence)=>!validEvidence(r)))throw new Error('Unsupported record');
    return {records:data.records,error:null};
  }catch{return {records:[],error:'Saved evidence is unreadable or incompatible. It has been retained without being overwritten.'};}
}
export function storeEvidence(storage:Store,record:CandidateEvidence){
  if(!validEvidence(record)||JSON.stringify(record).length>160000)throw new Error('Invalid or oversized investigation record.');
  const current=readEvidence(storage);if(current.error)throw new Error(current.error);
  const records=[record,...current.records.filter(r=>r.id!==record.id)];if(records.length>20)throw new Error('The local collection holds at most 20 investigations. Export or remove one first.');
  storage.setItem(CANDIDATE_KEY,JSON.stringify({version:1,records}));
}
export function removeEvidence(storage:Store,id:string){const current=readEvidence(storage);if(current.error)throw new Error(current.error);storage.setItem(CANDIDATE_KEY,JSON.stringify({version:1,records:current.records.filter(r=>r.id!==id)}));}
export function evidenceJson(record:CandidateEvidence){const {targetSnapshot,...portable}=record;return JSON.stringify({...portable,field:{center:targetSnapshot.center,wcsHeader:targetSnapshot.wcsHeader,dimensions:targetSnapshot.dimensions}},null,2);}
export function evidenceMarkdown(record:CandidateEvidence){return `# Manual candidate evidence\n\n${record.classification}\n\n${record.measurementKind}\n\nField: ${record.targetName}\n\nA: ${record.a.observation.id}, ${record.a.observation.timestampUtc} UTC\n\nB: ${record.b.observation.id}, ${record.b.observation.timestampUtc} UTC\n\nManual separation: ${record.separationArcsec.toFixed(6)} arcsec over ${record.elapsedDays.toFixed(6)} days.\n\nNotes: ${record.notes}\n\n## Reproducible evidence\n\n\`\`\`json\n${evidenceJson(record)}\n\`\`\`\n`;}
export function downloadEvidence(record:CandidateEvidence,markdown=false){const blob=new Blob([markdown?evidenceMarkdown(record):evidenceJson(record)],{type:markdown?'text/markdown':'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`spherex-candidate-${record.id}.${markdown?'md':'json'}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
