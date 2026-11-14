"""Create independent browser registration samples without rewriting past outputs."""
from pathlib import Path
import json
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

if __name__=='__main__':
    project=Path(__file__).resolve().parents[1];assets=project/'frontend/public/data'
    catalog=json.loads((assets/'catalog.json').read_text());samples={}
    for target in catalog['targets']:
        samples[target['id']]=[]
        for frame in target['sequence']['frames']:
            points=[]
            with fits.open(assets/frame['assets']['fits']) as hdus:
                image=hdus[0].data;wcs=WCS(hdus[0].header)
                for y in range(8,image.shape[0]-8,4):
                    for x in range(8,image.shape[1]-8,4):
                        if np.isfinite(image[y,x]):
                            sky=wcs.pixel_to_world(x,y).icrs
                            points.append({'pixel':[x,y],'sky':[float(sky.ra.deg),float(sky.dec.deg)],'value':float(image[y,x])})
            samples[target['id']].append(points)
    output=project/'outputs/spx004a/registration_samples.json'
    output.write_text(json.dumps(samples,indent=2))
    print({key:[len(frame) for frame in frames] for key,frames in samples.items()})
