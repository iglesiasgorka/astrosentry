"""Bounded official IRSA SIA2 metadata, normalized to the existing cutout model."""
from io import BytesIO
import math
import time
from urllib.parse import urlsplit

from astropy.io.votable import parse
from astropy.table import Table
from astropy import units as u
from astropy.coordinates import SkyCoord
import numpy as np
import requests

from .alignment import common_grid
from .data_access import parse_artifact_url, prepare_observations

ENDPOINT = 'https://irsa.ipac.caltech.edu/SIA'
COLLECTIONS = ('spherex_dr1', 'spherex_qr3', 'spherex_dr1_deep', 'spherex_qr3_deep')
REQUIRED = {'access_url', 'obs_id', 'obs_collection', 'energy_bandpassname', 't_min', 't_max', 's_region'}


class SiaQueryError(RuntimeError):
    def __init__(self,status,attempts):
        self.status=status;self.attempts=attempts
        self.public_message=f'IRSA SIA2 returned HTTP {status} after {attempts} attempt(s); this is not a no-data result.'
        super().__init__(self.public_message)


def region_corners(p):
    grid, shape = common_grid(p.ra, p.dec, p.size, 6.2)
    return grid.pixel_to_world(np.array([-.5, shape[1]-.5, shape[1]-.5, -.5]),
                               np.array([-.5, -.5, shape[0]-.5, shape[0]-.5]))


def sia_parameters(p, maxrec=5000):
    center = SkyCoord(p.ra*u.deg, p.dec*u.deg)
    radius = float(np.max(center.separation(region_corners(p)).deg))
    return [('POS', f'CIRCLE {p.ra} {p.dec} {radius}'),
            *[('COLLECTION', value) for value in COLLECTIONS], ('MAXREC', str(maxrec))]


def polygon_contains(region, points, center):
    """Conservative tangent-plane polygon test; unsupported footprints stay null."""
    words = str(region).split()
    if words[:2] != ['POLYGON', 'ICRS'] or len(words) < 8 or len(words) % 2:
        return None
    try:
        vertices = np.asarray(words[2:], dtype=float).reshape(-1, 2)
        def project(ra, dec):
            a, b = np.deg2rad(ra-center[0]), np.deg2rad(dec)
            d = np.deg2rad(center[1])
            denominator = np.sin(d)*np.sin(b)+np.cos(d)*np.cos(b)*np.cos(a)
            if np.any(denominator <= 0):
                raise ValueError('Polygon crosses the projection horizon.')
            return np.cos(b)*np.sin(a)/denominator, (np.cos(d)*np.sin(b)-np.sin(d)*np.cos(b)*np.cos(a))/denominator
        vx, vy = project(vertices[:, 0], vertices[:, 1])
        x, y = project(points.ra.deg, points.dec.deg)
        inside = np.zeros(np.shape(x), dtype=bool)
        j = len(vx)-1
        for i in range(len(vx)):
            if vy[j] != vy[i]:
                inside ^= ((vy[i] > y) != (vy[j] > y)) & (x < (vx[j]-vx[i])*(y-vy[i])/(vy[j]-vy[i])+vx[i])
            j = i
        return bool(np.all(inside))
    except (ValueError, TypeError):
        return None


def parse_sia_response(body, p, maxrec=5000):
    votable = parse(BytesIO(body))
    infos = [info for r in votable.resources for info in r.infos]
    if not any(i.name == 'QUERY_STATUS' and i.value == 'OK' for i in infos):
        raise ValueError('SIA2 did not report a successful query.')
    if any(i.name == 'QUERY_STATUS' and i.value in {'ERROR', 'OVERFLOW'} for i in infos):
        raise ValueError('SIA2 reported an error or incomplete results; narrow the region.')
    table = votable.get_first_table().to_table(use_names_over_ids=True)
    if not REQUIRED.issubset(table.colnames):
        raise ValueError('SIA2 response lacks required official observation columns.')
    if len(table) >= maxrec:
        raise ValueError('SIA2 row limit reached; completeness is not established.')
    rows, provenance = [], {}
    corners = region_corners(p)
    for row in table:
        if str(row['energy_bandpassname']) != p.bandpass:
            continue
        url = str(row['access_url']); parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'irsa.ipac.caltech.edu'
                or parsed.query or parsed.fragment or not parsed.path.startswith('/ibe/data/spherex/')):
            raise ValueError('SIA2 access_url is not a trusted on-premises SPHEREx artifact.')
        identity = parse_artifact_url(url)
        if (identity['observation_id'] != str(row['obs_id'])
                or str(row['obs_collection']) not in COLLECTIONS
                or not str(row['obs_collection']).startswith('spherex_'+identity['release'])):
            raise ValueError('SIA2 observation identity/release disagrees with its artifact.')
        if any(np.ma.is_masked(row[n]) for n in ['t_min', 't_max']):
            raise ValueError('SIA2 observation time is missing.')
        lower, upper = float(row['t_min']), float(row['t_max'])
        if not math.isfinite(lower+upper) or upper < lower:
            raise ValueError('SIA2 observation time bounds are invalid.')
        # Match the documented direct-cutout syntax and the live validated URL.
        cutout = f'{url}?center={p.ra},{p.dec}&size={p.size}'
        rows.append((cutout, parsed.path.lstrip('/'), lower, p.bandpass))
        provenance[cutout] = {'service': 'IRSA SIA2', 'collection': str(row['obs_collection']),
            'access_url': url, 's_region': str(row['s_region']), 't_min': lower, 't_max': upper,
            'intersectsSearchCircle': True,
            'requestedGridCoveredByMetadata': polygon_contains(row['s_region'], corners, (p.ra, p.dec)),
            'coverageWarning': 'SIA2 intersection is not full coverage. Metadata polygon only; verify actual FITS WCS and valid masks.',
            'wavelengthStatus': 'Requires local FITS spectral WCS; detector-wide spectral bounds are not a local wavelength.'}
    normalized = Table(rows=rows, names=['uri', 'artifact_uri', 'time_bounds_lower', 'energy_bandpassname'])
    records = prepare_observations(normalized)
    for record in records:
        record.update(sia=provenance[record['url']], timestamp_source='SIA2 t_min (MJD UTC lower bound)')
    return records, {'rawRows': len(table), 'detectorRows': len(rows), 'deduplicatedRows': len(records),
                     'schema': table.colnames, 'queryStatus': 'OK', 'rowLimit': maxrec}


def query_sia_observations(p, timeout=40, evidence=None):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('SIA2 timeout must be positive and finite.')
    params = sia_parameters(p); began = time.monotonic();deadline=began+timeout
    statuses=[]
    for attempt in range(1,4):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('IRSA SIA2 exhausted its metadata deadline; this is not a no-data result.')
        per_attempt=min(6,remaining/(4-attempt))
        with requests.get(ENDPOINT, params=params, timeout=(min(2,per_attempt),per_attempt), stream=True, allow_redirects=False) as response:
            statuses.append(response.status_code)
            if response.status_code!=200:
                if response.status_code not in {502,503,504} or attempt==3:raise SiaQueryError(response.status_code,attempt)
            else:
                body=bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body)>8_000_000 or time.monotonic()>=deadline:raise ValueError('SIA2 response exceeds metadata byte/time limits.')
                records,report=parse_sia_response(bytes(body),p)
                report.update(service='IRSA SIA2',endpoint=ENDPOINT,parameters=params,bytes=len(body),
                    elapsedSeconds=time.monotonic()-began,status=200,attemptStatuses=statuses)
                break
        delay=.5*attempt
        if time.monotonic()+delay>=deadline:raise SiaQueryError(statuses[-1],attempt)
        time.sleep(delay)
    if evidence is not None:
        from .fits_utils import write_manifest
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence/'response.xml').write_bytes(body)
        write_manifest(evidence/'query.json', report)
    return records, report
