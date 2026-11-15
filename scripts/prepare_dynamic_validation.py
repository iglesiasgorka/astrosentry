"""Independent native FITS samples for the new dynamic field; no network."""
from pathlib import Path
import json
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from spherex_explorer.fits_utils import write_manifest

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/spx007b'
if __name__=='__main__':
    target=json.loads((OUT/'new_region_target.json').read_text());result={}
    for frame in target['sequence']['frames']:
        with fits.open(OUT/'assets'/frame['assets']['fits']) as hdus:
            data=hdus[0].data;wcs=WCS(hdus[0].header)
            ys,xs=np.where(np.isfinite(data));indices=np.linspace(0,len(xs)-1,min(len(xs),350)).round().astype(int)
            samples=[]
            for i in indices:
                x,y=int(xs[i]),int(ys[i]);c=wcs.pixel_to_world(x,y)
                samples.append({'pixel':[x,y],'sky':[float(c.ra.deg),float(c.dec.deg)],'value':float(data[y,x])})
            result[frame['id']]=samples
    write_manifest(OUT/'live_samples.json',result)
    print({key:len(v) for key,v in result.items()})
