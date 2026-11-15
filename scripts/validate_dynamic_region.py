"""Prove the tutorial field is new, search real SIA2, optionally prepare <=4 frames."""
import argparse
from pathlib import Path
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from spherex_explorer.dynamic import search, parameters, prepare_region
from spherex_explorer.fits_utils import write_manifest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/spx007b'

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true',help='Acquire up to four small cutouts under the phase ledger.')
    args=parser.parse_args()
    p=parameters({'ra':304.693508808,'dec':42.4436872991,'size':.05,'detector':2})
    point=SkyCoord(p.ra*u.deg,p.dec*u.deg);checks=[]
    for path in sorted((ROOT/'data/raw').rglob('*.fits')):
        with fits.open(path) as hdus:
            wcs=WCS(hdus['IMAGE'].header);h,w=hdus['IMAGE'].data.shape
            x,y=wcs.world_to_pixel(point)
            center=wcs.pixel_to_world((w-1)/2,(h-1)/2)
            checks.append({'path':path.relative_to(ROOT).as_posix(),
                'containsRequestedCenter':bool(np.isfinite(x+y) and -.5<=x<w-.5 and -.5<=y<h-.5),
                'distanceFromCutoutCenterDeg':float(point.separation(center).deg)})
    assert len(checks)==52 and not any(c['containsRequestedCenter'] for c in checks)
    assert min(c['distanceFromCutoutCenterDeg'] for c in checks)>5
    write_manifest(OUT/'new_region_coverage.json',{'parameters':{'ra':p.ra,'dec':p.dec,'size':p.size,'detector':2},
        'existingOriginalFits':len(checks),'outsideAllExistingCutouts':True,'checks':checks,
        'method':'Original IMAGE WCS inverse at requested center plus >5 degree separation from every small cutout center. No original covers or intersects this 0.05-degree region.'})
    result=search(ROOT,p)
    write_manifest(OUT/'new_region_search.json',result)
    print('New region:',result['count'],'D2 observations;',result['visitCount'],'visits',flush=True)
    if args.prepare:
        target=prepare_region(ROOT,result,4)
        write_manifest(OUT/'new_region_target.json',target)
        print('Prepared:',target['id'],len(target['sequence']['frames']),'frames',flush=True)
