import {useEffect,useMemo,useReducer,useRef,useState} from 'react';
import type {SkyEngine,SkyTarget} from '../../types/sky';
import {TargetPreview} from './TargetPreview';
import {initialPlayback,playbackReducer} from './playback';
import {MotionInspector} from './MotionInspector';
import {MotionOverlay} from './MotionOverlay';
import {BrightnessInspector} from './BrightnessInspector';
import {DifferencePanel} from './DifferencePanel';
import {compatibleBlink,groupIndices,motionContext,observationGroups,preparedDifference} from './comparison';
import {CandidateInspector} from './CandidateInspector';
import type {CandidateEvidence} from './candidateModel';
import {UnifiedInspector,type InspectorTab,type InspectorSection} from './UnifiedInspector';
import {ObservationMetadata} from './ObservationMetadata';
import {scienceStatus} from '../sky/productLayout';

declare global {interface Window {__analysis?:{index:number;mode:string;prepared:boolean;targetId:string;groupId:string;frameIds:string[];motionFrameIds:string[];a:number;b:number;view:'epoch'|'difference';pause:()=>void}}}
export function TemporalAnalysis({engine,target,onBack,interruption,restoredCandidate}:{engine:SkyEngine;target:SkyTarget;onBack:()=>void;interruption:number;restoredCandidate?:CandidateEvidence}){
  const frames=target.sequence?.frames??[],count=frames.length||1;
  const groups=useMemo(()=>observationGroups(target),[target]);
  const [groupId,setGroupId]=useState(target.sequence?.defaultGroupId??groups[0].id);
  const group=groups.find(g=>g.id===groupId)??groups[0];
  const scope=useMemo(()=>groupIndices(target,group),[target,group]);
  const [playback,dispatch]=useReducer(playbackReducer,count,n=>playbackReducer(initialPlayback(n),{type:'group',indices:scope}));
  const [layer,setLayer]=useState<'loading'|'ready'|'error'>('loading'),[prepared,setPrepared]=useState(false);
  const [error,setError]=useState(''),[visible,setVisible]=useState(true),[inspectorOpen,setInspectorOpen]=useState(()=>window.innerWidth>700),[tab,setTab]=useState<InspectorTab>('overview'),[differenceMode,setDifferenceMode]=useState(false);
  const generation=useRef(0);
  const [candidateOpen,setCandidateOpen]=useState(false),[candidateSeed,setCandidateSeed]=useState<CandidateEvidence|null>(null);
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
      .catch(e=>{if(token===generation.current){engine.hideCutout();setLayer('error');setInspectorOpen(true);setTab('overview');setError(String(e));dispatch({type:'mode',mode:'paused'});}});
  },[engine,target,playback.index,group,differenceActive,difference]);
  useEffect(()=>{if(playback.mode==='paused'||!prepared||differenceActive)return;const timer=window.setInterval(()=>dispatch({type:'tick'}),playback.intervalMs);return()=>clearInterval(timer);},[playback.mode,playback.intervalMs,prepared,differenceActive]);
  useEffect(()=>{dispatch({type:'mode',mode:'paused'});},[interruption]);
  useEffect(()=>{
    if(!restoredCandidate)return;
    const a=frames.findIndex(f=>f.id===restoredCandidate.a.frameId),b=frames.findIndex(f=>f.id===restoredCandidate.b.frameId);
    const selected=groups.find(g=>g.comparison&&g.frameIds.includes(restoredCandidate.a.frameId)&&g.frameIds.includes(restoredCandidate.b.frameId));
    if(a<0||b<0||!selected){setError('Saved observation pair is no longer available in a compatible group.');return;}
    setGroupId(selected.id);dispatch({type:'group',indices:groupIndices(target,selected)});dispatch({type:'pair',slot:'a',index:a});dispatch({type:'pair',slot:'b',index:b});dispatch({type:'select',index:a});
    setInspectorOpen(true);setTab('candidate');setCandidateSeed(restoredCandidate);setCandidateOpen(true);
  },[restoredCandidate]);
  useEffect(()=>{if(import.meta.env.DEV)window.__analysis={index:playback.index,mode:playback.mode,prepared,targetId:target.id,groupId,frameIds:scope.map(i=>frames[i].id),motionFrameIds:motionTarget.sequence!.frames.map(f=>f.id),a:playback.a,b:playback.b,view:differenceActive?'difference':'epoch',pause:()=>dispatch({type:'mode',mode:'paused'})};},[playback,prepared,target.id,groupId,scope,frames,motionTarget,differenceActive]);
  const show=()=>{dispatch({type:'mode',mode:'paused'});setCandidateOpen(false);if(tab==='candidate')setTab('overview');engine.setCutoutVisible(!visible);setVisible(!visible)};
  const select=(index:number)=>{setDifferenceMode(false);dispatch({type:'select',index});};
  const step=(delta:number)=>{setDifferenceMode(false);dispatch({type:'step',delta});};
  const changeGroup=(id:string)=>{const selected=groups.find(g=>g.id===id)!;setDifferenceMode(false);setGroupId(id);dispatch({type:'group',indices:groupIndices(target,selected)});};
  const canInspect=!target.brightness&&motionTarget.sequence!.frames.some(f=>f.expectedPosition||f.measuredPosition);
  const options=scope.map(i=><option key={frames[i].id} value={i}>{frames[i].observation.timestampUtc.slice(0,10)} · {frames[i].observation.wavelengthUm?.toFixed(4)} μm</option>);
  const pause=()=>dispatch({type:'mode',mode:'paused'});
  const closeInspector=()=>{pause();setCandidateOpen(false);setInspectorOpen(false);requestAnimationFrame(()=>document.querySelector<HTMLButtonElement>('.inspector-reopen')?.focus());};
  const openTab=(next:InspectorTab)=>{setInspectorOpen(true);setTab(next);if(next!=='candidate')setCandidateOpen(false);if(next==='candidate'){pause();setDifferenceMode(false);setCandidateOpen(true);}if(next==='difference'&&difference){pause();setDifferenceMode(true);}};
  const tabs:InspectorSection[]=[{id:'overview',label:'Overview'},...(canInspect?[{id:'motion' as const,label:'Motion'}]:[]),...(target.brightness?[{id:'brightness' as const,label:'Brightness'}]:[]),...(target.sequence!.differences?.length?[{id:'difference' as const,label:'Difference'}]:[]),{id:'metadata',label:'Metadata'},...(blinkAllowed?[{id:'candidate' as const,label:'Candidate'}]:[])];
  const currentTab=tabs.some(t=>t.id===tab)?tab:'overview';
  const toggleDifference=()=>{pause();setCandidateOpen(false);setDifferenceMode(!differenceActive);setTab(differenceActive?'overview':'difference');setInspectorOpen(true);};
  const mark=()=>{pause();setCandidateSeed(null);setCandidateOpen(true);setTab('candidate');setInspectorOpen(true);};
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){const details=document.querySelector<HTMLDetailsElement>('.timeline-options[open]');if(details){details.open=false;return;}if(inspectorOpen){e.stopPropagation();closeInspector();}}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[inspectorOpen]);
  useEffect(()=>{const outside=(e:PointerEvent)=>{const details=document.querySelector<HTMLDetailsElement>('.timeline-options[open]');if(details&&!details.contains(e.target as Node))details.open=false;};document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside);},[]);
  const epoch=()=>differenceActive?<DifferencePanel target={target} difference={difference!} layer={layer} visible={visible} onVisible={show} onBack={onBack}/>:<TargetPreview target={displayed} layerState={layer} visible={visible} onVisible={show} onBack={onBack}/>;
  return <>
    {inspectorOpen?<UnifiedInspector tabs={tabs} active={currentTab} onTab={openTab} onClose={closeInspector} layer={layer} visible={visible} onVisible={show}>
      {currentTab==='overview'&&epoch()}
      {currentTab==='metadata'&&<ObservationMetadata target={target} frame={frame} difference={differenceActive?difference:undefined}/>}
      {currentTab==='motion'&&canInspect&&<MotionInspector target={motionTarget} onClose={()=>openTab('overview')}/>}
      {currentTab==='brightness'&&target.brightness&&<BrightnessInspector target={target} index={playback.index} onSelect={select} onClose={()=>openTab('overview')}/>}
      {currentTab==='difference'&&(difference?<DifferencePanel target={target} difference={difference} layer={layer} visible={visible} onVisible={show} onBack={onBack}/>:<p className="primary-warning">No prepared residual for this ordered pair. Choose the historical compatible pair in More controls. No Difference has been invented.</p>)}
      {currentTab==='candidate'&&candidateOpen&&blinkAllowed&&visible&&!differenceActive&&<CandidateInspector key={`${target.id}:${groupId}:${playback.a}:${playback.b}`} engine={engine} target={target} a={playback.a} b={playback.b} current={playback.index} layerReady={layer==='ready'} onEpoch={select} onClose={()=>{setCandidateOpen(false);setTab('overview')}} initialEvidence={candidateSeed?.a.frameId===frames[playback.a].id&&candidateSeed?.b.frameId===frames[playback.b].id?candidateSeed:undefined}/>}
    </UnifiedInspector>:<button className="inspector-reopen" aria-label="Expand analysis" onClick={()=>{setInspectorOpen(true);setTab('overview')}}>Inspect observations ↗</button>}
    {inspectorOpen&&currentTab==='motion'&&canInspect&&<MotionOverlay engine={engine} target={motionTarget} current={motionCurrent}/>}
    <section className="temporal-timeline floating-panel" aria-label={`${target.name} temporal analysis`} data-frame-index={playback.index} data-group={groupId} data-view={differenceActive?'difference':'epoch'}>
      <div className="timeline-primary">
        <button aria-label="Previous observation" onClick={()=>step(-1)}>←</button>
        <button className="play-button" aria-label={playback.mode==='playing'?'Pause playback':'Play observations'} disabled={!prepared||!visible||scope.length<2} onClick={()=>{setCandidateOpen(false);if(tab==='candidate')setTab('overview');setDifferenceMode(false);dispatch({type:'mode',mode:playback.mode==='playing'?'paused':'playing'});}}>{playback.mode==='playing'?'Ⅱ Pause':'▶ Play'}</button>
        <button aria-label="Next observation" onClick={()=>step(1)}>→</button>
        <span className="epoch-current">{differenceActive?'Difference B − A':frame.observation.timestampUtc.slice(0,10)+' UTC'}<small>Observation λ {frame.observation.wavelengthUm?.toFixed(5)} μm · {scope.indexOf(playback.index)+1} / {scope.length} observations</small></span>
        <button className="blink-button" aria-label={playback.mode==='blinking'?'Stop blink':'Blink A/B'} disabled={!prepared||!visible||!blinkAllowed} title={blinkAllowed?'Alternate the selected real A/B epochs':'Blink needs two distinct epochs in a compatible group'} onClick={()=>{setCandidateOpen(false);if(tab==='candidate')setTab('overview');setDifferenceMode(false);dispatch({type:'mode',mode:playback.mode==='blinking'?'paused':'blinking'});}}>{playback.mode==='blinking'?'Stop blink':'Blink A/B'}</button>
        <button className="difference-toggle" aria-label="Difference B minus A" aria-pressed={differenceActive} disabled={!prepared||!group.comparison||!difference} title={difference?'Prepared masked residual':'No prepared compatible residual for this ordered pair'} onClick={toggleDifference}>Difference B − A</button>
        <button className="candidate-toggle" disabled={!prepared||!blinkAllowed||!visible||differenceActive} title="Manual marking requires a compatible pair and visible real epochs" onClick={mark}>Mark Candidate</button>
        <details className="timeline-options"><summary>More controls</summary><div className="advanced-controls surface">
          <p className="eyebrow">{group.comparison?'COMPARE TWO DATES':'BROWSE OBSERVATIONS'}</p>
          <div className="comparison-group"><label>Observation group<select aria-label="Observation group" value={groupId} onChange={e=>{setCandidateOpen(false);changeGroup(e.target.value)}}>{groups.map(g=><option key={g.id} value={g.id}>{g.label} ({g.frameIds.length})</option>)}</select></label><span>{count} available observations · {scope.length} in view</span></div>
          <label>Playback speed<select aria-label="Playback speed" value={playback.intervalMs} onChange={e=>dispatch({type:'speed',intervalMs:Number(e.target.value)})}><option value={1500}>Slow · 1.5 s</option><option value={900}>Normal · 0.9 s</option><option value={400}>Fast · 0.4 s</option></select></label>
          <label>Observation A<select aria-label="Observation A" value={playback.a} onChange={e=>{setCandidateOpen(false);setDifferenceMode(false);dispatch({type:'pair',slot:'a',index:Number(e.target.value)});}}>{options}</select></label>
          <label>Observation B<select aria-label="Observation B" value={playback.b} onChange={e=>{setCandidateOpen(false);setDifferenceMode(false);dispatch({type:'pair',slot:'b',index:Number(e.target.value)});}}>{options}</select></label>
          <div className="epoch-shortcuts"><button aria-label="Show epoch A" onClick={()=>select(playback.a)}>Epoch A</button><button aria-label="Show epoch B" onClick={()=>select(playback.b)}>Epoch B</button></div>
          <p>{group.label}. {group.warnings.join(' ')}</p><p>Common {activeDisplay.stretch} limits: {activeDisplay.vmin.toFixed(5)}–{activeDisplay.vmax.toFixed(5)}. No per-frame auto scaling.</p>
        </div></details>
      </div>
      <div className="epoch-track" role="group" aria-label="Observation dates in UTC">{scope.map((index,i)=><button className={index===playback.index&&!differenceActive?'active':''} key={frames[index].id} aria-pressed={index===playback.index&&!differenceActive} aria-label={`Select observation ${i+1}: ${frames[index].observation.timestampUtc} UTC`} onClick={()=>select(index)}><i/><span>{frames[index].observation.timestampUtc.slice(0,10)}</span></button>)}</div>
      <p className="timeline-note"><span className="science-note">{scienceStatus(target)} · {group.comparison?'Compatible group; systematics remain unvalidated.':'Inspection only: spectra or quality differ.'}</span><span>{prepared?'Local frames prepared':'Preparing local frames…'} · Real dates, visual playback cadence</span></p>
      {!blinkAllowed&&<p className="operation-reason">Blink and manual A/B comparison need a compatible, distinct pair. No homogeneous comparison is inferred from these frames.</p>}
      {error&&<p className="temporal-error" role="alert">{error}</p>}
    </section>
  </>;
}
