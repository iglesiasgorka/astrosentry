import {useState} from 'react';
import type {SkyTarget} from '../../types/sky';
import '../../styles/guide.css';
export function investigationSteps(target:SkyTarget){
  const sequence=target.sequence!,pair=sequence.historicalPair;
  const a=sequence.frames.find(f=>f.id===pair?.aId)??sequence.frames[0],b=sequence.frames.find(f=>f.id===pair?.bId)??sequence.frames[1];
  return [
    {title:'Start with real observations',text:`Our example is ${target.name}. Compare ${a.observation.timestampUtc.slice(0,10)} and ${b.observation.timestampUtc.slice(0,10)} UTC at ${a.observation.wavelengthUm?.toFixed(6)} and ${b.observation.wavelengthUm?.toFixed(6)} µm. These are real SPHEREx observations, not a simulated motion sequence.`},
    {title:'Compare dates on a fixed sky',text:'Use Previous / Next or Play below. The date changes while the WCS grid, orientation and camera stay fixed. Playback speed is visual cadence; the actual time gaps are not played in real time.'},
    {title:'Try Blink A/B',text:`Click Blink A/B on the timeline. The retained apparent photocenter displacement is approximately ${sequence.motion?.measuredDisplacementArcsec?.toFixed(3)} arcsec, or ${sequence.motion?.measuredDisplacementPixels?.toFixed(2)} output pixels. A subtle blink alone cannot establish significant motion. PSF, spectral response, annual parallax and binary photocenter effects need review.`},
    {title:'Read Difference cautiously',text:'Choose Difference B − A, then return with More controls → Epoch A / B. Blue is negative, red positive, off-white zero. Invalid pixels reveal the background. This uncorrected residual can contain background and instrumental effects; a dipole is not automatically a moving object or a significance measurement.'},
    {title:'Record evidence for review',text:'Choose Mark Candidate to annotate valid pixels in the two real epochs. Add notes, save locally in My Discoveries and export JSON or Markdown. Manual marks are not fitted centroids or validated proper motion. Nothing is submitted to NASA, and a source away from the known target is not automatically new.'},
  ];
}
export function GuidedDiscovery({target,onExplore,onClose}:{target:SkyTarget;onExplore:()=>void;onClose:()=>void}){
  const [step,setStep]=useState(0),[minimized,setMinimized]=useState(false);const steps=investigationSteps(target),current=steps[step];
  return <section className={`guided-discovery floating-panel ${minimized?'is-minimized':''}`} aria-label="Guided Discovery"><header><span className="eyebrow">YOUR FIRST INVESTIGATION · {step+1} / {steps.length}</span><div><button className="text-button" onClick={()=>setMinimized(!minimized)}>{minimized?'Expand guide':'Minimize guide'}</button><button className="text-button" aria-label="Close guide" onClick={onClose}>×</button></div></header>
    {!minimized&&<><div className="guide-progress" aria-label={`Guide progress: ${step+1} of ${steps.length}`}><span style={{width:`${(step+1)/steps.length*100}%`}}/></div><h2>{current.title}</h2><p>{current.text}</p><small>Example: {target.name} · exploratory, not a significant-motion detection.</small><div className="guide-actions"><button disabled={step===0} onClick={()=>setStep(step-1)}>Previous guide step</button>{step===0?<button onClick={()=>{onExplore();setStep(1)}}>Open real example</button>:step===steps.length-1?<button onClick={onClose}>Finish guide</button>:<button onClick={()=>setStep(step+1)}>Next guide step</button>}{step>0&&<button className="text-button" onClick={onExplore}>Return to example</button>}</div></>}
  </section>;
}
