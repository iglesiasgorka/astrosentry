import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import type { SkyCatalog, SkyEngine, SkyTarget, SurveyStatus } from '../../types/sky';
import { createSkyEngine, HOME_CAMERA } from './SkyEngine';
import { flyTo } from './flyTo';
import { initialMapState, mapReducer } from './state';
import { TargetMarkers } from './TargetMarkers';
import { TemporalAnalysis } from '../analysis/TemporalAnalysis';
import { CameraReadout, SkyDetailStatus } from './CameraReadout';
import {SpectralExplorer} from './SpectralExplorer';
import {CoordinateSearch} from './CoordinateSearch';
import type {Region} from './coordinates';
import {Discoveries} from '../analysis/Discoveries';
import type {CandidateEvidence} from '../analysis/candidateModel';
import {validateCatalog} from '../../data/catalog';
import {GuidedDiscovery} from './GuidedDiscovery';
import {ExploreSidebar} from './ExploreSidebar';
import {investigationFov,scienceStatus} from './productLayout';

declare global { interface Window { __sky?:{engine:SkyEngine;targets:SkyTarget[];state:typeof initialMapState;select:(id:string)=>void;back:()=>void} } }

export function SkyMap({catalog}:{catalog:SkyCatalog}){
  const host=useRef<HTMLDivElement>(null),flight=useRef<AbortController|null>(null),version=useRef(0);
  const [engine,setEngine]=useState<SkyEngine|null>(null),[error,setError]=useState<string|null>(null);
  const [survey,setSurvey]=useState<SurveyStatus>({id:'spherex',name:'SPHEREx DR1 all-sky',state:'loading'});
  const [state,dispatch]=useReducer(mapReducer,initialMapState);
  const [interruption,setInterruption]=useState(0);
  const aboutDialog=useRef<HTMLElement>(null);
  const [about,setAbout]=useState(false),[fields,setFields]=useState(()=>window.innerWidth>700);
  const [runtimeTargets,setRuntimeTargets]=useState<SkyTarget[]>([]);
  const [restoredCandidate,setRestoredCandidate]=useState<CandidateEvidence|null>(null);
  const [guideOpen,setGuideOpen]=useState(false);
  const exploreSidebar=useRef(window.innerWidth>700);
  const toggleFields=()=>setFields(previous=>{const next=!previous;if(state.mode==='global')exploreSidebar.current=next;return next});
  const [searchOpen,setSearchOpen]=useState(()=>new URLSearchParams(window.location.search).has('ra'));
  const investigate=state.mode!=='global';
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){if(about)setAbout(false);else if(searchOpen)setSearchOpen(false);else if(guideOpen)setGuideOpen(false);else if(window.innerWidth<=700)setFields(false);}if(e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes((e.target as HTMLElement).tagName)&&!investigate){e.preventDefault();setSearchOpen(true);}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[about,searchOpen,guideOpen,investigate]);
  useEffect(()=>{if(!about)return;const previous=document.activeElement as HTMLElement|null;aboutDialog.current?.querySelector<HTMLButtonElement>('button')?.focus();const trap=(e:KeyboardEvent)=>{if(e.key!=='Tab')return;const nodes=[...aboutDialog.current!.querySelectorAll<HTMLElement>('button,a[href]')],first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}};window.addEventListener('keydown',trap);return()=>{window.removeEventListener('keydown',trap);previous?.focus()};},[about]);
  const allTargets=useMemo(()=>[...catalog.targets,...runtimeTargets],[catalog.targets,runtimeTargets]);
  const target=allTargets.find(t=>t.id===state.targetId)??null;
  useEffect(()=>{
    let canceled=false,instance:SkyEngine|undefined,unsubscribe=()=>{};
    createSkyEngine(host.current!,catalog.targets,setSurvey).then(async value=>{
      if(canceled){value.dispose();return;}
      instance=value;setEngine(value);await value.setSurvey('spherex');
    }).catch(e=>{if(!canceled)setError(String(e));});
    return()=>{canceled=true;flight.current?.abort();version.current++;unsubscribe();instance?.dispose();delete window.__sky;};
  },[catalog]);
  const select=useCallback(async(next:SkyTarget,restore?:CandidateEvidence)=>{
    if(!engine)return;
    setRestoredCandidate(restore??null);
    flight.current?.abort();const controller=new AbortController();flight.current=controller;const token=++version.current;
    engine.hideCutout();setSearchOpen(false);setFields(false);dispatch({type:'select',id:next.id,flight:token});
    void engine.prepareSequence(next).catch(()=>{/* The integrated panel reports local errors on arrival. */});
    // The map host stays mounted; allow its mode insets/native ResizeObserver to settle.
    await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));
    if(controller.signal.aborted||token!==version.current)return;
    const viewport=engine.snapshot().size;
    const completed=await flyTo(engine.getCamera(),{center:[next.center.raDeg,next.center.decDeg],
      fov:investigationFov(next.angularSizeDeg.width,next.angularSizeDeg.height,viewport)},camera=>engine.setCamera(camera),controller.signal,
      2500,window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    if(!completed||token!==version.current)return;
    dispatch({type:'arrive',flight:token});
  },[engine]);
  const back=useCallback(async()=>{
    if(!engine)return;
    flight.current?.abort();const controller=new AbortController();flight.current=controller;version.current++;
    dispatch({type:'back'});engine.hideCutout();setFields(exploreSidebar.current);
    await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));
    await flyTo(engine.getCamera(),HOME_CAMERA,camera=>engine.setCamera(camera),controller.signal,2300,window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  },[engine]);
  const locate=useCallback((p:Region)=>{
    if(!engine)return;flight.current?.abort();const controller=new AbortController();flight.current=controller;version.current++;
    dispatch({type:'back'});engine.hideCutout();setFields(false);
    void flyTo(engine.getCamera(),{center:[p.ra,p.dec],fov:p.size},camera=>engine.setCamera(camera),controller.signal,1800,window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  },[engine]);
  const openPrepared=useCallback((next:SkyTarget,restore?:CandidateEvidence)=>{
    if(!engine)return;
    if(!catalog.targets.some(t=>t.id===next.id)){engine.registerTarget(next);setRuntimeTargets(previous=>previous.some(t=>t.id===next.id)?previous:[...previous,next]);}
    void select(next,restore);
  },[engine,catalog,select]);
  const reopenCandidate=(record:CandidateEvidence)=>{
    const next=allTargets.find(t=>t.id===record.targetId)??validateCatalog({version:1,targets:[record.targetSnapshot]}).targets[0];
    for(const epoch of [record.a,record.b]){const frame=next.sequence?.frames.find(f=>f.id===epoch.frameId);
      if(!frame)throw new Error('Saved observations are no longer available.');
      if(epoch.sourceSha256&&frame.provenance?.sourceSha256&&epoch.sourceSha256!==frame.provenance.sourceSha256)throw new Error('The source data fingerprint changed. Export the archived evidence for review.');}
    openPrepared(next,record);
  };
  const interrupt=()=>{flight.current?.abort();version.current++;setInterruption(n=>n+1);if(state.mode==='flying'){engine?.hideCutout();dispatch({type:'interrupt'});}};
  useEffect(()=>{if(engine&&import.meta.env.DEV)window.__sky={engine,targets:allTargets,state,select:id=>{const t=allTargets.find(t=>t.id===id);if(t)void select(t);},back:()=>void back()};},[engine,allTargets,state,select,back]);
  return <main className={`sky-experience product-experience mode-${state.mode} ${fields?'sidebar-open':''}`} data-mode={state.mode}>
    <div className="sky-canvas" ref={host} aria-label="Interactive astronomical sky map" onPointerDown={interrupt} onWheel={interrupt}/>
    <div className="map-overlays">{engine&&<TargetMarkers engine={engine} targets={allTargets} selected={state.mode==='inspecting'?state.targetId:null} onSelect={t=>void select(t)}/>}</div>
    <header className="app-header"><a className="brand" href="#" onClick={event=>{event.preventDefault();void back();}} aria-label="SPHEREx Explorer, return to sky"><span className="brand-orbit" aria-hidden="true">✦</span><span>SPHEREx <strong>Explorer</strong></span></a>
      {!investigate&&<div className="header-explore-actions"><button className="fields-toggle" aria-label={`${allTargets.length} prepared fields`} aria-expanded={fields} onClick={toggleFields}><span aria-hidden="true">☷</span> Fields</button><button className="search-trigger" aria-label="Open Coordinate Search" aria-expanded={searchOpen} onClick={()=>setSearchOpen(!searchOpen)}><span aria-hidden="true">⌕</span><span>Enter coordinates<small>RA / Dec · search the real sky</small></span><kbd>/</kbd></button></div>}
      <div className="header-utilities"><div className="survey-selector"><span className={`status-dot ${survey.state}`}/><select aria-label="Background survey" value={survey.id==='2mass'?'2mass':'spherex'} onChange={event=>void engine?.setSurvey(event.target.value)} disabled={!engine}><option value="spherex">Sky background · SPHEREx DR1 · {survey.id==='spherex'&&survey.wavelengthUm?survey.wavelengthUm.toFixed(3)+' μm':'all-sky cube'}</option><option value="2mass">Sky background · 2MASS K · 2.16 μm</option></select></div><button className="about-button" onClick={()=>setAbout(true)}>About / Data sources <span aria-hidden="true">↗</span></button></div></header>
    {investigate&&target&&<header className="investigation-header"><button className="back-to-explore" aria-label="Back to Sky" onClick={()=>void back()}>← <span>Back to sky</span></button><div><span className="eyebrow">INVESTIGATE</span><h1>{target.name}</h1></div><button className="change-field" aria-label={`${allTargets.length} prepared fields`} aria-expanded={fields} onClick={toggleFields}>Change field⌄</button><span className="investigation-count">{target.sequence?.frames.length??1} observations</span><span className="science-status">{scienceStatus(target)}</span></header>}
    {!engine&&!error&&<div className="loading-state" role="status"><span className="loading-ring"/><strong>Opening the infrared sky</strong><span>Initializing the astronomical map…</span></div>}
    {error&&<div className="engine-error floating-panel" role="alert"><h2>The sky engine could not start</h2><p>This map needs WebGL2. Try a browser with hardware acceleration enabled.</p><details><summary>Technical details</summary>{error}</details><div className="local-inspection-links">{catalog.targets.map(t=><a key={t.id} href={`data/${t.assets.png}`}>{t.name} · local image</a>)}</div></div>}
    {engine&&fields&&!guideOpen&&<ExploreSidebar targets={allTargets} onSelect={t=>void select(t)} onGuide={()=>{setSearchOpen(false);setGuideOpen(true)}} onClose={()=>{setFields(false);if(state.mode==='global')exploreSidebar.current=false}}/>}
    {engine&&!investigate&&!fields&&!guideOpen&&<button className="investigation-cta" aria-label="Start your first investigation" onClick={()=>setGuideOpen(true)}>✦ Start your first investigation →</button>}
    {engine&&<nav className="map-controls" aria-label="Map navigation"><button aria-label="Zoom in" onClick={()=>{interrupt();engine.setCamera({...engine.getCamera(),fov:engine.getCamera().fov/1.7});}}>+</button><button aria-label="Zoom out" onClick={()=>{interrupt();engine.setCamera({...engine.getCamera(),fov:Math.min(360,engine.getCamera().fov*1.7)});}}>−</button><span/><button aria-label="Back to Sky" onClick={()=>void back()}>⌂</button></nav>}
    {state.mode==='flying'&&target&&<div className="flight-status" role="status"><span className="loading-ring small"/> Flying to {target.name}<button onClick={interrupt}>Cancel</button></div>}
    {state.mode==='inspecting'&&target&&engine&&<TemporalAnalysis key={target.id} target={target} engine={engine} interruption={interruption} onBack={()=>void back()} restoredCandidate={restoredCandidate?.targetId===target.id?restoredCandidate:undefined}/>}
    <SpectralExplorer engine={engine} survey={survey} hidden={investigate}/>
    {engine&&<CoordinateSearch targets={allTargets} hidden={investigate||!searchOpen||guideOpen} onLocate={locate} onPrepared={openPrepared} onGuide={()=>setGuideOpen(true)} onClose={()=>setSearchOpen(false)}/>}
    {guideOpen&&catalog.targets.find(t=>t.id==='epsilon_indi_b')&&<GuidedDiscovery target={catalog.targets.find(t=>t.id==='epsilon_indi_b')!} onExplore={()=>{const example=catalog.targets.find(t=>t.id==='epsilon_indi_b');if(example)void select(example)}} onClose={()=>{setGuideOpen(false);requestAnimationFrame(()=>document.querySelector<HTMLButtonElement>('.start-investigation,.investigation-cta')?.focus())}}/>}
    {engine&&<Discoveries onOpen={reopenCandidate}/>}
    {engine&&<SkyDetailStatus engine={engine}/>}
    {survey.message&&<div className="survey-notice" role="status">{survey.message}</div>}
    <footer className="map-footer"><span className="data-credit">Real sky imagery · <a href="https://aladin.cds.unistra.fr/AladinLite/" target="_blank" rel="noreferrer">Aladin Lite / CDS</a> · {survey.id==='2mass'?'2MASS / IPAC':'SPHEREx / NASA / Caltech-IPAC'}</span>
      {engine&&<CameraReadout engine={engine}/>}</footer>
    {about&&<div className="modal-backdrop" onClick={()=>setAbout(false)}><section ref={aboutDialog} className="about-dialog floating-panel" role="dialog" aria-modal="true" aria-labelledby="about-title" onClick={e=>e.stopPropagation()}><button className="dialog-close" aria-label="Close data sources" onClick={()=>setAbout(false)}>×</button><p className="eyebrow">ABOUT THE ATLAS</p><h2 id="about-title">A sky grounded in real data.</h2><p>SPHEREx Explorer is an independent NASA Space Apps Challenge project, not an official NASA product.</p><p>Explore real SPHEREx images through time and wavelength on one sky map. Enter coordinates, open a prepared field, then use Play, Blink or an available Difference. The global mosaic is separate from individual observations.</p><ul><li><a href="https://irsa.ipac.caltech.edu/Missions/spherex.html" target="_blank" rel="noreferrer">SPHEREx / NASA / Caltech-IPAC / IRSA</a></li><li><a href="https://caltech-ipac.github.io/irsa-tutorials/spherex-hipscube/" target="_blank" rel="noreferrer">SPHEREx DR1 all-sky spectral cube · official channel metadata</a></li><li><a href="https://aladin.cds.unistra.fr/AladinLite/" target="_blank" rel="noreferrer">Aladin Lite 3.8.2, developed by CDS, Strasbourg</a></li><li><a href="https://irsa.ipac.caltech.edu/Missions/2mass.html" target="_blank" rel="noreferrer">2MASS K infrared context, if selected</a></li></ul><p className="muted">Survey tiles and archive queries need internet access. New scientific preparation needs the optional Python service; prepared examples work without it. My Discoveries stores manual, unverified annotations in this browser and exports evidence for review; nothing is submitted to NASA. Original scientific FITS remain unchanged. A visual change, residual or manual mark is not a significant-motion or variability detection.</p></section></div>}
  </main>;
}
