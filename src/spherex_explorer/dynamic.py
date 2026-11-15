"""Small real temporal sequences using the existing SPHEREx scientific engine."""
import base64
import hashlib
import math
import json
from pathlib import Path
import threading

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from astropy.visualization import ImageNormalize, AsinhStretch
import matplotlib
matplotlib.use('Agg')
import numpy as np
from PIL import Image

from .alignment import common_grid, align_observation, save_aligned
from .acquisition import AcquisitionBudget
from .data_access import SearchParameters, query_observations, prepare_observations
from .fits_utils import write_manifest
from .observation import Observation
from .scientific_pipeline import initial_target_selection
from .targets import epoch_groups, select_spectral_sequence
from .web_export import sky_geometry, display_limits
from .sia_access import query_sia_observations

WORKSPACE = 'outputs/spx007b'

QUERY_LOCK = threading.Lock()
WARNINGS = ['Exploratory visual comparison only. No validated motion or variability measurement.',
            'PSF, spectral response, backgrounds and astrometric systematics are not matched.',
            'Display masks differ from conservative science masks. PNG intensities are not photometry.']


def parameters(data):
    if any(isinstance(data.get(k), bool) for k in ['ra','dec','size','detector']):
        raise ValueError('Numeric parameters cannot be booleans.')
    value = float(data.get('detector', 2))
    if not math.isfinite(value) or not value.is_integer():
        raise ValueError('Detector must be a finite integer.')
    detector = int(value)
    if detector != value:
        raise ValueError('Detector must be an integer.')
    p = SearchParameters(float(data['ra']), float(data['dec']), float(data.get('size', .1)), f'SPHEREx-D{detector}')
    if not .05 <= p.size <= .20:
        raise ValueError('Dynamic cutout width must be between 0.05 and 0.20 degrees.')
    return p


def search_key(p):
    return hashlib.sha256(f'{p.ra:.10f},{p.dec:.10f},{p.size:.4f},{p.bandpass}'.encode()).hexdigest()[:20]


def search(project, p, timeout=40, service='sia2', workspace=None):
    """Cache successful bounded metadata; never auto-retry a second service."""
    if service not in {'sia2','tap'}:
        raise ValueError('Choose the verified SIA2 adapter or explicit TAP option.')
    identifier = hashlib.sha256((search_key(p)+':'+service).encode()).hexdigest()[:20]
    root=Path(workspace) if workspace is not None else Path(project)/WORKSPACE
    destination = root/'searches'/f'{identifier}.json'
    if destination.exists():
        cached=json.loads(destination.read_text())
        for record in cached['records']:
            if service=='sia2':
                record['url']=f'{record["sia"]["access_url"]}?center={p.ra},{p.dec}&size={p.size}'
        write_manifest(destination,cached)
        return cached
    with QUERY_LOCK:
        if service == 'sia2':
            records, report = query_sia_observations(p, timeout, destination.parent/identifier)
        else:
            records = prepare_observations(query_observations(p, timeout=timeout))
            report = {'service':'IRSA TAP','coverage':'Center intersection only; not complete requested-grid coverage.'}
    visits = {r['observation_id']: number for number, group in enumerate(epoch_groups(records), 1) for r in group}
    result = {'id': identifier, 'parameters': {'ra': p.ra, 'dec': p.dec, 'size': p.size, 'detector': int(p.bandpass[-1])},
              'count': len(records), 'visitCount': len(set(visits.values())), 'records': records,
              'observations': [{'id': r['observation_id'], 'timestampUtc': r['timestamp'], 'mjd': r['mjd'],
                'detector': r['bandpass'], 'release': r['release'], 'processingVersion': r['processing_version'],
                'visit': visits[r['observation_id']], 'wavelengthUm': None,
                'wavelengthStatus': 'Requires local spectral WCS after FITS acquisition.'} for r in records],
              'query':report, 'completeArchiveSearch':True,
              'source':f'Official IRSA {service.upper()}; deduplicated observation/detector. Intersection is not complete field coverage; local wavelengths require FITS.'}
    write_manifest(destination, result)
    return result


def public_search(result):
    return {k: v for k, v in result.items() if k != 'records'}


def local_search(project, p):
    """Verified original-cutout coverage subset, explicitly not complete archive availability."""
    project=Path(project);records=[];seen=set();point=SkyCoord(p.ra*u.deg,p.dec*u.deg)
    grid,shape=common_grid(p.ra,p.dec,p.size,6.2)
    corners=grid.pixel_to_world(np.array([-.5,shape[1]-.5,shape[1]-.5,-.5]),np.array([-.5,-.5,shape[0]-.5,shape[0]-.5]))
    sources=['outputs/observations.json','outputs/spx002/barnard/observations.json',
        'outputs/spx002b/epsilon_indi_b/observations.json','outputs/spx004a/rw_aur/preparation/observations.json',
        'outputs/spx004a/r_dra/preparation/observations.json','outputs/spx006c/wise0855/observations.json']
    for source in sources:
        path=project/source
        if not path.exists():continue
        for record in json.loads(path.read_text())['observations']:
            if int(record['detector'])!=int(p.bandpass[-1]):continue
            local=Path(record['local_path']);local=(local if local.is_absolute() else project/local).resolve()
            if not local.is_relative_to((project/'data/raw').resolve()) or not local.is_file():continue
            identity=(record['observation_id'],int(record['detector']))
            if identity in seen:continue
            with fits.open(local,memmap=True) as hdus:
                header=hdus['IMAGE'].header;wcs=WCS(header);height,width=header['NAXIS2'],header['NAXIS1']
                x,y=wcs.world_to_pixel(point)
                if not(np.isfinite(x+y) and -.5<=x<width-.5 and -.5<=y<height-.5):continue
                cx,cy=wcs.world_to_pixel(corners)
                covered=bool(np.isfinite(cx+cy).all() and ((cx>=-.5)&(cx<width-.5)&(cy>=-.5)&(cy<height-.5)).all())
            copied={**record,'cached_local_path':local.relative_to(project).as_posix(),'cachedRequestedRegionCovered':covered,
                'requested_cutout_url':f'https://irsa.ipac.caltech.edu/{record["artifact_uri"]}?center={p.ra},{p.dec}d&size={p.size}',
                'mjd':record.get('midpoint_mjd',record['mjd']),'timestamp':record.get('midpoint_utc',record['timestamp']),
                'bandpass':p.bandpass}
            spectral=Observation.read(local,record['release']).spectral_at(point)
            copied.update(wavelength_um=spectral['wavelength_um'],bandwidth_um=spectral['bandwidth_um'],target_quality_ok=True)
            records.append(copied);seen.add(identity)
    records.sort(key=lambda r:r['mjd']);visits={r['observation_id']:n for n,group in enumerate(epoch_groups(records),1) for r in group}
    identifier=hashlib.sha256((search_key(p)+':local-cache').encode()).hexdigest()[:20]
    result={'id':identifier,'parameters':{'ra':p.ra,'dec':p.dec,'size':p.size,'detector':int(p.bandpass[-1])},
        'count':len(records),'visitCount':len(set(visits.values())),'records':records,'completeArchiveSearch':False,
        'source':'Verified local original-FITS coverage subset. The archive was not queried; this is not a complete availability search.',
        'observations':[{'id':r['observation_id'],'timestampUtc':r['timestamp'],'mjd':r['mjd'],'detector':p.bandpass,
            'release':r['release'],'processingVersion':r['processing_version'],'visit':visits[r['observation_id']],
            'wavelengthUm':r['wavelength_um'],'cachedRequestedRegionCovered':r['cachedRequestedRegionCovered']} for r in records]}
    write_manifest(project/WORKSPACE/'searches'/f'{identifier}.json',result)
    return result


def export_aligned_sequence(items, records, root, prefix, key, name, warnings=None, positions=None):
    """Export lightweight fixed-grid display derivatives, preserving science masks."""
    if len(items) < 2:
        raise ValueError('At least two real readable observations are required.')
    ordered = sorted(zip(items, records), key=lambda pair: pair[0].observation.midpoint.mjd)
    items, records = map(list, zip(*ordered))
    first = items[0]
    for item in items:
        if item.image.shape != first.image.shape or dict(item.wcs.to_header()) != dict(first.wcs.to_header()):
            raise ValueError('Temporal frames must share exactly one fixed WCS and shape.')
    low, high = display_limits(np.concatenate([i.display_image[np.isfinite(i.display_image)] for i in items]))
    display = {'vmin':low, 'vmax':high, 'stretch':'asinh', 'common':True, 'pngAsinhParameter':.1}
    norm = ImageNormalize(vmin=low,vmax=high,stretch=AsinhStretch())
    cmap = matplotlib.colormaps['gray'].with_extremes(bad='#683a68')
    root = Path(root);frames = [];cluster_records = []
    for item, record in zip(items, records):
        obs = item.observation;identifier = f'{obs.observation_id}D{int(record["detector"])}'
        assets = {kind: f'{prefix}/frames/{identifier}{suffix}' for kind,suffix in [('fits','.fits'),('png','.png'),('masks','.masks.json')]}
        destination = root/assets['fits'];destination.parent.mkdir(parents=True,exist_ok=True)
        header = item.wcs.to_header();header['BUNIT']=obs.header.get('BUNIT','');header['OBSID']=obs.observation_id
        header['DATE-AVG']=obs.midpoint.utc.isot;header['DATAMIN']=low;header['DATAMAX']=high
        fits.PrimaryHDU(item.display_image.astype(np.float32),header).writeto(destination,overwrite=True)
        Image.fromarray(np.flipud(cmap(norm(np.ma.masked_invalid(item.display_image)),bytes=True))).save(root/assets['png'])
        pack=lambda m:base64.b64encode(np.packbits(m.ravel(),bitorder='little').tobytes()).decode()
        write_manifest(root/assets['masks'],{'encoding':'packed-bits-base64','bitOrder':'little','shape':list(item.image.shape),
            'origin':'FITS bottom-left; row-major y,x','displayValid':pack(item.display_coverage),'scienceValid':pack(item.coverage)})
        position = (positions or {}).get(obs.observation_id, {})
        expected = position.get('expectedPosition')
        spectral = obs.spectral_at(SkyCoord((expected['raDeg'] if expected else first.wcs.wcs.crval[0])*u.deg,
                                           (expected['decDeg'] if expected else first.wcs.wcs.crval[1])*u.deg))
        observation = {'id':obs.observation_id,'timestampUtc':obs.midpoint.utc.isot,'detector':f'SPHEREx-D{int(record["detector"])}',
            'release':record['release'],'processingVersion':record['processing_version'],
            'wavelengthUm':spectral['wavelength_um'],'bandwidthUm':spectral['bandwidth_um'],
            'wavelengthReference':'Catalog-predicted position at this epoch' if expected else 'Fixed requested field center'}
        frames.append({'id':identifier,'observation':observation,'assets':assets,'display':display,
            'expectedPosition':position.get('expectedPosition'),'measuredPosition':position.get('measuredPosition'),
            'formalCentroidErrorArcsec':position.get('formalCentroidErrorArcsec'),'formalCentroidErrorOriginalPixels':None,
            'warnings':list(warnings or WARNINGS),'quality':obs.quality_at(SkyCoord(first.wcs.wcs.crval[0]*u.deg,first.wcs.wcs.crval[1]*u.deg)),
            'masks':{'displayValidFraction':float(item.display_coverage.mean()),'scienceValidFraction':float(item.coverage.mean())},
            'provenance':{'sourceUrl':record['url'],'sourceSha256':hashlib.sha256(obs.path.read_bytes()).hexdigest()}})
        cluster_records.append({'observation_id':identifier,'mjd':float(obs.midpoint.mjd),'detector':int(record['detector']),
            'release':record['release'],'wavelength_um':spectral['wavelength_um'],'bandwidth_um':spectral['bandwidth_um'],
            'target_quality_ok':bool(item.coverage.mean() >= .25)})
    cluster = select_spectral_sequence(cluster_records, limit=len(frames))
    visits={r['observation_id']:number for number,visit in enumerate(epoch_groups(cluster_records),1) for r in visit}
    for frame in frames:frame['visitId']=f'visit-{visits[frame["id"]]}'
    groups = []
    if len(cluster) >= 2:
        groups.append({'id':'compatible','label':'Preliminary spectral group · exploratory only','frameIds':[r['observation_id'] for r in cluster],
            'comparison':True,'display':display,'warnings':list(warnings or WARNINGS)})
    groups.append({'id':'inspection','label':'All available observations · inspection only','frameIds':[f['id'] for f in frames],
        'comparison':False,'display':display,'warnings':['Wavelengths or quality may differ; this group is not a homogeneous temporal measurement.']})
    geometry = sky_geometry(first.wcs,first.image.shape,*first.wcs.wcs.crval,6.2)
    target = {'id':key,'name':name,'objectType':'User-selected sky region','classification':'diagnostic',**geometry,
        'observation':frames[0]['observation'],'assets':frames[0]['assets'],'display':display,'warnings':list(warnings or WARNINGS),
        'sequence':{'frames':frames,'display':display,'motion':None,'classification':'diagnostic','warnings':list(warnings or WARNINGS),
            'interpretation':'Real fixed-grid observations; exploratory visual inspection, not a validated motion or variability result.',
            'predictionModel':None,'astrometricReference':None,'groups':groups,'defaultGroupId':groups[0]['id'],
            'availableObservationCount':len(frames),'independentVisitCount':len(set(visits.values()))}}
    write_manifest(root/prefix/'target.json',target)
    return target


def prepare_region(project, result, count=4, cancel=None, budget=None, workspace=None):
    if type(count) is not int or count not in [2,3,4]:
        raise ValueError('Prepare between two and four observations.')
    p=parameters(result['parameters']);job=hashlib.sha256(f'{result["id"]}:{count}'.encode()).hexdigest()[:20]
    root=Path(workspace) if workspace is not None else Path(project)/WORKSPACE
    directory=root/'jobs'/job;directory.mkdir(parents=True,exist_ok=True)
    # Prefer already validated, exact-request cutouts. Their local spectral WCS
    # can guide selection without interpreting detector-wide metadata as lambda.
    available=[];cached=[];point=SkyCoord(p.ra*u.deg,p.dec*u.deg)
    for original in result['records']:
        record=dict(original)
        digest=hashlib.sha256(record['url'].encode()).hexdigest()[:16]
        paths=list((root/'raw').glob(f'*_{digest}.fits'))
        if paths:
            try:
                obs=Observation.read(paths[0],record['release'])
                spectral=obs.spectral_at(point)
                record.update(wavelength_um=spectral['wavelength_um'],bandwidth_um=spectral['bandwidth_um'],
                              target_quality_ok=bool((~obs.science_invalid).mean()>=.25))
                cached.append(record)
            except (OSError,ValueError):
                pass
        available.append(record)
    compatible=select_spectral_sequence(available,limit=count)
    selected=compatible if len(compatible)>=2 else []
    pool=cached if len(cached)>=count else available
    selected+=initial_target_selection([r for r in pool if r not in selected],count-len(selected)) if len(selected)<count else []
    grid,shape=common_grid(p.ra,p.dec,p.size,6.2)
    items=[];records=[];failures=[]
    budget=budget or AcquisitionBudget(project,root/'acquisition_ledger.json',limit=12,reservation=0)
    import time
    deadline=time.monotonic()+300
    consecutive_failures=0
    for record in selected:
        if cancel and cancel.is_set():
            raise InterruptedError('Preparation canceled before the next acquisition.')
        if time.monotonic() >= deadline:
            raise TimeoutError('Preparation exceeded its five-minute deadline.')
        try:
            if record.get('cachedRequestedRegionCovered'):
                path=(Path(project)/record['cached_local_path']).resolve()
                if not path.is_relative_to((Path(project)/'data/raw').resolve()):raise ValueError('Cached source escapes raw-data directory.')
            else:
                record=dict(record,url=record.get('requested_cutout_url',record['url']))
                path=budget.download(record['url'],root/'raw',purpose='dynamic')
            obs=Observation.read(path,record['release'])
            if obs.observation_id != record['observation_id'] or int(obs.header.get('DETECTOR',0)) != int(record['detector']):
                raise ValueError('Downloaded FITS identity/detector differs from the archive result.')
            with fits.open(path) as hdus:
                required={'PRIMARY','IMAGE','FLAGS','VARIANCE','ZODI','EPSF','WCS-WAVE'}
                if not required.issubset({h.name for h in hdus}):
                    raise ValueError('SPHEREx cutout lacks required scientific extensions.')
            if obs.midpoint is None:
                raise ValueError('Observation midpoint is missing.')
            aligned=align_observation(obs,grid,shape)
            if not np.isfinite(aligned.display_image).any():
                raise ValueError('No finite display pixels in the requested region.')
            from .scientific_pipeline import build_alignment_report
            save_aligned(aligned,directory/'aligned'/f'{obs.observation_id}.fits')
            items.append(aligned);records.append(record)
            consecutive_failures=0
        except Exception as error:
            failures.append({'id':record['observation_id'],'error':f'{type(error).__name__}: {error}'})
            consecutive_failures+=1
        write_manifest(directory/'preparation.json',{'parameters':result['parameters'],'selected':selected,'downloaded':len(items),'failures':failures})
        if consecutive_failures>=2:
            break
    warnings=list(WARNINGS)
    if failures:
        warnings.append(f'Partial preparation: {len(items)} of {len(selected)} selected observations are usable. Some acquisitions or scientific reads failed; no replacement frames were invented.')
    target=export_aligned_sequence(items,records,root/'assets',f'dynamic/{job}',f'region_{job}',f'Sky region {p.ra:.4f}°, {p.dec:+.4f}°',warnings=warnings)
    target['preparation']={'selectedCount':len(selected),'preparedCount':len(items),'failedObservationIds':[f['id'] for f in failures]}
    write_manifest(directory/'alignment_report.json',build_alignment_report(items,SkyCoord(p.ra*u.deg,p.dec*u.deg),shape,6.2))
    write_manifest(directory/'target.json',target)
    return target
