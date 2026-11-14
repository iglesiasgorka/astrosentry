import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import type { SkyCatalog, SkyEngine, SkyTarget, SurveyStatus } from '../../types/sky';
import { createSkyEngine, HOME_CAMERA } from './SkyEngine';
import { flyTo, fitFieldFov } from './flyTo';
import { initialMapState, mapReducer } from './state';
import { TargetMarkers } from './TargetMarkers';
import { TemporalAnalysis } from '../analysis/TemporalAnalysis';
import { CameraReadout, SkyDetailStatus } from './CameraReadout';
import {SpectralExplorer} from './SpectralExplorer';

declare global { interface Window { __sky?:{engine:SkyEngine;targets:SkyTarget[];state:typeof initialMapState;select:(id:string)=>void;back:()=>void} } }

export function SkyMap({catalog}:{catalog:SkyCatalog}){
  const host=useRef<HTMLDivElement>(null),flight=useRef<AbortController|null>(null),version=useRef(0);
  const [engine,setEngine]=useState<SkyEngine|null>(null),[error,setError]=useState<string|null>(null);
  const [survey,setSurvey]=useState<SurveyStatus>({id:'spherex',name:'SPHEREx DR1 all-sky',state:'loading'});
  const [state,dispatch]=useReducer(mapReducer,initialMapState);
  const [interruption,setInterruption]=useState(0);
  const [about,setAbout]=useState(false),[fields,setFields]=useState(false);
  const target=catalog.targets.find(t=>t.id===state.targetId)??null;
  useEffect(()=>{
    let canceled=false,instance:SkyEngine|undefined,unsubscribe=()=>{};
    createSkyEngine(host.current!,catalog.targets,setSurvey).then(async value=>{
      if(canceled){value.dispose();return;}
      instance=value;setEngine(value);await value.setSurvey('spherex');
    }).catch(e=>{if(!canceled)setError(String(e));});
    return()=>{canceled=true;flight.current?.abort();version.current++;unsubscribe();instance?.dispose();delete window.__sky;};
  },[catalog]);
  const select=useCallback(async(next:SkyTarget)=>{
    if(!engine)return;
    flight.current?.abort();const controller=new AbortController();flight.current=controller;const token=++version.current;
    engine.hideCutout();setFields(false);dispatch({type:'select',id:next.id,flight:token});
    void engine.prepareSequence(next).catch(()=>{/* The integrated panel reports local errors on arrival. */});
    const viewport=engine.snapshot().size;
    const completed=await flyTo(engine.getCamera(),{center:[next.center.raDeg,next.center.decDeg],
      fov:fitFieldFov(next.angularSizeDeg.width,next.angularSizeDeg.height,viewport)},camera=>engine.setCamera(camera),controller.signal,
      2500,window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    if(!completed||token!==version.current)return;
    dispatch({type:'arrive',flight:token});
  },[engine]);
  const back=useCallback(async()=>{
    if(!engine)return;
    flight.current?.abort();const controller=new AbortController();flight.current=controller;version.current++;
    dispatch({type:'back'});engine.hideCutout();setFields(false);
    await flyTo(engine.getCamera(),HOME_CAMERA,camera=>engine.setCamera(camera),controller.signal,2300,window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  },[engine]);
  const interrupt=()=>{flight.current?.abort();version.current++;setInterruption(n=>n+1);if(state.mode==='flying'){engine?.hideCutout();dispatch({type:'interrupt'});}};
  useEffect(()=>{if(engine&&import.meta.env.DEV)window.__sky={engine,targets:catalog.targets,state,select:id=>{const t=catalog.targets.find(t=>t.id===id);if(t)void select(t);},back:()=>void back()};},[engine,catalog,state,select,back]);
  return <main className={`sky-experience mode-${state.mode}`} data-mode={state.mode}>
    <div className="sky-canvas" style={{width:'100%',height:'100%'}} ref={host} aria-label="Interactive astronomical sky map" onPointerDown={interrupt} onWheel={interrupt}/>
    {engine&&<TargetMarkers engine={engine} targets={catalog.targets} selected={state.mode==='inspecting'?state.targetId:null} onSelect={t=>void select(t)}/>}
    <header className="app-header"><a className="brand" href="#" onClick={event=>{event.preventDefault();void back();}} aria-label="SPHEREx Explorer, return to sky"><span className="brand-orbit" aria-hidden="true">✦</span><span>SPHEREx <strong>Explorer</strong></span><small>INFRARED SKY ATLAS</small></a>
      <div className="survey-selector"><span className={`status-dot ${survey.state}`}/><select aria-label="Background survey" value={survey.id==='2mass'?'2mass':'spherex'} onChange={event=>void engine?.setSurvey(event.target.value)} disabled={!engine}>
        <option value="spherex">SPHEREx DR1 · {survey.id==='spherex'&&survey.wavelengthUm?survey.wavelengthUm.toFixed(3)+' μm':'all-sky cube'}</option><option value="2mass">2MASS K · 2.16 μm</option></select></div>
      <button className="about-button" onClick={()=>setAbout(true)}>About / Data sources <span aria-hidden="true">↗</span></button></header>
    {!engine&&!error&&<div className="loading-state" role="status"><span className="loading-ring"/><strong>Opening the infrared sky</strong><span>Initializing the astronomical map…</span></div>}
    {error&&<div className="engine-error floating-panel" role="alert"><h2>The sky engine could not start</h2><p>This map needs WebGL2. Try a browser with hardware acceleration enabled.</p><details><summary>Technical details</summary>{error}</details><div className="local-inspection-links">{catalog.targets.map(t=><a key={t.id} href={`data/${t.assets.png}`}>{t.name} · local image</a>)}</div></div>}
    {engine&&state.mode==='global'&&<section className="sky-introduction"><p className="eyebrow"><span/> A REAL VIEW OF OUR UNIVERSE</p><h1>Follow your<br/>curiosity.</h1><p>Explore the infrared sky.<br/>Choose a marked field to look closer.</p><div className="navigation-hint"><span aria-hidden="true">↔</span> Drag to roam <i/> Scroll to zoom</div></section>}
    {engine&&<nav className="map-controls" aria-label="Map navigation"><button aria-label="Zoom in" onClick={()=>{interrupt();engine.setCamera({...engine.getCamera(),fov:engine.getCamera().fov/1.7});}}>+</button><button aria-label="Zoom out" onClick={()=>{interrupt();engine.setCamera({...engine.getCamera(),fov:Math.min(360,engine.getCamera().fov*1.7)});}}>−</button><span/><button aria-label="Back to Sky" onClick={()=>void back()}>⌂</button></nav>}
    {engine&&<button className="field-index-button" onClick={()=>setFields(!fields)} aria-expanded={fields}>⌖ <span>{catalog.targets.length} prepared fields</span></button>}
    {fields&&<nav className="field-index floating-panel" aria-label="Prepared fields navigation">{catalog.targets.map(t=><button key={t.id} onClick={()=>void select(t)}>{t.name}<span>↗</span></button>)}</nav>}
    {state.mode==='flying'&&target&&<div className="flight-status" role="status"><span className="loading-ring small"/> Flying to {target.name}<button onClick={interrupt}>Cancel</button></div>}
    {state.mode==='inspecting'&&target&&engine&&<TemporalAnalysis key={target.id} target={target} engine={engine} interruption={interruption} onBack={()=>void back()}/>}
    <SpectralExplorer engine={engine} survey={survey} hidden={state.mode==='inspecting'}/>
    {engine&&<SkyDetailStatus engine={engine}/>}
    {survey.message&&<div className="survey-notice" role="status">{survey.message}</div>}
    <footer className="map-footer"><span className="data-credit">Real sky imagery · <a href="https://aladin.cds.unistra.fr/AladinLite/" target="_blank" rel="noreferrer">Aladin Lite / CDS</a> · {survey.id==='2mass'?'2MASS / IPAC':'SPHEREx / NASA / Caltech-IPAC'}</span>
      {engine&&<CameraReadout engine={engine}/>}</footer>
    {about&&<div className="modal-backdrop" onClick={()=>setAbout(false)}><section className="about-dialog floating-panel" role="dialog" aria-modal="true" aria-labelledby="about-title" onClick={e=>e.stopPropagation()}><button className="dialog-close" aria-label="Close data sources" onClick={()=>setAbout(false)}>×</button><p className="eyebrow">ABOUT THE ATLAS</p><h2 id="about-title">A sky grounded in real data.</h2><p>SPHEREx Explorer is an independent NASA Space Apps Challenge project, not an official NASA product.</p><p>The global map is a survey mosaic. Each highlighted field opens one real, locally processed SPHEREx observation on its fixed celestial grid.</p><ul><li><a href="https://irsa.ipac.caltech.edu/Missions/spherex.html" target="_blank" rel="noreferrer">SPHEREx / NASA / Caltech-IPAC / IRSA</a></li><li><a href="https://caltech-ipac.github.io/irsa-tutorials/spherex-hipscube/" target="_blank" rel="noreferrer">SPHEREx DR1 all-sky spectral cube · official channel metadata</a></li><li><a href="https://aladin.cds.unistra.fr/AladinLite/" target="_blank" rel="noreferrer">Aladin Lite 3.8.2, developed by CDS, Strasbourg</a></li><li><a href="https://irsa.ipac.caltech.edu/Missions/2mass.html" target="_blank" rel="noreferrer">2MASS K infrared context, if selected</a></li></ul><p className="muted">Survey tiles need an internet connection. Local cutouts are visualization derivatives; original scientific FITS remain unchanged. Scientific classifications and limitations are preserved.</p></section></div>}
  </main>;
}
