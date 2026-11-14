import {useEffect,useRef} from 'react';
import type {Position,SkyEngine,SkyTarget} from '../../types/sky';

export function MotionOverlay({engine,target,current}:{engine:SkyEngine;target:SkyTarget;current:number}){
  const svg=useRef<SVGSVGElement>(null),frames=target.sequence?.frames??[];
  useEffect(()=>{const update=()=>{
    if(!svg.current)return;const [width,height]=engine.snapshot().size;svg.current.setAttribute('viewBox',`0 0 ${width} ${height}`);
    frames.forEach((frame,index)=>{for(const kind of ['expected','measured'] as const){
      const position=frame[`${kind}Position`];const group=svg.current!.querySelector<SVGGElement>(`[data-mark="${kind}-${index}"]`);
      if(!group)continue;const point=position?engine.project([position.raDeg,position.decDeg]):null;
      group.style.display=point?'':'none';if(point)group.setAttribute('transform',`translate(${point[0]} ${point[1]})`);
    }});
    const vector=(kind:'expected'|'measured')=>{const positions=frames.map(f=>f[`${kind}Position`]).filter((p):p is Position=>!!p);if(positions.length!==2)return '';
      const points=positions.map(p=>engine.project([p.raDeg,p.decDeg]));return points.every(Boolean)?`M ${points[0]![0]},${points[0]![1]} L ${points[1]![0]},${points[1]![1]}`:'';};
    for(const kind of ['expected','measured'] as const)svg.current.querySelector(`[data-vector="${kind}"]`)?.setAttribute('d',vector(kind));
  };update();return engine.subscribe(update);},[engine,frames]);
  return <svg className="motion-map-overlay" ref={svg} aria-label="Expected and measured sky positions" data-testid="motion-map-overlay">
    <path data-vector="expected" className="expected-vector"/><path data-vector="measured" className="measured-vector"/>
    {frames.map((frame,index)=><g key={frame.id} opacity={index===current?1:.55}>
      {frame.expectedPosition&&<g data-mark={`expected-${index}`} className="expected-mark"><path d="M -8 0 H 8 M 0 -8 V 8"/><text x="11" y="-9">E{index+1}</text></g>}
      {frame.measuredPosition&&<g data-mark={`measured-${index}`} className="measured-mark"><circle r="6"/><text x="11" y="12">M{index+1}</text></g>}
    </g>)}
  </svg>;
}
