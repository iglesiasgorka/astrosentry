import {useEffect,useRef,useState} from 'react';
import '../../styles/coordinates.css';
import type {SkyTarget} from '../../types/sky';
import {API_BASE} from '../../data/apiConfig';
import {parseRegion,regionFromUrl,separationArcsec,type Region} from './coordinates';
import {findObservations,prepareObservations,getJob,cancelJob,validatePreparedTarget,type Availability,type PreparationJob} from './regionApi';

export function CoordinateSearch({targets,hidden,onLocate,onPrepared,onGuide,onClose}:{targets:SkyTarget[];hidden:boolean;onLocate:(p:Region)=>void;onPrepared:(t:SkyTarget)=>void;onGuide:()=>void;onClose:()=>void}){
  const [ra,setRa]=useState(''),[dec,setDec]=useState(''),[size,setSize]=useState(.1),[detector,setDetector]=useState(2),[count,setCount]=useState(4);
  const [result,setResult]=useState<Availability|null>(null),[job,setJob]=useState<PreparationJob|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const request=useRef<AbortController|null>(null),generation=useRef(0),jobId=useRef<string|null>(null),initial=useRef(false);
  const cancel=()=>{generation.current++;request.current?.abort();request.current=null;if(jobId.current){void cancelJob(jobId.current);jobId.current=null;}setBusy(false);};
  useEffect(()=>{if(hidden)cancel();},[hidden]);
  useEffect(()=>()=>{generation.current++;request.current?.abort();if(jobId.current)void cancelJob(jobId.current);},[]);
  useEffect(()=>{if(initial.current)return;initial.current=true;try{const p=regionFromUrl(window.location.search);if(p){setRa(String(p.ra));setDec(String(p.dec));setSize(p.size);setDetector(p.detector);onLocate(p);}}catch(e){setError(String(e));}},[onLocate]);
  const panel=useRef<HTMLElement>(null);
  useEffect(()=>{if(hidden)return;const previous=document.activeElement as HTMLElement|null;panel.current?.querySelector<HTMLInputElement>('input')?.focus();const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.stopPropagation();onClose()}};window.addEventListener('keydown',key);return()=>{window.removeEventListener('keydown',key);previous?.focus();};},[hidden]);
  const region=()=>parseRegion(ra,dec,size,detector);
  const changed=()=>{cancel();setResult(null);setJob(null);setError('');};
  const locate=()=>{try{const p=region();setError('');onLocate(p);const url=new URL(window.location.href);url.search=new URLSearchParams({ra:String(p.ra),dec:String(p.dec),fov:String(p.size),detector:String(p.detector)}).toString();window.history.replaceState(null,'',url);}catch(e){setError(String(e));}};
  const find=async(localOnly=false)=>{
    cancel();setResult(null);setJob(null);setError('');let p:Region;try{p=region();onLocate(p);}catch(e){setError(String(e));return;}
    const token=++generation.current,controller=new AbortController();request.current=controller;setBusy(true);
    try{const value=await findObservations(p,controller.signal,localOnly);if(token===generation.current)setResult(value);}catch(e){if(token===generation.current&&!controller.signal.aborted)setError(`${String(e)} This is not a no-data result. Existing fields and sky navigation remain available.`);}finally{if(token===generation.current)setBusy(false);}
  };
  const prepare=async()=>{
    if(!result)return;cancel();setError('');setBusy(true);const token=++generation.current,controller=new AbortController();request.current=controller;
    try{
      let value=await prepareObservations(result.id,count,controller.signal);if(token!==generation.current)return;jobId.current=value.id;setJob(value);const deadline=Date.now()+300000;
      while(value.status==='preparing'){
        await new Promise<void>((resolve,reject)=>{const abort=()=>{clearTimeout(timeout);reject(new DOMException('Canceled','AbortError'));};const timeout=window.setTimeout(()=>{controller.signal.removeEventListener('abort',abort);resolve();},1500);controller.signal.addEventListener('abort',abort,{once:true});});
        if(Date.now()>deadline){void cancelJob(value.id);throw new Error('Local preparation exceeded five minutes and cancellation was requested.');}
        value=await getJob(value.id,controller.signal);if(token!==generation.current)return;setJob(value);
      }
      jobId.current=null;if(value.target)validatePreparedTarget(value.target);
    }catch(e){if(token===generation.current&&!controller.signal.aborted)setError(String(e));}finally{if(token===generation.current)setBusy(false);}
  };
  let prepared:SkyTarget|undefined;
  try{const p=region();prepared=targets.filter(t=>separationArcsec([p.ra,p.dec],[t.center.raDeg,t.center.decDeg])<Math.min(t.angularSizeDeg.width,t.angularSizeDeg.height)*1800).sort((a,b)=>separationArcsec([p.ra,p.dec],[a.center.raDeg,a.center.decDeg])-separationArcsec([p.ra,p.dec],[b.center.raDeg,b.center.decDeg]))[0];}catch{/* Invalid form remains editable. */}
  return <section ref={panel} className="coordinate-search floating-panel" role="dialog" aria-modal="false" aria-label="Coordinate Search" hidden={hidden}>
    <header><div><span className="eyebrow">SPACE · FIND A REAL SKY REGION</span><h2>Coordinate Search</h2></div><div><button className="text-button guide-start" onClick={onGuide}>Start your first investigation</button><button className="text-button" aria-label="Close Coordinate Search" onClick={onClose}>×</button></div></header>
    <><form onSubmit={e=>{e.preventDefault();void find();}}>
      <div className="coordinate-inputs"><label>Right Ascension<input aria-label="Right Ascension" placeholder="133.795129 or 08h55m10.831s" value={ra} onChange={e=>{changed();setRa(e.target.value)}}/></label><label>Declination<input aria-label="Declination" placeholder="−7.245147 or −07d14m42.53s" value={dec} onChange={e=>{changed();setDec(e.target.value)}}/></label>
      <label>Field width<select aria-label="Requested field width" value={size} onChange={e=>{changed();setSize(Number(e.target.value))}}>{[.05,.1,.15,.2].map(n=><option key={n} value={n}>{n.toFixed(2)}°</option>)}</select></label><label>Detector<select aria-label="Observation detector" value={detector} onChange={e=>{changed();setDetector(Number(e.target.value))}}>{[1,2,3,4,5,6].map(n=><option key={n} value={n}>D{n}</option>)}</select></label></div>
      <div className="coordinate-actions"><button type="button" onClick={locate}>Locate in Sky</button><button type="submit" disabled={busy}>Find Observations</button><button type="button" className="text-button" onClick={()=>{changed();setRa('08h55m10.831s');setDec('-07d14m42.53s');setSize(.15);setDetector(6)}}>Example: WISE 0855</button>{API_BASE&&<button type="button" aria-label="Search existing local FITS coverage only" title="Verified local original-FITS subset, not a full IRSA search" className="text-button" disabled={busy} onClick={()=>void find(true)}>Local FITS only</button>}</div>
    </form>
    {busy&&<p role="status">{job?'Preparing real observations locally…':'Querying observation metadata…'} <button className="text-button" onClick={cancel}>Cancel</button></p>}
    {error&&<p className="coordinate-error" role="alert">{error}</p>}
    {prepared&&<button className="prepared-region" onClick={()=>onPrepared(prepared!)}>Open prepared field: {prepared.name}<small>Existing framing and observation wavelengths are retained.</small></button>}
    {result&&<div className="availability-results"><p>{result.count} real available observations · {result.visitCount} visit groups. Availability is not processed imagery.</p><p className="coordinate-hint">{result.source}</p>
      {result.count===0?<p>No observations in this response. A local-cache result does not establish absence from the full archive.</p>:<><div className="availability-table"><table><thead><tr><th>UTC</th><th>Observation</th><th>Detector / release</th><th>λ μm</th></tr></thead><tbody>{result.observations.slice(0,30).map(o=><tr key={o.id}><td>{o.timestampUtc.slice(0,10)}</td><td>{o.id}</td><td>{o.detector} / {o.release.toUpperCase()}</td><td>{o.wavelengthUm===null?'FITS required':o.wavelengthUm.toFixed(4)}</td></tr>)}</tbody></table></div><p className="coordinate-hint">Showing up to 30 rows. Exact local wavelengths require reading each FITS spectral WCS.</p>
      {API_BASE?<div className="coordinate-actions"><label>Cutouts<select aria-label="Maximum preparation observations" value={count} onChange={e=>setCount(Number(e.target.value))}>{[2,3,4].map(n=><option key={n}>{n}</option>)}</select></label><button disabled={busy||result.count<2} onClick={()=>void prepare()}>Prepare real timeline locally</button></div>:<p className="coordinate-hint">Metadata search is available directly from IRSA when browser access permits. Preparing a new timeline requires a configured processing API; no public backend is deployed.</p>}</>}
    </div>}
    {job&&<p role="status">{job.message}{job.status==='ready'&&job.target&&<button onClick={()=>onPrepared(job.target!)}>Explore Timeline</button>}</p>}
    <div className="coordinate-footer"><details className="coordinate-help"><summary>Coordinate formats & limits</summary><p>ICRS · decimal degrees or complete h:m:s / signed d:m:s. RA: [0, 360), Dec: [−90, +90]. Field width also controls the requested cutouts. Prepared-field framing is retained when opening existing data.</p></details><p className="processing-mode">{API_BASE?'Local processing configured · bounded demo':'Static mode · new processing needs a service'}</p></div>
    </>
  </section>;
}
