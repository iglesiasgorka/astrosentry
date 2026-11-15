import {useEffect,useRef,useState} from 'react';
import type {SkyEngine,SurveyStatus} from '../../types/sky';
import {channelAt,DEFAULT_SPECTRAL_POSITION,SPECTRAL_CHANNELS} from './surveys';
import type {SpectralStatus} from './spectralSwitch';

const initialStatus:SpectralStatus={available:false,requestedFrame:29,appliedFrame:null,phase:'unavailable'};
export function SpectralExplorer({engine,survey,hidden}:{engine:SkyEngine|null;survey:SurveyStatus;hidden:boolean}){
  const [position,setPosition]=useState(DEFAULT_SPECTRAL_POSITION),[status,setStatus]=useState(initialStatus);
  const dragging=useRef(false),timer=useRef(0),latest=useRef(position);
  useEffect(()=>{if(!engine)return;setStatus(engine.getSpectralStatus());return engine.subscribeSpectral(()=>setStatus(engine.getSpectralStatus()));},[engine]);
  useEffect(()=>{if(hidden||survey.id!=='spherex'){clearTimeout(timer.current);engine?.cancelSpectralChange();}},[hidden,survey.id,engine]);
  useEffect(()=>()=>clearTimeout(timer.current),[]);
  const request=(next:number,delay=0)=>{clearTimeout(timer.current);timer.current=window.setTimeout(()=>{void engine?.setSpectralFrame(channelAt(next).frameIndex).catch(()=>{/* Unavailable surveys disable the control. */});},delay);};
  const preview=(next:number)=>{clearTimeout(timer.current);engine?.cancelSpectralChange();latest.current=next;setPosition(next);if(!dragging.current)request(next,300);};
  const selected=channelAt(position),applied=SPECTRAL_CHANNELS.find(c=>c.frameIndex===status.appliedFrame);
  if(survey.id!=='spherex')return null;
  return <section className="spectral-explorer floating-panel" aria-label="Spectral Explorer" hidden={hidden} data-requested-frame={selected.frameIndex} data-applied-frame={status.appliedFrame??''} data-phase={status.phase}>
    <header><div><span className="eyebrow">SKY BACKGROUND · GLOBAL MOSAIC</span><h2>Spectral Explorer</h2></div><output htmlFor="spectral-slider" aria-live="polite">{selected.wavelengthUm.toFixed(3)} <small>μm</small></output></header>
    <label htmlFor="spectral-slider" className="spectral-channel">Band {selected.band} · channel {selected.channel} <span>frame {selected.frameIndex} · {SPECTRAL_CHANNELS.length} available channels</span></label>
    <input id="spectral-slider" aria-label="SPHEREx wavelength" aria-valuetext={`${selected.wavelengthUm.toFixed(3)} micrometers, band ${selected.band}, channel ${selected.channel}, frame ${selected.frameIndex}`} type="range" min="0" max={SPECTRAL_CHANNELS.length-1} step="1" value={position} disabled={!status.available} onPointerDown={()=>{dragging.current=true;clearTimeout(timer.current);engine?.cancelSpectralChange();}} onPointerUp={()=>{dragging.current=false;request(latest.current);}} onPointerCancel={()=>{dragging.current=false;request(latest.current,300);}} onChange={e=>preview(Number(e.target.value))} onBlur={()=>{if(!dragging.current&&status.available)request(latest.current);}}/>
    <div className="spectral-directions"><span>{Math.min(...SPECTRAL_CHANNELS.map(c=>c.wavelengthUm)).toFixed(2)} μm · shorter</span><span>longer · {Math.max(...SPECTRAL_CHANNELS.map(c=>c.wavelengthUm)).toFixed(2)} μm</span></div>
    <details className="spectral-band-picker"><summary>Jump to band</summary><div className="spectral-bands" role="group" aria-label="Instrumental bands">{[8,29,42,59,76,93].map(index=>{const c=SPECTRAL_CHANNELS.find(c=>c.frameIndex===index)!;return <button key={index} disabled={!status.available} aria-label={`Show band ${c.band}: ${c.wavelengthUm.toFixed(3)} micrometers`} aria-pressed={applied?.frameIndex===index} onClick={()=>{const next=SPECTRAL_CHANNELS.findIndex(c=>c.frameIndex===index);latest.current=next;setPosition(next);request(next);}}>Band {c.band}</button>;})}</div></details>
    <div className="spectral-status" role="status"><span className={`status-dot ${status.phase==='error'?'error':status.phase==='preparing'||!status.available?'loading':'ready'}`}/><span>{status.phase==='preparing'?`Checking requested channel · map remains ${applied?.wavelengthUm.toFixed(3)??'initializing'} μm`:status.phase==='error'?status.message:status.available?`Sky background wavelength ${applied?.wavelengthUm.toFixed(3)} μm · detail loads progressively`:'Initializing SPHEREx spectral mosaic…'}</span>{status.phase==='error'&&<><button onClick={()=>request(position)}>Retry</button>{applied&&<button onClick={()=>{const next=SPECTRAL_CHANNELS.findIndex(c=>c.frameIndex===applied.frameIndex);latest.current=next;setPosition(next);request(next);}}>Return to last channel</button>}</>}</div>
    <details className="spectral-note"><summary>Infrared visualization · methodology</summary><p>SPHEREx DR1 spectral mosaic. Wavelength exploration is for visualization and does not represent a time sequence or quantitative source photometry.</p><p>Applied channel identifies the native map layer; it does not certify that all visible detail has loaded. Individual FITS observations retain their own wavelengths.</p><a href="https://caltech-ipac.github.io/irsa-tutorials/spherex-hipscube/" target="_blank" rel="noreferrer">Official IRSA cube documentation ↗</a></details>
  </section>;
}
