import { useEffect, useState } from 'react';
import { loadCatalog } from './data/catalog';
import type { SkyCatalog } from './types/sky';
import { SkyMap } from './features/sky/SkyMap';

export default function App(){
  const [catalog,setCatalog]=useState<SkyCatalog|null>(null),[error,setError]=useState<string|null>(null);
  useEffect(()=>{const controller=new AbortController();loadCatalog(controller.signal).then(setCatalog).catch(e=>{if(!controller.signal.aborted)setError(String(e));});return()=>controller.abort();},[]);
  if(error)return <main className="startup-error"><h1>Local sky fields could not load</h1><p>{error}</p><button onClick={()=>window.location.reload()}>Try again</button></main>;
  return catalog?<SkyMap catalog={catalog}/>:<main className="startup-loading" role="status">Loading real sky fields…</main>;
}
