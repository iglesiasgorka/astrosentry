"""Independent epoch and signed-residual samples for SPX-004B browser QA."""
from pathlib import Path
import json
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

if __name__=='__main__':
    project=Path(__file__).resolve().parents[1];assets=project/'frontend/public/data'
    catalog=json.loads((assets/'catalog.json').read_text(encoding='utf-8'));samples={};residuals={}
    def points(path,step=4,strict=False,limit=None):
        result=[]
        with fits.open(assets/path) as hdus:
            data=hdus[0].data;wcs=WCS(hdus[0].header)
            for y in range(8,data.shape[0]-8,step):
                for x in range(8,data.shape[1]-8,step):
                    if not np.isfinite(data[y,x]):continue
                    if strict and (not np.isfinite(data[y-1:y+2,x-1:x+2]).all() or abs(data[y,x])>.92*limit):continue
                    sky=wcs.pixel_to_world(x,y).icrs
                    result.append({'pixel':[x,y],'sky':[float(sky.ra.deg),float(sky.dec.deg)],'value':float(data[y,x])})
        return result
    for target in catalog['targets']:
        samples[target['id']]=[points(frame['assets']['fits']) for frame in target['sequence']['frames']]
        for difference in target['sequence'].get('differences',[]):
            residuals[f"{target['id']}:{difference['id']}"]=points(difference['assets']['fits'],3,True,difference['display']['vmax'])
    output=project/'outputs/spx004b'
    (output/'registration_samples.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
    (output/'residual_samples.json').write_text(json.dumps(residuals,indent=2),encoding='utf-8')
    print('Epoch samples:',{key:[len(frame) for frame in frames] for key,frames in samples.items()})
    print('Residual samples:',{key:len(value) for key,value in residuals.items()})
