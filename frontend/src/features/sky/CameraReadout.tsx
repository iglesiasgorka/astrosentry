import {useEffect,useRef,useState} from 'react';
import type {SkyEngine} from '../../types/sky';

export function CameraReadout({engine}:{engine:SkyEngine}){
  const node=useRef<HTMLDivElement>(null);
  useEffect(()=>{const update=()=>{if(!node.current)return;const camera=engine.snapshot();
    const [ra,dec]=camera.center;node.current.querySelector('strong')!.textContent=`RA ${ra.toFixed(5)}°  /  DEC ${dec.toFixed(5)}°`;
    node.current.querySelector('small')!.textContent=`AIT · FoV ${camera.fov>=1?camera.fov.toFixed(1)+'°':(camera.fov*60).toFixed(2)+'′'}`;
  };update();return engine.subscribe(update);},[engine]);
  return <div className="coordinate-readout" ref={node}><span>VIEW CENTER · ICRS</span><strong/><small/></div>;
}

/** Network activity indicator, deliberately not a claim that all survey detail is complete. */
export function SkyDetailStatus({engine}:{engine:SkyEngine}){
  const [busy,setBusy]=useState(false);
  useEffect(()=>{let timer=0;const activity=()=>{setBusy(true);clearTimeout(timer);timer=window.setTimeout(()=>setBusy(false),1200);};
    const stop=engine.subscribe(activity);
    const observer=new PerformanceObserver(list=>{if(list.getEntries().some(entry=>entry.name.includes('/Npix')))activity();});
    observer.observe({type:'resource',buffered:false});return()=>{stop();observer.disconnect();clearTimeout(timer);};
  },[engine]);
  return busy?<div className="sky-detail-status" role="status"><span className="loading-ring small"/> Sky detail updating</div>:null;
}
