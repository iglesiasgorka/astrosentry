"""Offline inventory, extended display assets and conservative signed differences.

Only already downloaded original/registered observations are read. A residual is
an exploratory surface-brightness difference, never a significance image.
"""
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import shutil

from astropy import units as u
from astropy.io import fits
from astropy.wcs import WCS
import matplotlib
matplotlib.use('Agg')
from matplotlib.colors import LinearSegmentedColormap, Normalize
from astropy.visualization import ImageNormalize, AsinhStretch
import numpy as np
from PIL import Image

from .fits_utils import write_manifest
from .observation import Observation
from .targets import epoch_groups
from .web_export import display_limits, portable_asset

HISTORICAL_PAIR = ('2025W18_1B_0081_2', '2025W39_2A_0693_3')
RESIDUAL_COLORS = ['#2166ac', '#f7f7f7', '#b2182b']
RESIDUAL_WARNINGS = [
    'Exploratory signed residual, not a statistical significance or certified physical-change map.',
    'PSF, spectral response, background and astrometric systematics are not matched or fully validated.',
    'A positive/negative dipole is not automatically a real motion detection.',
    'Only the intersection of conservative science COVERAGE and finite aligned IMAGE pixels is used.',
    'No VAR_DIAG uncertainty propagation, background correction, gain normalization or PSF matching is applied.',
]


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def compatible_pair(a, b, fraction=.5, require_independent=True):
    """Preliminary local-bandwidth filter; not photometric-response certification."""
    if not 0 < fraction <= .5:
        raise ValueError('Spectral fraction must be in (0, 0.5].')
    if int(a['detector']) != int(b['detector']):
        raise ValueError('Difference requires the same detector.')
    if a['release'] != b['release']:
        raise ValueError('Difference requires the same release.')
    values = [a.get('wavelength_um'), b.get('wavelength_um'), a.get('bandwidth_um'), b.get('bandwidth_um')]
    if any(v is None or not np.isfinite(v) or v <= 0 for v in values):
        raise ValueError('Missing or invalid local spectral metadata.')
    separation = abs(values[0]-values[1])
    if separation > fraction*min(values[2:]):
        raise ValueError('Local wavelengths fail the declared compatibility filter.')
    if require_independent and abs(a['midpoint_mjd']-b['midpoint_mjd']) < 1:
        raise ValueError('The observations are not independent one-day-separated visits.')
    return {'wavelengthSeparationUm': separation, 'maximumSeparationUm': fraction*min(values[2:]),
            'timeSeparationDays': abs(a['midpoint_mjd']-b['midpoint_mjd']),
            'warning': 'Half-bandwidth screening is exploratory, not matched-response certification.'}


def assign_visit_ids(records, prefix):
    """Group chronological exposures; same-visit files are not independent epochs."""
    visits = {}
    chronological = [dict(record, mjd=record['midpoint_mjd']) for record in records]
    for number, group in enumerate(epoch_groups(chronological), 1):
        for record in group:
            visits[record['observation_id']] = f'{prefix}-visit-{number}'
    return visits


def signed_difference(a, b, valid_a, valid_b, wcs_a, wcs_b, unit_a, unit_b):
    """Return B-A in A's units with the conservative common mask and no correction."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.ndim != 2 or a.shape != b.shape or a.shape != np.shape(valid_a) or b.shape != np.shape(valid_b):
        raise ValueError('Difference shapes and mask dimensions must agree in two dimensions.')
    if dict(wcs_a.to_header(relax=True)) != dict(wcs_b.to_header(relax=True)):
        raise ValueError('Difference requires exactly the same fixed WCS.')
    if not unit_a or not unit_b:
        raise ValueError('Difference requires explicit compatible units.')
    ua, ub = u.Unit(unit_a), u.Unit(unit_b)
    if not ua.is_equivalent(ub) or not ua.is_equivalent(u.MJy/u.sr):
        raise ValueError('Difference requires compatible surface-brightness units.')
    valid = np.asarray(valid_a, dtype=bool) & np.asarray(valid_b, dtype=bool) & np.isfinite(a) & np.isfinite(b)
    if not valid.any():
        raise ValueError('Difference has no common finite science pixels.')
    result = np.full(a.shape, np.nan)
    result[valid] = b[valid]*(1*ub).to_value(ua)-a[valid]
    return result, valid


def read_aligned(path):
    with fits.open(path, memmap=False) as hdus:
        for name in ('IMAGE', 'DISPLAY', 'COVERAGE'):
            if name not in hdus:
                raise ValueError(f'Existing aligned file lacks real {name}: {Path(path).name}')
        return {'image': np.array(hdus['IMAGE'].data, dtype=float),
                'display': np.array(hdus['DISPLAY'].data, dtype=float),
                'valid': np.array(hdus['COVERAGE'].data, dtype=bool),
                'header': hdus['IMAGE'].header.copy(), 'wcs': WCS(hdus['IMAGE'].header)}


def inventory(project):
    """Inspect actual original files and visits; exclude aligned/display derivatives."""
    project = Path(project)
    sources = [('m101', 'outputs/observations.json', 'outputs/spx002/m101'),
               ('barnard', 'outputs/spx002/barnard/observations.json', 'outputs/spx002/barnard'),
               ('epsilon_indi_b', 'outputs/spx002b/epsilon_indi_b/observations.json', 'outputs/spx002b/epsilon_indi_b'),
               ('r_dra', 'outputs/spx004a/r_dra/preparation/observations.json', 'outputs/spx004a/r_dra/preparation'),
               ('rw_aur', 'outputs/spx004a/rw_aur/preparation/observations.json', 'outputs/spx004a/rw_aur/preparation')]
    known = {}
    for target, manifest_path, directory in sources:
        manifest = load_json(project/manifest_path)
        for record in manifest['observations']:
            path = Path(record['local_path'])
            path = path if path.is_absolute() else project/path
            aligned = project/directory/record.get('aligned_asset', f"aligned/{record['observation_id']}.fits")
            known[path.resolve()] = (target, record, aligned)
    records = []
    for path in sorted((project/'data/raw').rglob('*.fits')):
        entry = {'path': path.relative_to(project).as_posix(), 'validFits': False}
        try:
            if path.resolve() not in known:
                raise ValueError('Original file is not represented in existing scientific manifests.')
            target, record, aligned = known[path.resolve()]
            obs = Observation.read(path, record['release'])
            inspect = record.get('inspection', {})
            entry.update(target=target, observationId=obs.observation_id, detector=int(record['detector']),
                         release=record['release'], processingVersion=record['processing_version'],
                         timestampUtc=obs.midpoint.utc.isot, mjd=float(obs.midpoint.utc.mjd),
                         wavelengthUm=record.get('wavelength_um', inspect.get('effective_wavelength_um')),
                         bandwidthUm=record.get('bandwidth_um', inspect.get('spectral_bandwidth_um')),
                         originalShape=list(obs.image.shape), validFits=True,
                         originalScienceValidFraction=float((~obs.science_invalid).mean()),
                         sourceQuality=record.get('target_quality'),
                         registeredAsset=aligned.relative_to(project).as_posix() if aligned.exists() else None,
                         originalSha256=hashlib.sha256(path.read_bytes()).hexdigest())
            if aligned.exists():
                prepared = read_aligned(aligned)
                entry['registeredScienceValidFraction'] = float(prepared['valid'].mean())
                entry['registeredShape'] = list(prepared['image'].shape)
        except Exception as error:
            entry['error'] = f'{type(error).__name__}: {error}'
        records.append(entry)
    for target in {r.get('target') for r in records if r['validFits']}:
        for detector in {r['detector'] for r in records if r.get('target') == target}:
            subset = [r for r in records if r.get('target') == target and r.get('detector') == detector and r['validFits']]
            for number, group in enumerate(epoch_groups(subset), 1):
                for record in group:
                    record['visitId'] = f'{target}-D{detector}-visit-{number}'
    counts = {target: sum(r.get('target') == target and r['validFits'] for r in records) for target, _, _ in sources}
    return {'originalFitsCount': len(records), 'validOriginalFitsCount': sum(r['validFits'] for r in records),
            'uniqueObservationDetectorCount': len({(r.get('observationId'), r.get('detector')) for r in records if r['validFits']}),
            'countsByTarget': counts, 'visitDefinition': 'Consecutive records separated by at least one day start a visit group, per target and detector; files and detectors are not independent epoch counts.',
            'records': records}


def _pack(mask):
    return base64.b64encode(np.packbits(mask.ravel(), bitorder='little').tobytes()).decode('ascii')


def _position(centroid, measured, height):
    measurement = centroid.get('measurement', {})
    if measured and not measurement.get('accepted'):
        return None
    values = [centroid.get('measured_x'), centroid.get('measured_y'), measurement.get('ra_deg'), measurement.get('dec_deg')] if measured else [centroid.get('expected_x'), centroid.get('expected_y'), centroid.get('expected_ra_deg'), centroid.get('expected_dec_deg')]
    if any(value is None for value in values):
        return None
    x, y, ra, dec = values
    return {'raDeg': ra, 'decDeg': dec, 'xFits': x, 'yFits': y, 'xImage': x, 'yImage': height-1-y}


def _export_frame(root, target, record, aligned, cuts):
    prefix = f"{target['id']}/frames/{record['observation_id']}"
    assets = {'fits': prefix+'.fits', 'png': prefix+'.png', 'masks': prefix+'.masks.json'}
    (root/assets['fits']).parent.mkdir(parents=True, exist_ok=True)
    values = aligned['display']
    header = aligned['wcs'].to_header(relax=True)
    header['BUNIT'] = aligned['header']['BUNIT'];header['OBSID'] = record['observation_id']
    header['DATE-AVG'] = record['midpoint_utc'];header['DATAMIN'] = cuts['vmin'];header['DATAMAX'] = cuts['vmax']
    header['HISTORY'] = 'SPX-004B fixed-grid display derivative from existing aligned DISPLAY; no recentering.'
    fits.PrimaryHDU(values.astype(np.float32), header).writeto(root/assets['fits'], overwrite=True)
    rgba = matplotlib.colormaps['gray'].with_extremes(bad='#683a68')(ImageNormalize(vmin=cuts['vmin'], vmax=cuts['vmax'], stretch=AsinhStretch())(np.ma.masked_invalid(values)), bytes=True)
    Image.fromarray(np.flipud(rgba)).save(root/assets['png'])
    write_manifest(root/assets['masks'], {'encoding': 'packed-bits-base64', 'bitOrder': 'little', 'shape': list(values.shape),
        'origin': 'FITS bottom-left; row-major y,x', 'displayValid': _pack(np.isfinite(values)), 'scienceValid': _pack(aligned['valid'])})
    centroid = record.get('target_centroid', {})
    measurement = centroid.get('measurement', {})
    return {'id': record['observation_id'], 'observation': {'id': record['observation_id'], 'timestampUtc': record['midpoint_utc'],
        'startUtc': record.get('start_utc'), 'detector': f"SPHEREx-D{int(record['detector'])}", 'release': record['release'],
        'processingVersion': record['processing_version'], 'mjd': record['midpoint_mjd'],
        'wavelengthUm': record['wavelength_um'], 'bandwidthUm': record['bandwidth_um'],
        'wavelengthReference': 'Existing local target-position spectral metadata; not a detector-wide wavelength.'},
        'assets': assets, 'display': cuts, 'expectedPosition': _position(centroid, False, values.shape[0]),
        'measuredPosition': _position(centroid, True, values.shape[0]),
        'formalCentroidErrorArcsec': measurement.get('formal_error_arcsec'),
        'formalCentroidErrorOriginalPixels': measurement.get('formal_error_pixels'),
        'warnings': ['Inspection-only outside the historical compatible pair; wavelength/response changes must not be called temporal variability.'],
        'masks': {'displayValidFraction': float(np.isfinite(values).mean()), 'scienceValidFraction': float(aligned['valid'].mean()), 'scienceMaskAvailable': True},
        'provenance': {'sourceUrl': record['url'], 'sourceAlignedFits': record.get('_aligned_relative', record['aligned_asset']),
                       'sourceSha256': record.get('_aligned_sha256'),
                       'newAstrometryComputed': False}}


def export_difference(root, private, path_a, path_b, record_a, record_b):
    """One uncorrected historical pair only; no quadratic pair asset expansion."""
    spectral = compatible_pair(record_a, record_b)
    a, b = read_aligned(path_a), read_aligned(path_b)
    residual, valid = signed_difference(a['image'], b['image'], a['valid'], b['valid'], a['wcs'], b['wcs'], a['header'].get('BUNIT'), b['header'].get('BUNIT'))
    if valid.mean() < .5:
        raise ValueError('Historical residual has less than 50 percent common science coverage.')
    limit = max(float(np.percentile(np.abs(residual[valid]), 99.5)), 1e-9)
    display = {'vmin': -limit, 'vmax': limit, 'stretch': 'linear', 'colormap': 'spx_residual',
               'colors': RESIDUAL_COLORS, 'zeroColor': RESIDUAL_COLORS[1], 'invalidColor': '#683a68', 'common': True}
    prefix = 'epsilon_indi_b/differences/historical'
    assets = {'fits': prefix+'.fits', 'png': prefix+'.png', 'mask': prefix+'.mask.json'}
    (root/assets['fits']).parent.mkdir(parents=True, exist_ok=True)
    header = a['wcs'].to_header(relax=True);header['BUNIT'] = a['header']['BUNIT'];header['EPOCH_A'] = record_a['midpoint_utc'];header['EPOCH_B'] = record_b['midpoint_utc']
    header['DATAMIN'] = -limit;header['DATAMAX'] = limit;header['HISTORY'] = 'D = B - A from aligned scientific IMAGE, conservative COVERAGE intersection; no correction; not significance.'
    fits.PrimaryHDU(residual.astype(np.float32), header).writeto(root/assets['fits'], overwrite=True)
    cmap = LinearSegmentedColormap.from_list('spx_residual', RESIDUAL_COLORS).with_extremes(bad='#683a68')
    Image.fromarray(np.flipud(cmap(Normalize(-limit, limit)(np.ma.masked_invalid(residual)), bytes=True))).save(root/assets['png'])
    write_manifest(root/assets['mask'], {'encoding': 'packed-bits-base64', 'bitOrder': 'little', 'shape': list(valid.shape),
        'origin': 'FITS bottom-left; row-major y,x', 'valid': _pack(valid)})
    private.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(residual, header).writeto(private/'difference.fits', overwrite=True)
    shutil.copyfile(root/assets['png'], private/'difference.png')
    fits.PrimaryHDU(valid.astype(np.uint8), a['wcs'].to_header()).writeto(private/'difference_mask.fits', overwrite=True)
    yy, xx = np.indices(valid.shape);background = valid & (np.hypot(xx-(valid.shape[1]-1)/2, yy-(valid.shape[0]-1)/2) > 10)
    result = {'id': 'historical', 'aId': record_a['observation_id'], 'bId': record_b['observation_id'],
        'aTimestampUtc': record_a['midpoint_utc'], 'bTimestampUtc': record_b['midpoint_utc'], 'assets': assets,
        'display': display, 'units': a['header']['BUNIT'], 'classification': 'exploratory',
        'validFraction': float(valid.mean()), 'validPixels': int(valid.sum()), 'totalPixels': valid.size,
        'spectralScreen': spectral, 'method': 'D = aligned scientific IMAGE B minus A; finite conservative science COVERAGE intersection.',
        'normalization': 'None. No gain, background, flux or PSF correction.', 'uncertainty': None,
        'precision': 'Float64 calculation/private FITS; float32 lightweight native web FITS.',
        'backgroundDiagnostic': {'region': 'Common finite science pixels outside radius ten fixed-grid pixels of field center; descriptive field median, not a fitted background model.',
            'pixels': int(background.sum()), 'medianA': float(np.median(a['image'][background])), 'medianB': float(np.median(b['image'][background])),
            'medianDifference': float(np.median(residual[background])), 'correctionApplied': False},
        'residualDiagnostics': {'median': float(np.median(residual[valid])), 'mad': float(np.median(np.abs(residual[valid]-np.median(residual[valid])))),
            'positiveFraction': float(np.mean(residual[valid] > 0)), 'negativeFraction': float(np.mean(residual[valid] < 0)),
            'minimum': float(residual[valid].min()), 'maximum': float(residual[valid].max())},
        'warnings': RESIDUAL_WARNINGS}
    write_manifest(private/'difference.json', result)
    return result


def prepare(project):
    project = Path(project).resolve();output = project/'outputs/spx004b';output.mkdir(parents=True, exist_ok=True)
    catalogue = load_json(project/'frontend/public/data/catalog.json')
    target = deepcopy(next(t for t in catalogue['targets'] if t['id'] == 'epsilon_indi_b'))
    original_frames = {frame['id']: deepcopy(frame) for frame in target['sequence']['frames'] if frame['id'] in HISTORICAL_PAIR}
    if set(original_frames) != set(HISTORICAL_PAIR):
        raise ValueError('The unchanged historical pair must be present before extending Epsilon.')
    source_dir = project/'outputs/spx002b/epsilon_indi_b'
    manifest = load_json(source_dir/'observations.json')
    records = sorted([r for r in manifest['observations'] if int(r['detector']) == 6], key=lambda r:r['midpoint_mjd'])
    if len(records) != 6 or len({r['observation_id'] for r in records}) != 6:
        raise ValueError('Expected exactly the six existing distinct D6 observations.')
    aligned = {r['observation_id']: read_aligned(source_dir/r['aligned_asset']) for r in records}
    reference = aligned[HISTORICAL_PAIR[0]]
    for item in aligned.values():
        if item['image'].shape != reference['image'].shape or dict(item['wcs'].to_header()) != dict(reference['wcs'].to_header()):
            raise ValueError('Extended observations must share the unchanged historical fixed WCS.')
    low, high = display_limits(np.concatenate([item['display'][np.isfinite(item['display'])] for item in aligned.values()]))
    inspection_cuts = {'vmin': low, 'vmax': high, 'stretch': 'asinh', 'common': True, 'pngAsinhParameter': .1,
                       'units': reference['header']['BUNIT'], 'warning': 'Common visual scale across all D6 observations; the full set is NOT a homogeneous temporal comparison.'}
    root = output/'web_data';root.mkdir(exist_ok=True)
    frames = []
    visits = assign_visit_ids(records, 'd6')
    for record in records:
        source_path = source_dir/record['aligned_asset']
        record['_aligned_relative'] = source_path.relative_to(project).as_posix()
        record['_aligned_sha256'] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        frame = original_frames.get(record['observation_id']) or _export_frame(root, target, record, aligned[record['observation_id']], inspection_cuts)
        frame['visitId'] = visits[frame['id']]
        frame['inspectionOnly'] = frame['id'] not in HISTORICAL_PAIR
        frame['comparisonGroupIds'] = ['d6-historical'] if frame['id'] in HISTORICAL_PAIR else []
        frames.append(frame)
    groups = [
        {'id': 'd6-historical', 'label': 'Historical D6 pair · 4.42–4.43 μm', 'frameIds': list(HISTORICAL_PAIR),
         'comparison': True, 'display': deepcopy(target['sequence']['display']),
         'warnings': ['Only this historical pair has the retained motion measurement; response/PSF systematics remain unvalidated.']},
        {'id': 'd6-all-inspection', 'label': 'All six D6 observations · visual inspection only', 'frameIds': [frame['id'] for frame in frames],
         'comparison': False, 'display': inspection_cuts,
         'warnings': ['Different local wavelengths and four visit groups; not six homogeneous independent temporal epochs. Blink and scientific Difference are restricted to the compatible historical group.']},
    ]
    by_id = {r['observation_id']:r for r in records}
    difference = export_difference(root, output/'epsilon_indi_b', source_dir/by_id[HISTORICAL_PAIR[0]]['aligned_asset'],
        source_dir/by_id[HISTORICAL_PAIR[1]]['aligned_asset'], by_id[HISTORICAL_PAIR[0]], by_id[HISTORICAL_PAIR[1]])
    target['sequence'].update(frames=frames, groups=groups, defaultGroupId='d6-historical',
        historicalPair={'aId': HISTORICAL_PAIR[0], 'bId': HISTORICAL_PAIR[1]}, differences=[difference],
        availableObservationCount=6, independentVisitCount=len(set(visits.values())))
    write_manifest(output/'extension.json', {'version':1, 'targets':[target], 'notes':['Only Epsilon D6 is extended. M101 remains its existing registered pair; Barnard and RW Aur remain unchanged.']})
    # Keep a self-contained local display bundle, copying only old display assets
    # into the new phase directory, never raw/unaltered scientific observations.
    for frame in original_frames.values():
        for asset in frame['assets'].values():
            destination = root/portable_asset(asset);destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project/'frontend/public/data'/asset, destination)
    write_manifest(root/'catalog.json', {'version':1, 'coordinateFrame':'ICRS', 'targets':[target]})
    actual_inventory = inventory(project);write_manifest(output/'inventory.json', actual_inventory)
    write_manifest(output/'epsilon_indi_b/sequence_manifest.json', dict(target, assetBase='../web_data/'))
    return {'inventory':actual_inventory, 'target':target}


def include_change_targets(project, output, catalog):
    """Optional prepared-extension hook, preserving historical assets and metadata."""
    project, output = Path(project), Path(output)
    manifest = project/'outputs/spx004b/extension.json'
    if not manifest.exists():
        return catalog
    extension = load_json(manifest)
    for target in extension['targets']:
        if target['id'] != 'epsilon_indi_b':
            raise ValueError('Unexpected extended target.')
        assets = {path for frame in target['sequence']['frames'] for path in frame['assets'].values()}
        assets.update(path for difference in target['sequence']['differences'] for path in difference['assets'].values())
        for asset in assets:
            relative = portable_asset(asset)
            source = project/'outputs/spx004b/web_data'/relative;destination = output/relative
            if source.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists() or hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
                    shutil.copyfile(source, destination)
            elif not destination.exists():
                raise FileNotFoundError(f'Historical web asset is absent: {relative}')
        catalog['targets'] = [deepcopy(target) if current['id'] == target['id'] else current for current in catalog['targets']]
    write_manifest(output/'catalog.json', catalog)
    return catalog
