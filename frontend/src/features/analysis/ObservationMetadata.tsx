import type {SequenceFrame,SkyTarget,PreparedDifference} from '../../types/sky';
export function ObservationMetadata({target,frame,difference}:{target:SkyTarget;frame:SequenceFrame;difference?:PreparedDifference}){
  const o=frame.observation;
  return <section aria-label="Observation metadata"><p className="eyebrow">PROVENANCE & QUALITY</p><h3>{difference?'Prepared residual and epoch metadata':'Individual observation'}</h3>
    {difference&&<p className="primary-warning">Current layer: {difference.id}, B − A. This is a prepared residual, not a single observation. Source IDs: {difference.aId} → {difference.bId}.</p>}
    <dl className="metadata-grid"><dt>Observation ID</dt><dd>{o.id}</dd><dt>UTC</dt><dd>{o.timestampUtc} UTC</dd><dt>Detector / release</dt><dd>{o.detector} / {o.release.toUpperCase()}</dd><dt>Processing version</dt><dd>{o.processingVersion??'Unavailable'}</dd><dt>Observation effective wavelength</dt><dd>{o.wavelengthUm?.toFixed(6)??'Unavailable'} μm</dd><dt>Spectral bandwidth</dt><dd>{o.bandwidthUm?.toFixed(6)??'Unavailable'} μm</dd><dt>Fixed spatial grid</dt><dd>{target.dimensions.width} × {target.dimensions.height} · ICRS<br/>{String(target.wcsHeader.CTYPE1)} / {String(target.wcsHeader.CTYPE2)}</dd></dl>
    <details className="metadata-details"><summary>Spatial WCS</summary><pre>{JSON.stringify(target.wcsHeader,null,2)}</pre></details>
    <details className="metadata-details"><summary>Available masks & quality flags</summary><p>Display coverage and conservative scientific masks are distinct. Valid display pixels do not validate a source measurement.</p><pre>{JSON.stringify(frame.quality??frame.masks,null,2)??'Unavailable'}</pre></details>
    <details className="metadata-details"><summary>Source provenance</summary><pre>{JSON.stringify(frame.provenance??null,null,2)}</pre></details>
  </section>;
}
