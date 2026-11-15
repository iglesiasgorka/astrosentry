import type { Position, SkyCatalog, SkyTarget, TemporalSequence } from '../types/sky';
import {API_BASE} from './apiConfig';

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
    const allowedDisplays=sequence.groups?.filter(g=>g.frameIds.includes(frame.id)).map(g=>g.display)??[display];
    if(!frame.display||!allowedDisplays.some(d=>frame.display.vmin===d.vmin&&frame.display.vmax===d.vmax&&frame.display.stretch===d.stretch))throw new Error('Per-frame auto scaling is forbidden.');
    if(!validPosition(frame.expectedPosition)||!validPosition(frame.measuredPosition))throw new Error('Invalid sky positions or FITS/PNG pixel convention.');
    if(!Array.isArray(frame.warnings))throw new Error('Temporal quality metadata are missing.');
    if(target.id==='barnard'&&frame.measuredPosition!==null)throw new Error('The diagnostic Barnard sequence has no reliable measured positions.');
  }
  if(sequence.groups){
    if(!sequence.groups.length||!sequence.groups.some(g=>g.id===sequence.defaultGroupId)||new Set(sequence.groups.map(g=>g.id)).size!==sequence.groups.length)throw new Error('Invalid comparison groups.');
    for(const group of sequence.groups){
      if(!group.frameIds.length||new Set(group.frameIds).size!==group.frameIds.length||group.frameIds.some(id=>!ids.has(id))||!finite(group.display.vmin)||!finite(group.display.vmax)||group.display.vmax<=group.display.vmin||!group.display.common)throw new Error('Invalid group members or shared intensity limits.');
      const members=sequence.frames.filter(f=>group.frameIds.includes(f.id));
      if(group.comparison&&members.length>1){const first=members[0].observation;
        if(members.some(f=>f.observation.detector!==first.detector||f.observation.release!==first.release))throw new Error('A comparison group mixes detectors or releases.');
        const wavelengths=members.map(f=>f.observation.wavelengthUm),bandwidths=members.map(f=>f.observation.bandwidthUm);
        if(!wavelengths.every(finite)||!bandwidths.every(finite)||Math.max(...wavelengths)-Math.min(...wavelengths)>.5*Math.min(...bandwidths))throw new Error('Spectrally incompatible comparison group.');
      }
    }
  }
  for(const difference of sequence.differences??[]){
    if(!ids.has(difference.aId)||!ids.has(difference.bId)||difference.aId===difference.bId||!relative(difference.assets.fits)||!relative(difference.assets.png)||!relative(difference.assets.mask)||difference.display.vmin!==-difference.display.vmax||difference.display.vmax<=0||difference.display.stretch!=='linear')throw new Error('Invalid prepared signed difference.');
    if(!sequence.groups?.some(g=>g.comparison&&g.frameIds.includes(difference.aId)&&g.frameIds.includes(difference.bId)))throw new Error('Difference pair must belong to a compatible group.');
  }
  if(sequence.historicalPair&&(!ids.has(sequence.historicalPair.aId)||!ids.has(sequence.historicalPair.bId)))throw new Error('Historical motion pair is missing.');
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
    if(t.brightness){const b=t.brightness;
      if(!Array.isArray(b.points)||b.points.length!==t.sequence?.frames.length||!Array.isArray(b.references)||!Array.isArray(b.warnings))throw new Error('Incomplete brightness manifest.');
      b.points.forEach((p,i)=>{if(p.id!==t.sequence!.frames[i].id||p.timestampUtc!==t.sequence!.frames[i].observation.timestampUtc)throw new Error('Brightness epochs must match the temporal frames.');
        if(p.comparisonAccepted&&(!p.qualityAccepted||!finite(p.fluxMicroJy)||!finite(p.formalErrorMicroJy)||p.formalErrorMicroJy<0))throw new Error('Accepted brightness requires a real flux and formal uncertainty.');
      });
    }
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
  if(path.startsWith('dynamic/')){if(!API_BASE)throw new Error('This prepared region requires its processing service.');return API_BASE+'/assets/'+path;}
  return new URL(DATA_ROOT + path, window.location.href).href;
}
