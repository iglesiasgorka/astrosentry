import type { SkyTarget } from '../../types/sky';
import { assetUrl } from '../../data/catalog';

export function TargetPreview({target,layerState,visible,onVisible,onBack}:{target:SkyTarget;layerState:'loading'|'ready'|'error';visible:boolean;onVisible:()=>void;onBack:()=>void}){
  return <section className="target-preview floating-panel" aria-label={`${target.name} inspection`}>
    <div className="preview-eyebrow"><span>INDIVIDUAL SPHEREx OBSERVATION</span><span className={`classification ${target.classification==='diagnostic'?'diagnostic':''}`}>{target.classification}</span></div>
    <h2>{target.name}</h2><p className="object-type">{target.objectType}</p>
    {target.warnings[0]&&<p className="primary-warning">{target.warnings[0]}</p>}
    <dl className="observation-meta">
      <div><dt>Observed · UTC</dt><dd>{target.observation.timestampUtc.replace('T',' ').replace(/\.\d+$/,'')}</dd></div>
      <div><dt>Detector / release</dt><dd>{target.observation.detector} · {target.observation.release.toUpperCase()}</dd></div>
      {target.observation.processingVersion&&<div><dt>Processing version</dt><dd>{target.observation.processingVersion}</dd></div>}
      <div><dt>Effective wavelength</dt><dd>{target.observation.wavelengthUm?.toFixed(5)??'Unavailable'} μm</dd></div>
      <div><dt>Fixed ICRS center</dt><dd>{target.center.raDeg.toFixed(6)}° / {target.center.decDeg.toFixed(6)}°</dd></div>
    </dl>
    <div className="layer-control"><span className={`status-dot ${layerState}`}/><span>{layerState==='ready'?'WCS-registered local FITS':layerState==='loading'?'Loading local FITS layer…':'FITS layer unavailable'}</span>
      {layerState==='ready'&&<button className="text-button" onClick={onVisible} aria-pressed={visible}>{visible?'Hide layer':'Show layer'}</button>}</div>
    {layerState==='error'&&<div className="honest-fallback"><img src={assetUrl(target.assets.png)} alt={`${target.name}: local inspection image, not registered on the map`}/><p>Local inspection only. The map overlay could not be registered.</p></div>}
    <details className="science-warnings"><summary>Scientific context & limitations</summary><ul>{target.warnings.map(warning=><li key={warning}>{warning}</li>)}</ul><p>Display coverage and conservative science masks are separate. Visual intensities and PNGs are not quantitative photometry.</p></details>
    <button className="back-button" onClick={onBack}><span aria-hidden="true">↖</span> Back to Sky</button>
  </section>;
}
