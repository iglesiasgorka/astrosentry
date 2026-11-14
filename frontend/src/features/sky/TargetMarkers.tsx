import type { SkyEngine, SkyTarget } from '../../types/sky';
import {useEffect,useRef} from 'react';

export function TargetMarkers({engine,targets,selected,onSelect}:{engine:SkyEngine;targets:SkyTarget[];selected:string|null;onSelect:(target:SkyTarget)=>void}){
  const nodes=useRef(new Map<string,HTMLButtonElement>());
  useEffect(()=>{
    const update=()=>{const [width,height]=engine.snapshot().size;for(const target of targets){const node=nodes.current.get(target.id);if(!node)continue;const point=engine.project([target.center.raDeg,target.center.decDeg]);
      const hidden=!point||point[0]<16||point[1]<75||point[0]>width-16||point[1]>height-45;
      node.hidden=hidden;if(point){node.style.left=point[0]+'px';node.style.top=point[1]+'px';}
    }};update();return engine.subscribe(update);
  },[engine,targets,selected]);
  return <div className="target-markers" aria-label="Prepared sky fields">{targets.map(target=>{
    if(selected===target.id)return null;
    return <button className="target-marker" key={target.id} ref={node=>{if(node)nodes.current.set(target.id,node);else nodes.current.delete(target.id);}}
      data-target={target.id} aria-label={`Fly to ${target.name}`} onClick={()=>onSelect(target)}>
      <span className="marker-orbit" aria-hidden="true"><i/></span>
      <span className="marker-label"><strong>{target.name}</strong><small>SPHEREx field <span aria-hidden="true">↗</span></small></span>
    </button>;
  })}</div>;
}
