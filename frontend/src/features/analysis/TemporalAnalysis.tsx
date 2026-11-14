import {useEffect,useMemo,useReducer,useRef,useState} from 'react';
import type {SkyEngine,SkyTarget} from '../../types/sky';
import {TargetPreview} from './TargetPreview';
import {initialPlayback,playbackReducer} from './playback';
import {MotionInspector} from './MotionInspector';
import {MotionOverlay} from './MotionOverlay';
import {BrightnessInspector} from './BrightnessInspector';
import {DifferencePanel} from './DifferencePanel';
import {compatibleBlink,groupIndices,motionContext,observationGroups,preparedDifference} from './comparison';

declare global {interface Window {__analysis?:{index:number;mode:string;prepared:boolean;targetId:string;groupId:string;frameIds:string[];motionFrameIds:string[];a:number;b:number;view:'epoch'|'difference';pause:()=>void}}}
export function TemporalAnalysis({engine,target,onBack,interruption}:{engine:SkyEngine;target:SkyTarget;onBack:()=>void;interruption:number}){
  const frames=target.sequence?.frames??[],count=frames.length||1;
  const groups=useMemo(()=>observationGroups(target),[target]);
  const [groupId,setGroupId]=useState(target.sequence?.defaultGroupId??groups[0].id);
  const group=groups.find(g=>g.id===groupId)??groups[0];
  const scope=useMemo(()=>groupIndices(target,group),[target,group]);
  const [playback,dispatch]=useReducer(playbackReducer,count,n=>playbackReducer(initialPlayback(n),{type:'group',indices:scope}));
  const [layer,setLayer]=useState<'loading'|'ready'|'error'>('loading'),[prepared,setPrepared]=useState(false);
  const [error,setError]=useState(''),[visible,setVisible]=useState(true),[inspector,setInspector]=useState(false),[minimized,setMinimized]=useState(false),[differenceMode,setDifferenceMode]=useState(false);
  const generation=useRef(0);
  const frame=frames[playback.index],difference=preparedDifference(target,playback.a,playback.b);
  const blinkAllowed=compatibleBlink(target,group,playback.a,playback.b);
  const differenceActive=differenceMode&&!!difference&&group.comparison;
  const activeDisplay=differenceActive?difference!.display:group.display;
  const motionTarget=useMemo(()=>motionContext(target,playback.a,playback.b,playback.index),[target,playback.a,playback.b,playback.index]);
  const motionCurrent=motionTarget.sequence!.frames.findIndex(f=>f.id===frame.id);
  const displayed:SkyTarget={...target,observation:frame.observation,assets:frame.assets,warnings:[...new Set([target.sequence!.interpretation,...group.warnings,...target.warnings,...frame.warnings])]};
  useEffect(()=>{let canceled=false;setPrepared(false);
    engine.prepareSequence(target,scope).then(()=>{if(!canceled)setPrepared(true)}).catch(e=>{if(!canceled)setError(`Some local observations could not be prepared: ${String(e)}`)});
    return()=>{canceled=true;};
  },[engine,target,scope]);
  useEffect(()=>()=>{generation.current++;delete window.__analysis;},[]);
  useEffect(()=>{const token=++generation.current;setLayer('loading');setError('');
    const load=differenceActive?engine.showDifference(target,difference!):engine.showFrame(target,playback.index,group.display);
    load.then(()=>{if(token===generation.current){engine.setCutoutVisible(visible);setLayer('ready');}})
      .catch(e=>{if(token===generation.current){engine.hideCutout();setLayer('error');setError(String(e));dispatch({type:'mode',mode:'paused'});}});
  },[engine,target,playback.index,group,differenceActive,difference]);
  useEffect(()=>{if(playback.mode==='paused'||!prepared||differenceActive)return;const timer=window.setInterval(()=>dispatch({type:'tick'}),playback.intervalMs);return()=>clearInterval(timer);},[playback.mode,playback.intervalMs,prepared,differenceActive]);
  useEffect(()=>{dispatch({type:'mode',mode:'paused'});},[interruption]);
  useEffect(()=>{if(import.meta.env.DEV)window.__analysis={index:playback.index,mode:playback.mode,prepared,targetId:target.id,groupId,frameIds:scope.map(i=>frames[i].id),motionFrameIds:motionTarget.sequence!.frames.map(f=>f.id),a:playback.a,b:playback.b,view:differenceActive?'difference':'epoch',pause:()=>dispatch({type:'mode',mode:'paused'})};},[playback,prepared,target.id,groupId,scope,frames,motionTarget,differenceActive]);
  const show=()=>{dispatch({type:'mode',mode:'paused'});engine.setCutoutVisible(!visible);setVisible(!visible)};
  const select=(index:number)=>{setDifferenceMode(false);dispatch({type:'select',index});};
  const step=(delta:number)=>{setDifferenceMode(false);dispatch({type:'step',delta});};
  const changeGroup=(id:string)=>{const selected=groups.find(g=>g.id===id)!;setDifferenceMode(false);setGroupId(id);dispatch({type:'group',indices:groupIndices(target,selected)});};
  const canInspect=!target.brightness&&motionTarget.sequence!.frames.some(f=>f.expectedPosition||f.measuredPosition);
  const options=scope.map(i=><option key={frames[i].id} value={i}>{frames[i].observation.timestampUtc.slice(0,10)} · {frames[i].observation.wavelengthUm?.toFixed(4)} μm</option>);
  return <>
    {!minimized&&(differenceActive?<DifferencePanel target={target} difference={difference!} layer={layer} visible={visible} onVisible={show} onBack={onBack}/>:<TargetPreview target={displayed} layerState={layer} visible={visible} onVisible={show} onBack={onBack}/>)}
    {inspector&&canInspect&&<><MotionInspector target={motionTarget} onClose={()=>setInspector(false)}/><MotionOverlay engine={engine} target={motionTarget} current={motionCurrent}/></>}
    {inspector&&target.brightness&&<BrightnessInspector target={target} index={playback.index} onSelect={select} onClose={()=>setInspector(false)}/>}
    <section className={`temporal-timeline floating-panel ${minimized?'is-minimized':''}`} aria-label={`${target.name} temporal analysis`} data-frame-index={playback.index} data-group={groupId} data-view={differenceActive?'difference':'epoch'}>
      <div className="timeline-heading"><span className="eyebrow">{target.classification==='diagnostic'?'DIAGNOSTIC OBSERVATION BROWSER':group.comparison?'SCIENTIFIC COMPARISON':'OBSERVATION BROWSER'} · {target.name}</span><span className="epoch-current">{differenceActive?'SIGNED RESIDUAL B − A':frame.observation.timestampUtc.replace('T',' ')+' UTC · '+frame.observation.wavelengthUm?.toFixed(5)+' μm'}</span><button className="text-button" onClick={()=>{dispatch({type:'mode',mode:'paused'});setMinimized(!minimized);if(!minimized)setInspector(false);}}>{minimized?'Expand analysis':'Minimize analysis'}</button></div>
      {!minimized&&<>
        {target.sequence?.groups&&<div className="comparison-group"><label>Observation / spectral group<select aria-label="Observation group" value={groupId} onChange={e=>changeGroup(e.target.value)}>{groups.map(g=><option key={g.id} value={g.id}>{g.label} ({g.frameIds.length})</option>)}</select></label><span>{count} available observations · {scope.length} in view</span>{!group.comparison&&<strong>Inspection only — wavelengths differ; not a homogeneous temporal sequence.</strong>}</div>}
        <div className="timeline-controls">
          <button aria-label="Previous observation" onClick={()=>step(-1)}>←</button>
          <button aria-label={playback.mode==='playing'?'Pause playback':'Play observations'} disabled={!prepared||!visible||scope.length<2} onClick={()=>{setDifferenceMode(false);dispatch({type:'mode',mode:playback.mode==='playing'?'paused':'playing'});}}>{playback.mode==='playing'?'Ⅱ Pause':'▶ Play'}</button>
          <button aria-label="Next observation" onClick={()=>step(1)}>→</button>
          <span className="frame-count">{scope.indexOf(playback.index)+1} / {scope.length} observations</span>
          <label>Speed<select aria-label="Playback speed" value={playback.intervalMs} onChange={e=>dispatch({type:'speed',intervalMs:Number(e.target.value)})}><option value={1500}>Slow · 1.5 s</option><option value={900}>Normal · 0.9 s</option><option value={400}>Fast · 0.4 s</option></select></label>
          <div className="blink-controls"><label>A<select aria-label="Observation A" value={playback.a} onChange={e=>{setDifferenceMode(false);dispatch({type:'pair',slot:'a',index:Number(e.target.value)});}}>{options}</select></label>
          <label>B<select aria-label="Observation B" value={playback.b} onChange={e=>{setDifferenceMode(false);dispatch({type:'pair',slot:'b',index:Number(e.target.value)});}}>{options}</select></label>
          <button aria-label={playback.mode==='blinking'?'Stop blink':'Blink A/B'} disabled={!prepared||!visible||!blinkAllowed} onClick={()=>{setDifferenceMode(false);dispatch({type:'mode',mode:playback.mode==='blinking'?'paused':'blinking'});}}>{playback.mode==='blinking'?'Stop blink':'Blink A/B'}</button></div>
          <button aria-label="Show epoch A" onClick={()=>select(playback.a)}>Epoch A</button><button aria-label="Show epoch B" onClick={()=>select(playback.b)}>Epoch B</button>
          <button className="difference-toggle" aria-label="Difference B minus A" aria-pressed={differenceActive} disabled={!prepared||!group.comparison||!difference} title={difference?'Prepared masked residual':'No prepared compatible residual for this ordered pair'} onClick={()=>{dispatch({type:'mode',mode:'paused'});setDifferenceMode(!differenceActive);}}>Difference B − A</button>
          {canInspect&&<button className="inspector-toggle" onClick={()=>setInspector(!inspector)} aria-expanded={inspector}>{target.id==='barnard'?'Predicted positions':'Motion Inspector'}</button>}
          {target.brightness&&<button className="inspector-toggle" onClick={()=>setInspector(!inspector)} aria-expanded={inspector}>Brightness Inspector</button>}
        </div>
        <div className="epoch-track" role="group" aria-label="Observation dates in UTC">{scope.map((index,i)=><button className={index===playback.index&&!differenceActive?'active':''} key={frames[index].id} aria-pressed={index===playback.index&&!differenceActive} aria-label={`Select observation ${i+1}: ${frames[index].observation.timestampUtc} UTC`} onClick={()=>select(index)}><i/><span>{frames[index].observation.timestampUtc.slice(0,10)}</span><small>{frames[index].observation.wavelengthUm?.toFixed(4)} μm · {frames[index].observation.release.toUpperCase()}</small></button>)}</div>
        <div className="timeline-footnote"><span>{differenceActive?'Prepared signed residual · symmetric intensity limits':prepared?'Selected local group prepared · common intensity limits':error?'Local preparation failed':'Preparing selected local group…'} · {activeDisplay.vmin.toFixed(5)}–{activeDisplay.vmax.toFixed(5)} · {activeDisplay.stretch}</span><span>Visual cadence; dates are real. Time gaps are not played in real time.</span></div>
        {error&&<p className="temporal-error" role="alert">{error}</p>}
        <p className="sequence-science-warning">{group.comparison?target.sequence?.interpretation:group.warnings.join(' ')}</p>
      </>}
      {minimized&&<button className="text-button" onClick={onBack}>Back to Sky</button>}
    </section>
  </>;
}
