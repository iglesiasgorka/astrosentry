import type {BrightnessData,BrightnessPoint,SkyTarget} from '../../types/sky';
export const brightnessTime=(point:BrightnessPoint)=>Date.parse(point.timestampUtc+'Z');
export const acceptedBrightness=(data:BrightnessData)=>data.points.filter(p=>p.comparisonAccepted&&p.fluxMicroJy!==null&&Number.isFinite(p.fluxMicroJy));
export function brightnessDomain(data:BrightnessData){const times=data.points.map(brightnessTime);return times.length?[Math.min(...times),Math.max(...times)] as const:[0,1] as const;}

export function BrightnessInspector({target,index,onSelect,onClose}:{target:SkyTarget;index:number;onSelect:(index:number)=>void;onClose:()=>void}){
  const data=target.brightness!,points=data.points,accepted=acceptedBrightness(data),selected=points[index];
  const [start,end]=brightnessDomain(data),x=(point:BrightnessPoint)=>54+285*(brightnessTime(point)-start)/Math.max(1,end-start);
  const low=accepted.length?Math.min(...accepted.map(p=>p.fluxMicroJy!-(p.formalErrorMicroJy??0))):0;
  const high=accepted.length?Math.max(...accepted.map(p=>p.fluxMicroJy!+(p.formalErrorMicroJy??0))):1;
  const span=Math.max(high-low,Math.abs(high)*.1,1),bottom=low-.15*span,top=high+.15*span;
  const y=(flux:number)=>191-(flux-bottom)/(top-bottom)*140;
  const value=(flux:number|null|undefined)=>flux==null?'Unavailable':flux.toLocaleString('en-US',{maximumFractionDigits:2});
  return <section className="motion-inspector brightness-inspector floating-panel" aria-label="Brightness Inspector">
    <header><div><p className="eyebrow">ORIGINAL-PIXEL PHOTOMETRY</p><h3>Brightness Inspector</h3></div><button onClick={onClose} aria-label="Close Brightness Inspector">×</button></header>
    <p className="brightness-verdict"><strong>{data.classification.toUpperCase()}</strong> · {accepted.length} / {points.length} comparable accepted measurements</p>
    <p className="inspector-context">{data.interpretation}</p>
    <svg className="brightness-chart" viewBox="0 0 380 245" role="img" aria-label="Original-pixel aperture flux versus real UTC observation dates">
      <path d="M54 35 V199 H339" className="chart-grid"/>
      {accepted.length>0&&[bottom,(bottom+top)/2,top].map(v=><g key={v}><path d={`M54 ${y(v)} H339`} className="chart-grid"/><text x="48" y={y(v)+3} textAnchor="end">{value(v)}</text></g>)}
      <text transform="translate(13 117) rotate(-90)" textAnchor="middle">Aperture flux · μJy</text>
      {!accepted.length&&<text className="no-brightness" x="197" y="105" textAnchor="middle"><tspan x="197">No accepted brightness measurements</tspan><tspan x="197" dy="17">No variability curve inferred</tspan></text>}
      {selected&&<path className="selected-epoch-line" d={`M${x(selected)} 35 V199`}/>}
      {accepted.map(point=><g key={point.id}>{point.formalErrorMicroJy!==null&&<path className="brightness-errorbar" d={`M${x(point)} ${y(point.fluxMicroJy!+point.formalErrorMicroJy)} V${y(point.fluxMicroJy!-point.formalErrorMicroJy)} M${x(point)-4} ${y(point.fluxMicroJy!+point.formalErrorMicroJy)} h8 M${x(point)-4} ${y(point.fluxMicroJy!-point.formalErrorMicroJy)} h8`}/>}<circle cx={x(point)} cy={y(point.fluxMicroJy!)} r={point.id===selected?.id?5:3.5} className="brightness-point"/></g>)}
      {points.map((point,i)=><g key={point.id} role="button" tabIndex={0} aria-label={`Select brightness epoch ${i+1}: ${point.timestampUtc} UTC`} aria-pressed={i===index} onClick={()=>onSelect(i)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(i);}}}>
        <title>{point.timestampUtc} UTC — {point.comparisonAccepted?'accepted measurement':'observation date only; flux rejected'}</title>
        <rect x={x(point)-3} y="195" width="6" height="18" fill="transparent"/><path d={`M${x(point)} 197 V207`} className={i===index?'epoch-tick selected':'epoch-tick'}/>
      </g>)}
      <text x="54" y="222">{points[0]?.timestampUtc.slice(0,10)}</text><text x="339" y="222" textAnchor="end">{points.at(-1)?.timestampUtc.slice(0,10)}</text>
      <text x="197" y="239" textAnchor="middle">UTC · ticks select real epochs, not flux values</text>
    </svg>
    {selected&&<><p className="brightness-date">Selected: {selected.timestampUtc.replace('T',' ')} UTC · {selected.wavelengthUm?.toFixed(6)} μm</p>
    <dl className="motion-values"><div><dt>In-aperture flux</dt><dd>{value(selected.fluxMicroJy)} μJy</dd></div><div><dt>Formal error · incomplete</dt><dd>{value(selected.formalErrorMicroJy)} μJy</dd></div><div><dt>Relative flux / change</dt><dd>{value(selected.relativeFlux)} / {value(selected.relativeChangePercent)}%</dd></div><div><dt>Aperture valid pixels</dt><dd>{selected.apertureValidFraction==null?'Unavailable':(100*selected.apertureValidFraction).toFixed(1)+'%'}</dd></div></dl>
    <p className="inspector-caution">{selected.reason}</p><p className="brightness-flags">Core flags: {Object.entries(selected.coreFlags).map(([name,count])=>`${name}: ${count}`).join(' · ')||'No set flags'}</p></>}
    <details className="position-table"><summary>Reference candidates & quality</summary><p>Independent compact field candidates; none are assumed constant. Stability requires comparable spectral responses.</p>{data.references.length?data.references.map(r=><p key={r.id}>{r.id}: {r.acceptedEpochs} valid apertures; comparable spectra: {r.spectrallyMatched?'yes':'no'}; relative scatter: {value(r.relativeScatter)}</p>):<p>No usable independent reference candidates.</p>}</details>
    <details className="position-table"><summary>Method & scientific limitations</summary><p>{data.method}</p>{data.warnings.map(warning=><p key={warning}>{warning}</p>)}<p>Relative ratios, if available, use one reference epoch and retain shared-denominator formal covariance in the manifest. No interpolation or total-error claim.</p></details>
  </section>;
}
