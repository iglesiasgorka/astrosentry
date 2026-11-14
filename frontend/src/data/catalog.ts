import type { Position, SkyCatalog, SkyTarget, TemporalSequence } from '../types/sky';

export const DATA_ROOT = `${import.meta.env.BASE_URL}data/`;
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const relative = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && !/^(?:[a-z]+:|\/)|\\|(?:^|\/)\.\.(?:\/|$)/i.test(v);

export function validateSequence(sequence:TemporalSequence,target:SkyTarget):void{
  if(!sequence||!Array.isArray(sequence.frames)||sequence.frames.length<2)throw new Error('A temporal sequence needs at least two real observations.');
  const display=sequence.display;
  if(!display?.common||!finite(display.vmin)||!finite(display.vmax)||display.vmax<=display.vmin||display.stretch!=='asinh')throw new Error('A sequence requires explicit common intensity limits.');
  const ids=new Set<string>();let previous=-Infinity;
  const validPosition=(p:Position|null)=>p===null||(p&&[p.raDeg,p.decDeg,p.xFits,p.yFits,p.xImage,p.yImage].every(finite)&&p.raDeg>=0&&p.raDeg<360&&Math.abs(p.decDeg)<=90&&Math.abs(p.xImage-p.xFits)<1e-6&&Math.abs(p.yImage-(target.dimensions.height-1-p.yFits))<1e-6);
  for(const frame of sequence.frames){
    const timestamp=Date.parse(frame.observation?.timestampUtc+'Z');
    if(!frame.id||ids.has(frame.id)||!Number.isFinite(timestamp)||timestamp<=previous)throw new Error('Temporal observations must be unique and chronological.');
    ids.add(frame.id);previous=timestamp;
    if(!relative(frame.assets?.fits)||!relative(frame.assets?.png)||!relative(frame.assets?.masks))throw new Error('Temporal resources must use local relative paths.');
    if(!frame.display||frame.display.vmin!==display.vmin||frame.display.vmax!==display.vmax||frame.display.stretch!==display.stretch)throw new Error('Per-frame auto scaling is forbidden.');
    if(!validPosition(frame.expectedPosition)||!validPosition(frame.measuredPosition))throw new Error('Invalid sky positions or FITS/PNG pixel convention.');
    if(!Array.isArray(frame.warnings))throw new Error('Temporal quality metadata are missing.');
    if(target.id==='barnard'&&frame.measuredPosition!==null)throw new Error('The diagnostic Barnard sequence has no reliable measured positions.');
  }
  if(target.id==='m101'&&sequence.motion!==null)throw new Error('M101 is a registration example, without motion measurements.');
}

export function validateCatalog(value: unknown): SkyCatalog {
  if (!value || typeof value !== 'object') throw new Error('The local sky catalog is missing.');
  const input = value as { version?: unknown; targets?: unknown };
  if (input.version !== 1 || !Array.isArray(input.targets) || input.targets.length === 0) throw new Error('Unsupported or empty sky catalog. Run the web data exporter.');
  const ids = new Set<string>();
  for (const item of input.targets) {
    const t = item as SkyTarget;
    if (!t || typeof t.id !== 'string' || ids.has(t.id) || typeof t.name !== 'string') throw new Error('Target identifiers must be unique.');
    ids.add(t.id);
    if (!finite(t.center?.raDeg) || t.center.raDeg < 0 || t.center.raDeg >= 360 || !finite(t.center.decDeg) || Math.abs(t.center.decDeg) > 90) throw new Error('Invalid ICRS field center.');
    if (!Number.isInteger(t.dimensions?.width) || !Number.isInteger(t.dimensions?.height) || t.dimensions.width <= 0 || t.dimensions.height <= 0 || !finite(t.pixelScaleArcsec) || t.pixelScaleArcsec <= 0) throw new Error('Invalid field dimensions or angular scale.');
    if (!Array.isArray(t.footprint) || t.footprint.length !== 4 || t.footprint.some(p => !Array.isArray(p) || p.length !== 2 || !p.every(finite) || p[0] < 0 || p[0] >= 360 || Math.abs(p[1]) > 90)) throw new Error('Invalid WCS footprint.');
    if (!t.wcsHeader || !relative(t.assets?.fits) || !relative(t.assets?.png) || (t.assets.alignedFits && !relative(t.assets.alignedFits))) throw new Error('The catalog must reference local relative assets.');
    if (!finite(t.angularSizeDeg?.width) || !finite(t.angularSizeDeg?.height) || t.angularSizeDeg.width <= 0 || t.angularSizeDeg.height <= 0) throw new Error('Invalid WCS field extent.');
    if (!t.observation?.id || !t.observation.timestampUtc || !Array.isArray(t.warnings) || typeof t.classification !== 'string') throw new Error('Observation provenance is incomplete.');
    if(t.sequence)validateSequence(t.sequence,t);
  }
  return input as SkyCatalog;
}

export async function loadCatalog(signal?: AbortSignal): Promise<SkyCatalog> {
  const response = await fetch(`${DATA_ROOT}catalog.json`, { signal });
  if (!response.ok) throw new Error(`Local catalog could not load (HTTP ${response.status}). Run scripts/export_web_data.py.`);
  return validateCatalog(await response.json());
}

export function assetUrl(path: string): string {
  if (!relative(path)) throw new Error('Expected a relative local asset.');
  return new URL(DATA_ROOT + path, window.location.href).href;
}
