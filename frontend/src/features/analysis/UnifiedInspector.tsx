import type {ReactNode} from 'react';

export type InspectorTab='overview'|'motion'|'brightness'|'difference'|'metadata'|'candidate';
export interface InspectorSection {id:InspectorTab;label:string}
export function UnifiedInspector({tabs,active,onTab,onClose,children,layer,visible,onVisible}:{tabs:InspectorSection[];active:InspectorTab;onTab:(tab:InspectorTab)=>void;onClose:()=>void;children:ReactNode;layer:string;visible:boolean;onVisible:()=>void}){
  return <aside className="unified-inspector surface" aria-label="Scientific inspector">
    <header className="inspector-heading"><h2>Inspect the observations</h2><button className="icon-button" aria-label="Minimize analysis" title="Close the inspector; keep the sky position" onClick={onClose}>›</button></header>
    <div className="inspector-tabs" role="tablist" aria-label="Scientific inspection tools" onKeyDown={e=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
      e.preventDefault();const index=tabs.findIndex(t=>t.id===active),next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
      onTab(tabs[next].id);e.currentTarget.querySelector<HTMLButtonElement>(`[data-tab="${tabs[next].id}"]`)?.focus();
    }}>{tabs.map(t=><button key={t.id} role="tab" id={`inspect-tab-${t.id}`} data-tab={t.id} aria-selected={t.id===active} aria-controls={`inspect-panel-${t.id}`} tabIndex={t.id===active?0:-1} onClick={()=>onTab(t.id)}>{t.label}</button>)}</div>
    <div className="inspector-body" role="tabpanel" id={`inspect-panel-${active}`} aria-labelledby={`inspect-tab-${active}`}>{children}</div>
    <footer className="inspector-layer"><span className={`status-dot ${layer}`}/><span>{layer==='ready'?'Native WCS layer':layer==='error'?'Layer unavailable':'Loading local FITS…'}</span><button className="text-button" aria-label={visible?'Hide layer':'Show layer'} onClick={onVisible} aria-pressed={visible}>{visible?'Hide layer':'Show layer'}</button></footer>
  </aside>;
}
