import type { SkyEngine, SkyTarget } from '../../types/sky';
import {useEffect,useRef} from 'react';
import {placeLabel} from './labelPlacement';

export function TargetMarkers({engine,targets,selected,onSelect}:{engine:SkyEngine;targets:SkyTarget[];selected:string|null;onSelect:(target:SkyTarget)=>void}){
  const nodes=useRef(new Map<string,HTMLButtonElement>());
  useEffect(()=>{
    let raf=0;
    const update=()=>{const [width,height]=engine.snapshot().size,root=document.querySelector('.map-overlays')!.getBoundingClientRect();
      const blocked=[...document.querySelectorAll<HTMLElement>('.explore-sidebar,.spectral-explorer:not([hidden]),.map-controls,.coordinate-search:not([hidden]),.guided-discovery,.app-header,.investigation-header,.unified-inspector,.temporal-timeline,.discoveries-button')].filter(n=>n.getClientRects().length).map(n=>{const r=n.getBoundingClientRect();return {left:r.left-root.left-5,top:r.top-root.top-5,right:r.right-root.left+5,bottom:r.bottom-root.top+5};});
      for(const target of targets){const node=nodes.current.get(target.id);if(!node)continue;const point=engine.project([target.center.raDeg,target.center.decDeg]);
        const hidden=!point||point[0]<16||point[1]<16||point[0]>width-16||point[1]>height-16||blocked.some(r=>point[0]>r.left&&point[0]<r.right&&point[1]>r.top&&point[1]<r.bottom);
        if(node.hidden!==hidden)node.hidden=hidden;
        if(point){node.style.left=point[0]+'px';node.style.top=point[1]+'px';
          const placement=placeLabel(point,Math.max(90,target.name.length*7+24),[width,height],blocked);
          node.dataset.labelSide=placement?.side??'right';node.dataset.labelHidden=String(!placement);if(placement)blocked.push(placement.rect);
        }
      }
    };
    const schedule=()=>{if(!raf)raf=requestAnimationFrame(()=>{raf=0;update()})};update();const unsubscribe=engine.subscribe(schedule);
    const observer=new MutationObserver(schedule);observer.observe(document.querySelector('.sky-experience')!,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden','open','class']});
    return()=>{unsubscribe();observer.disconnect();cancelAnimationFrame(raf)};
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
