import {useEffect,useReducer,useRef,useState} from 'react';
import type {SkyEngine,SkyTarget} from '../../types/sky';
import {TargetPreview} from './TargetPreview';
import {initialPlayback,playbackReducer} from './playback';
import {MotionInspector} from './MotionInspector';
import {MotionOverlay} from './MotionOverlay';
import {BrightnessInspector} from './BrightnessInspector';

declare global {interface Window {__analysis?:{index:number;mode:string;prepared:boolean;targetId:string;pause:()=>void}}}
export function TemporalAnalysis({engine,target,onBack,interruption}:{engine:SkyEngine;target:SkyTarget;onBack:()=>void;interruption:number}){
  const frames=target.sequence?.frames??[],count=frames.length||1;
  const [playback,dispatch]=useReducer(playbackReducer,count,initialPlayback);
  const [layer,setLayer]=useState<'loading'|'ready'|'error'>('loading'),[prepared,setPrepared]=useState(false);
  const [error,setError]=useState(''),[visible,setVisible]=useState(true),[inspector,setInspector]=useState(false),[minimized,setMinimized]=useState(false);
  const generation=useRef(0);
  const frame=frames[playback.index];
  const displayed:SkyTarget=frame?{...target,observation:frame.observation,assets:frame.assets,warnings:[...new Set([target.sequence!.interpretation,...target.warnings,...frame.warnings])]}:target;
  useEffect(()=>{let canceled=false;
    engine.prepareSequence(target).then(()=>{if(!canceled)setPrepared(true)}).catch(e=>{if(!canceled)setError(`Some local epochs could not be prepared: ${String(e)}`)});
    return()=>{canceled=true;generation.current++;delete window.__analysis;};
  },[engine,target]);
  useEffect(()=>{const token=++generation.current;setLayer('loading');setError('');
    engine.showFrame(target,playback.index).then(()=>{if(token===generation.current){engine.setCutoutVisible(visible);setLayer('ready');}})
      .catch(e=>{if(token===generation.current){engine.hideCutout();setLayer('error');setError(String(e));dispatch({type:'mode',mode:'paused'});}});
  },[engine,target,playback.index]);
  useEffect(()=>{if(playback.mode==='paused'||!prepared)return;const timer=window.setInterval(()=>dispatch({type:'tick'}),playback.intervalMs);return()=>clearInterval(timer);},[playback.mode,playback.intervalMs,prepared]);
  useEffect(()=>{dispatch({type:'mode',mode:'paused'});},[interruption]);
  useEffect(()=>{if(import.meta.env.DEV)window.__analysis={index:playback.index,mode:playback.mode,prepared,targetId:target.id,pause:()=>dispatch({type:'mode',mode:'paused'})};},[playback,prepared,target.id]);
  const show=()=>{dispatch({type:'mode',mode:'paused'});engine.setCutoutVisible(!visible);setVisible(!visible)};
  const select=(index:number)=>dispatch({type:'select',index});
  const canInspect=!target.brightness&&frames.some(f=>f.expectedPosition||f.measuredPosition);
  return <>
    {!minimized&&<TargetPreview target={displayed} layerState={layer} visible={visible} onVisible={show} onBack={onBack}/>}
    {inspector&&canInspect&&<><MotionInspector target={target} onClose={()=>setInspector(false)}/><MotionOverlay engine={engine} target={target} current={playback.index}/></>}
    {inspector&&target.brightness&&<BrightnessInspector target={target} index={playback.index} onSelect={select} onClose={()=>setInspector(false)}/>}
    <section className={`temporal-timeline floating-panel ${minimized?'is-minimized':''}`} aria-label={`${target.name} temporal analysis`} data-frame-index={playback.index}>
      <div className="timeline-heading"><span className="eyebrow">ANALYZE · {target.name}</span><span className="epoch-current">{displayed.observation.timestampUtc.replace('T',' ')} UTC · {displayed.observation.wavelengthUm?.toFixed(5)??'—'} μm</span><button className="text-button" onClick={()=>{dispatch({type:'mode',mode:'paused'});setMinimized(!minimized);}}>{minimized?'Expand analysis':'Minimize analysis'}</button></div>
      {!minimized&&<>
        <div className="timeline-controls">
          <button aria-label="Previous observation" onClick={()=>dispatch({type:'step',delta:-1})}>←</button>
          <button aria-label={playback.mode==='playing'?'Pause playback':'Play observations'} disabled={!prepared||!visible||count<2} onClick={()=>dispatch({type:'mode',mode:playback.mode==='playing'?'paused':'playing'})}>{playback.mode==='playing'?'Ⅱ Pause':'▶ Play'}</button>
          <button aria-label="Next observation" onClick={()=>dispatch({type:'step',delta:1})}>→</button>
          <span className="frame-count">{playback.index+1} / {count} observations</span>
          <label>Speed<select aria-label="Playback speed" value={playback.intervalMs} onChange={e=>dispatch({type:'speed',intervalMs:Number(e.target.value)})}><option value={1500}>Slow · 1.5 s</option><option value={900}>Normal · 0.9 s</option><option value={400}>Fast · 0.4 s</option></select></label>
          <div className="blink-controls"><label>A<select aria-label="Observation A" value={playback.a} onChange={e=>dispatch({type:'pair',slot:'a',index:Number(e.target.value)})}>{frames.map((f,i)=><option key={f.id} value={i}>{f.observation.timestampUtc.slice(0,10)}</option>)}</select></label>
          <label>B<select aria-label="Observation B" value={playback.b} onChange={e=>dispatch({type:'pair',slot:'b',index:Number(e.target.value)})}>{frames.map((f,i)=><option key={f.id} value={i}>{f.observation.timestampUtc.slice(0,10)}</option>)}</select></label>
          <button aria-label={playback.mode==='blinking'?'Stop blink':'Blink A/B'} disabled={!prepared||!visible||playback.a===playback.b||count<2} onClick={()=>dispatch({type:'mode',mode:playback.mode==='blinking'?'paused':'blinking'})}>{playback.mode==='blinking'?'Stop blink':'Blink A/B'}</button></div>
          {canInspect&&<button className="inspector-toggle" onClick={()=>setInspector(!inspector)} aria-expanded={inspector}>{target.id==='barnard'?'Predicted positions':'Motion Inspector'}</button>}
          {target.brightness&&<button className="inspector-toggle" onClick={()=>setInspector(!inspector)} aria-expanded={inspector}>Brightness Inspector</button>}
        </div>
        <div className="epoch-track" role="group" aria-label="Observation dates in UTC">{frames.map((f,index)=><button className={index===playback.index?'active':''} key={f.id} aria-pressed={index===playback.index} aria-label={`Select observation ${index+1}: ${f.observation.timestampUtc} UTC`} onClick={()=>select(index)}><i/><span>{f.observation.timestampUtc.slice(0,10)}</span><small>{f.observation.detector.replace('SPHEREx-','')} / {f.observation.release.toUpperCase()}</small></button>)}</div>
        <div className="timeline-footnote"><span>{prepared?'Local epochs cached · common intensity limits':error?'Local epoch preparation failed':'Preparing local epochs…'} · {target.sequence?.display.vmin.toFixed(5)}–{target.sequence?.display.vmax.toFixed(5)} · asinh</span><span>Visual cadence; dates are real. Time gaps are not played in real time.</span></div>
        {error&&<p className="temporal-error" role="alert">{error}</p>}
        <p className="sequence-science-warning">{target.sequence?.interpretation??target.warnings[0]}</p>
      </>}
      {minimized&&<button className="text-button" onClick={onBack}>Back to Sky</button>}
    </section>
  </>;
}
