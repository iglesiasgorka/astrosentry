import type {SkyTarget} from '../../types/sky';

export function ExploreSidebar({targets,onSelect,onGuide,onClose}:{targets:SkyTarget[];onSelect:(target:SkyTarget)=>void;onGuide:()=>void;onClose:()=>void}){
  const order=['barnard','epsilon_indi_b','wise0855','rw_aur','r_dra'];
  const official=targets.filter(t=>order.includes(t.id)).sort((a,b)=>order.indexOf(a.id)-order.indexOf(b.id));
  const additional=targets.filter(t=>t.id==='m101'||t.id.startsWith('region_'));
  const entry=(t:SkyTarget)=><button key={t.id} onClick={()=>onSelect(t)}><span><strong>{t.name}</strong><small>{t.objectType}</small></span><span aria-hidden="true">↗</span></button>;
  return <aside className="explore-sidebar surface" aria-label="Explore the sky">
    <header><div><span className="eyebrow">DISCOVER · EXPLORE · INVESTIGATE</span><h1>Explore the sky.</h1></div><button className="icon-button" aria-label="Collapse sidebar" onClick={onClose}>‹</button></header>
    <p>Real infrared observations.<br/>A different way to see the sky.</p>
    <button className="start-investigation" aria-label="Start your first investigation" onClick={onGuide}><span aria-hidden="true">✦</span><span>Start your first investigation<small>A guided look at two real dates</small></span><span aria-hidden="true">→</span></button>
    <nav className="field-index" aria-label="Prepared fields navigation"><h2>Challenge Targets <span>{official.length}</span></h2>{official.map(entry)}<h2>Additional Fields</h2>{additional.map(entry)}</nav>
    <footer><span className="mini-orbit" aria-hidden="true">⌖</span><p>Choose a field or enter coordinates.<br/>Drag the map to follow your curiosity.</p></footer>
  </aside>;
}
