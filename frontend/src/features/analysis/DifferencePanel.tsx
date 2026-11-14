import type {PreparedDifference,SkyTarget} from '../../types/sky';
import {assetUrl} from '../../data/catalog';
export function DifferencePanel({target,difference,layer,visible,onVisible,onBack}:{target:SkyTarget;difference:PreparedDifference;layer:string;visible:boolean;onVisible:()=>void;onBack:()=>void}){
  const frames=target.sequence!.frames,a=frames.find(f=>f.id===difference.aId)!,b=frames.find(f=>f.id===difference.bId)!;
  return <section className="target-preview difference-panel floating-panel" aria-label="Difference inspection">
    <div className="preview-eyebrow"><span>CHANGE EXPLORER</span><span className="classification">{difference.classification}</span></div>
    <h2>Difference B − A</h2><p className="object-type">{target.name} · signed surface-brightness residual</p>
    <dl className="observation-meta"><div><dt>Epoch A · UTC</dt><dd>{a.observation.timestampUtc.replace('T',' ')}</dd></div><div><dt>Epoch B · UTC</dt><dd>{b.observation.timestampUtc.replace('T',' ')}</dd></div><div><dt>A / B wavelength</dt><dd>{a.observation.wavelengthUm?.toFixed(6)} / {b.observation.wavelengthUm?.toFixed(6)} μm</dd></div><div><dt>Units / valid area</dt><dd>{difference.units} / {(difference.validFraction*100).toFixed(1)}%</dd></div></dl>
    <div className="residual-legend" aria-label="Signed residual scale"><div/><span>{difference.display.vmin.toFixed(4)}<strong>0</strong>+{difference.display.vmax.toFixed(4)}</span><p>Blue: negative · white: zero · red: positive<br/>Invalid pixels are transparent; sky context may show through.</p></div>
    <p className="primary-warning">Uncorrected B − A on the shared science-valid mask. No PSF matching, gain normalization or significance calculation. Residuals can reflect background and instrumental effects.</p>
    <div className="layer-control"><span className={`status-dot ${layer}`}/><span>{layer==='ready'?'WCS-registered residual FITS':layer==='loading'?'Loading residual…':'Residual unavailable'}</span>{layer==='ready'&&<button className="text-button" onClick={onVisible}>{visible?'Hide layer':'Show layer'}</button>}</div>
    {layer==='error'&&<div className="honest-fallback"><img src={assetUrl(difference.assets.png)} alt="Unregistered residual inspection only"/><p>Local inspection only. The residual map layer did not load.</p></div>}
    <details className="science-warnings"><summary>Method, quality & limitations</summary><ul>{difference.warnings.map(w=><li key={w}>{w}</li>)}</ul><p>A dipole is not automatically motion or a new source.</p></details>
    <button className="back-button" onClick={onBack}>↖ Back to Sky</button>
  </section>;
}
