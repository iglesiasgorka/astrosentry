import {useEffect,useRef,useState} from 'react';
import type {SkyEngine,SkyTarget,LonLat} from '../../types/sky';
import {assetUrl} from '../../data/catalog';
import {downloadEvidence,makeEvidence,readEvidence,storeEvidence,validManualPixel,type CandidateEvidence,type ManualPosition} from './candidateModel';
import {separationArcsec} from '../sky/coordinates';
import '../../styles/candidates.css';
import {MapOverlay} from '../sky/MapOverlay';

type Mask={displayValid:string;scienceValid:string|null};
export function CandidateInspector({engine,target,a,b,current,layerReady,onEpoch,onClose,initialEvidence}:{engine:SkyEngine;target:SkyTarget;a:number;b:number;current:number;layerReady:boolean;onEpoch:(index:number)=>void;onClose:()=>void;initialEvidence?:CandidateEvidence}){
  const frames=target.sequence!.frames,frameA=frames[a],frameB=frames[b];
  const [step,setStep]=useState<'idle'|'a'|'b'|'review'>(initialEvidence?'review':'idle'),[pointA,setPointA]=useState<ManualPosition|null>(initialEvidence?.a.position??null),[pointB,setPointB]=useState<ManualPosition|null>(initialEvidence?.b.position??null),[notes,setNotes]=useState(initialEvidence?.notes??''),[error,setError]=useState(''),[saved,setSaved]=useState(!!initialEvidence),[ready,setReady]=useState(false);
  const [masks,setMasks]=useState<Record<string,Mask>>({}),[evidence,setEvidence]=useState<CandidateEvidence|null>(initialEvidence??null);
  const svg=useRef<SVGSVGElement>(null),down=useRef<LonLat|null>(null);
  useEffect(()=>{const refresh=()=>{if(!saved||!evidence)return;const existing=readEvidence(localStorage).records.find(r=>r.id===evidence.id);if(existing){setEvidence(existing);setNotes(existing.notes);}else setSaved(false);};window.addEventListener('spx-candidates-changed',refresh);return()=>window.removeEventListener('spx-candidates-changed',refresh);},[saved,evidence?.id]);
  useEffect(()=>{const controller=new AbortController();setMasks({});
    Promise.all([frameA,frameB].map(async frame=>{const r=await fetch(assetUrl(frame.assets.masks),{signal:controller.signal});if(!r.ok)throw new Error('Quality mask is unavailable.');return [frame.id,await r.json()] as const;})).then(rows=>setMasks(Object.fromEntries(rows))).catch(e=>{if(!controller.signal.aborted)setError(String(e));});
    return()=>controller.abort();
  },[frameA.assets.masks,frameB.assets.masks]);
  useEffect(()=>{setReady(false);if(!layerReady||!['a','b'].includes(step)||!masks[frameA.id]||!masks[frameB.id])return;const expected=step==='a'?frameA.id:frameB.id;
    const timeout=window.setTimeout(()=>{const status=engine.getCutoutStatus();setReady(status.loaded&&status.kind==='epoch'&&status.frameId===expected);},250);return()=>clearTimeout(timeout);
  },[step,layerReady,current,engine,frameA.id,frameB.id,masks]);
  useEffect(()=>{const host=document.querySelector<HTMLElement>('.sky-canvas');if(!host)return;
    const pointer=(e:PointerEvent)=>{down.current=[e.clientX,e.clientY]};
    const click=(event:MouseEvent)=>{
      if(!ready||!['a','b'].includes(step)||event.button!==0||!down.current||Math.hypot(event.clientX-down.current[0],event.clientY-down.current[1])>4)return;
      const expected=step==='a'?frameA:frameB,status=engine.getCutoutStatus();
      if(!status.loaded||status.kind!=='epoch'||status.frameId!==expected.id){setError('The required real observation is not currently visible.');return;}
      const mask=masks[expected.id];if(!mask){setError('Wait for the quality mask before marking.');return;}
      const bounds=host.getBoundingClientRect(),sky=engine.unproject([event.clientX-bounds.left,event.clientY-bounds.top]);
      try{if(!sky)throw new Error('Click inside the sky projection.');const position=validManualPixel(target,sky,mask.displayValid,mask.scienceValid);setError('');setSaved(false);
        if(step==='a'){setPointA(position);setStep('b');onEpoch(b);}else{setPointB(position);setStep('review');}
      }catch(error){setError(String(error));}
    };
    host.addEventListener('pointerdown',pointer,true);host.addEventListener('click',click,true);
    return()=>{host.removeEventListener('pointerdown',pointer,true);host.removeEventListener('click',click,true);};
  },[engine,target,step,ready,masks,frameA,frameB,b,onEpoch]);
  useEffect(()=>{const update=()=>{for(const [slot,point] of [['a',pointA],['b',pointB]] as const){const node=svg.current?.querySelector<SVGGElement>(`[data-candidate-mark="${slot}"]`),projected=point?engine.project([point.raDeg,point.decDeg]):null;if(node){node.style.display=projected?'':'none';if(projected)node.setAttribute('transform',`translate(${projected[0]} ${projected[1]})`);}}};update();return engine.subscribe(update);},[engine,pointA,pointB]);
  const start=()=>{setPointA(null);setPointB(null);setEvidence(null);setSaved(false);setError('');setStep('a');onEpoch(a);};
  const save=()=>{try{if(!pointA||!pointB)throw new Error('Mark both real epochs first.');const value=evidence?{...evidence,notes}:makeEvidence(target,frameA,frameB,pointA,pointB,notes);setEvidence(value);storeEvidence(localStorage,value);setSaved(true);setError('');window.dispatchEvent(new Event('spx-candidates-changed'));}catch(e){setError(`${String(e)} You can still export the marked evidence.`);}};
  const exportCurrent=(markdown=false)=>{if(pointA&&pointB)downloadEvidence(evidence?{...evidence,notes}:makeEvidence(target,frameA,frameB,pointA,pointB,notes),markdown);};
  return <>
    <MapOverlay><svg ref={svg} className="candidate-map-overlay" aria-label="Manual candidate sky annotations"><g data-candidate-mark="a"><path d="M -8 -8 L 8 8 M -8 8 L 8 -8"/><text x="10" y="-10">Manual A</text></g><g data-candidate-mark="b"><circle r="8"/><text x="10" y="16">Manual B</text></g></svg></MapOverlay>
    <section className="candidate-inspector floating-panel" aria-label="Candidate Inspector" data-marking={step==='a'||step==='b'}><header><div><span className="eyebrow">MANUAL EVIDENCE · NO DETECTION CLAIM</span><h3>Mark Candidate</h3></div><button aria-label="Close Candidate Inspector" onClick={onClose}>×</button></header>
      <p className="candidate-verdict">Unverified — Requires review</p>
      <div className="candidate-actions"><button aria-label="Close Candidate Inspector" onClick={onClose}>Cancel marking</button><button onClick={start}>{step==='idle'?'Start with epoch A':'Restart marks'}</button>{step==='b'&&<button onClick={()=>onEpoch(b)}>Show epoch B for marking</button>}{pointA&&pointB&&<button onClick={save}>Save investigation</button>}</div>
      <p role="status">{step==='idle'?'Choose two corresponding source positions on the real FITS layers.':step==='review'?'Both epochs marked. Review the coordinates and save or export.':ready?`Click a valid observed source in epoch ${step.toUpperCase()}. Dragging still pans the map.`:`Waiting for epoch ${step.toUpperCase()} and its real FITS layer.`}</p>
      <p className="candidate-epochs">A · {frameA.observation.timestampUtc} UTC<br/>B · {frameB.observation.timestampUtc} UTC</p>
      {[['A',pointA],['B',pointB]] .map(([label,p])=>{const point=p as ManualPosition|null;return <p key={String(label)} className="manual-position">{String(label)} RA/Dec: {point?`${point.raDeg.toFixed(8)}°, ${point.decDeg.toFixed(8)}°`:'Not marked'}</p>})}
      {pointA&&pointB&&<p className="manual-position">Manual separation: {separationArcsec([pointA.raDeg,pointA.decDeg],[pointB.raDeg,pointB.decDeg]).toFixed(4)} arcsec<br/>Formatting and click precision do not imply astrometric accuracy.</p>}
      <details className="candidate-source-details"><summary>Observation metadata, quality & warnings</summary>{[frameA,frameB].map((f,i)=><div key={f.id}><strong>{i===0?'A':'B'} · {f.observation.id}</strong><p>{f.observation.detector} · {f.observation.release.toUpperCase()} · {f.observation.wavelengthUm?.toFixed(6)??'Unavailable'} µm</p><p>Processing: {f.observation.processingVersion}</p><p>{f.warnings.join(' ')}</p></div>)}<p>{target.warnings.join(' ')}</p><p>Both annotation pixels require valid display and conservative science masks. This does not validate source identity or a motion measurement.</p></details>
      <p className="manual-position">Actual epoch separation: {(Math.abs(Date.parse(frameB.observation.timestampUtc.replace(/Z$/,'')+'Z')-Date.parse(frameA.observation.timestampUtc.replace(/Z$/,'')+'Z'))/86400000).toFixed(6)} days</p>
      <label className="candidate-notes">Investigation notes<textarea aria-label="Candidate notes" rows={3} maxLength={2000} value={notes} onChange={e=>{setNotes(e.target.value);setSaved(false)}}/></label>
      {pointA&&pointB&&<div className="candidate-actions"><button onClick={()=>exportCurrent()}>Export JSON</button><button onClick={()=>exportCurrent(true)}>Export Markdown</button></div>}
      {saved&&<p role="status">Saved locally in My Discoveries. Nothing was submitted to NASA.</p>}{error&&<p role="alert">{error}</p>}
      <p className="candidate-caution">Manual marks are annotations, not fitted centroids, significance or validated proper motion. Field context: {target.name}; this does not identify either mark or establish a new object. Unsaved marks clear when the field or pair changes.</p>
    </section>
  </>;
}
