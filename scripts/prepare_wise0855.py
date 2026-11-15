"""Bounded WISE 0855 D6 experiment using cached official availability and astrometry."""
from pathlib import Path
import json
import argparse
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from spherex_explorer.acquisition import AcquisitionBudget
from spherex_explorer.scientific_pipeline import run_target
from spherex_explorer.targets import predict_position
from spherex_explorer.fits_utils import write_manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquire',action='store_true',help='Allow bounded official downloads; default reuses cached FITS only.')
    args=parser.parse_args()
    project=Path(__file__).resolve().parents[1]
    availability=json.loads((project/'outputs/spx002/target_availability.json').read_text())
    target=next(t for t in json.loads((project/'config/target_astrometry.json').read_text())['targets'] if t['key']=='wise0855')
    challenge=SkyCoord('08h55m10.831s','-07d14m42.53s',frame='icrs')
    predicted=predict_position(target,Time('2025-11-01',scale='utc'))
    output=project/'outputs/spx006c/wise0855'
    write_manifest(output/'reference_check.json',{'challengeRaDeg':challenge.ra.deg,'challengeDecDeg':challenge.dec.deg,
        'reference':target,'predictedAt20251101':{'raDeg':predicted.ra.deg,'decDeg':predicted.dec.deg},
        'challengeToPredictedArcsec':challenge.separation(predicted).arcsec,
        'fieldWidthDeg':.15,'parallaxMas':target['parallax_mas'],
        'limitations':['Reference epoch and bibliography retained from previously resolved SIMBAD ICRS J2000 astrometry.',
            'Linear proper motion only; annual parallax, orbital/perspective effects and observer position are omitted.',
            'A known high proper motion does not establish a detected SPHEREx centroid or significance.']})
    budget=AcquisitionBudget(project)
    result=run_target(project,output,availability,target,max_downloads=8,total_download_budget=8,size_deg=.15,
        detector='SPHEREx-D6',local_only=not args.acquire,timeout=45,raw_directory=project/'data/raw/spx006/wise0855',
        download_function=lambda url,directory,timeout:budget.download(url,directory,purpose='wise0855',timeout=timeout))
    print(json.dumps({'downloaded':result['downloaded_count'],'classification':result['sequence_classification'],'sequence':result['sequence_ids'],'attempts':len(budget.snapshot()['attempts'])}),flush=True)
