import type {SkyTarget} from '../../types/sky';

const number=(value:number|null|undefined,digits=5)=>value==null?'Unavailable':value.toFixed(digits);
export function MotionInspector({target,onClose}:{target:SkyTarget;onClose:()=>void}){
  const sequence=target.sequence!;
  const positions=sequence.frames.flatMap(frame=>[frame.expectedPosition,frame.measuredPosition]).filter(p=>p!==null);
  if(!positions.length)return null;
  const xs=positions.map(p=>p.xFits),ys=positions.map(p=>p.yFits);
  const centerX=(Math.min(...xs)+Math.max(...xs))/2,centerY=(Math.min(...ys)+Math.max(...ys))/2;
  const span=Math.max(.5,(Math.max(...xs)-Math.min(...xs))*1.8,(Math.max(...ys)-Math.min(...ys))*1.8);
  const lowX=centerX-span/2,lowY=centerY-span/2;
  const x=(v:number)=>65+220*(v-lowX)/span,y=(v:number)=>265-220*(v-lowY)/span;
  const motion=sequence.motion;
  const reference=sequence.astrometricReference as {main_id?:string;source?:string;proper_motion_bibcode?:string;epoch_note?:string}|null;
  return <section className="motion-inspector floating-panel" aria-label="Motion Inspector">
    <header><div><p className="eyebrow">FIXED-GRID ASTROMETRY</p><h3>{target.id==='barnard'?'Prediction Inspector':'Motion Inspector'}</h3></div><button aria-label="Close Motion Inspector" onClick={onClose}>×</button></header>
    <p className="inspector-context">{target.id==='barnard'?'Invalid and saturated source pixels: predicted positions only; no accepted centroid.':sequence.frames.some(f=>f.measuredPosition)?'Exploratory apparent displacement, not a significant-motion detection. Formal errors are incomplete; reference RMS is diagnostic.':'Predicted motion only. No accepted measured displacement or formal endpoint error. Reference RMS is diagnostic.'}</p>
    {motion&&<dl className="motion-values">
      <div><dt>Apparent measured shift</dt><dd>{number(motion.measuredDisplacementArcsec)}″ / {number(motion.measuredDisplacementPixels)} px</dd></div>
      <div><dt>Expected linear shift</dt><dd>{number(motion.expectedDisplacementArcsec)}″</dd></div>
      <div><dt>Elapsed time</dt><dd>{number(motion.timeSeparationDays,3)} days</dd></div>
      <div><dt>Reference RMS · diagnostic</dt><dd>{number(motion.referenceRmsArcsec)}″ ({motion.referenceCount??'—'} references)</dd></div>
      <div><dt>Formal endpoint error · incomplete</dt><dd>{number(motion.formalEndpointErrorArcsec)}″</dd></div>
    </dl>}
    <details className="position-table"><summary>Pair interpretation & caveats</summary><p>{sequence.interpretation}</p></details>
    <svg viewBox="0 0 345 310" className="motion-chart" role="img" aria-label="Magnified positions on a fixed pixel grid, north up and east left">
      <defs><marker id="motion-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L8 4 L0 8" fill="#ffb473"/></marker></defs>
      {[0,.25,.5,.75,1].map(t=><g key={t}><path className="chart-grid" d={`M ${65+t*220} 45 V 265 M 65 ${265-t*220} H 285`}/><text x={65+t*220} y="280" textAnchor="middle">{(lowX+t*span).toFixed(2)}</text><text x="57" y={268-t*220} textAnchor="end">{(lowY+t*span).toFixed(2)}</text></g>)}
      <text x="175" y="302" textAnchor="middle">Fixed-grid x · pixels (east ←)</text><text transform="translate(12 155) rotate(-90)" textAnchor="middle">Fixed-grid y · pixels (north ↑)</text>
      {sequence.frames.length===2&&sequence.frames.every(f=>f.measuredPosition)&&<path className="measured-vector" markerEnd="url(#motion-arrow)" d={`M ${x(sequence.frames[0].measuredPosition!.xFits)} ${y(sequence.frames[0].measuredPosition!.yFits)} L ${x(sequence.frames[1].measuredPosition!.xFits)} ${y(sequence.frames[1].measuredPosition!.yFits)}`}/>}
      {sequence.frames.length===2&&sequence.frames.every(f=>f.expectedPosition)&&<path className="expected-vector" d={`M ${x(sequence.frames[0].expectedPosition!.xFits)} ${y(sequence.frames[0].expectedPosition!.yFits)} L ${x(sequence.frames[1].expectedPosition!.xFits)} ${y(sequence.frames[1].expectedPosition!.yFits)}`}/>}
      {sequence.frames.map((frame,index)=><g key={frame.id}>
        {frame.expectedPosition&&<g className="expected-mark" transform={`translate(${x(frame.expectedPosition.xFits)} ${y(frame.expectedPosition.yFits)})`}><path d="M -7 0 H 7 M 0 -7 V 7"/><text x="9" y="-8">E{index+1}</text></g>}
        {frame.measuredPosition&&<g className="measured-mark" transform={`translate(${x(frame.measuredPosition.xFits)} ${y(frame.measuredPosition.yFits)})`}><circle r="5"/><text x="9" y="12">M{index+1}</text></g>}
      </g>)}
    </svg>
    <p className="position-legend"><span>+ Expected (cyan)</span><span>{sequence.frames.some(f=>f.measuredPosition)?'○ Measured (orange)':'○ Measured: unavailable'}</span></p>
    <details className="position-table"><summary>Epoch positions & formal errors</summary>{sequence.frames.map((frame,index)=><div key={frame.id}><strong>Epoch {index+1} · {frame.observation.timestampUtc.slice(0,10)} UTC</strong>
      <p>Expected RA/Dec: {frame.expectedPosition?`${frame.expectedPosition.raDeg.toFixed(9)}°, ${frame.expectedPosition.decDeg.toFixed(9)}°`:'Unavailable'}</p>
      <p>Measured RA/Dec: {frame.measuredPosition?`${frame.measuredPosition.raDeg.toFixed(9)}°, ${frame.measuredPosition.decDeg.toFixed(9)}°`:'null — no accepted measurement for this observation'}</p>
      <p>Formal centroid error: {number(frame.formalCentroidErrorArcsec)}″; {number(frame.formalCentroidErrorOriginalPixels)} original pixels (incomplete).</p>
    </div>)}</details>
    <p className="inspector-caution">Formal fit errors omit instrumental and reference-frame systematics. Reference RMS is a diagnostic, not detection significance. No parallax or binary orbit correction is included.</p>
    {reference&&<details className="position-table"><summary>Astrometric sources & prediction model</summary><p>{reference.main_id} · {reference.source}</p><p>Proper-motion reference: {reference.proper_motion_bibcode??'See source manifest'}</p><p>{reference.epoch_note}</p><p>{sequence.predictionModel}</p><a href="https://simbad.cds.unistra.fr/simbad/" target="_blank" rel="noreferrer">SIMBAD / CDS</a> · <a href="https://www.cosmos.esa.int/web/gaia" target="_blank" rel="noreferrer">ESA / Gaia</a></details>}
  </section>;
}
