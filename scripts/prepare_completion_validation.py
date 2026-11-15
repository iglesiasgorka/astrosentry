"""Independent native FITS/WCS samples for the new SPX-006 prepared fields."""
from pathlib import Path
import json
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

PROJECT=Path(__file__).resolve().parents[1]

def main():
    catalog=json.loads((PROJECT/'frontend/public/data/catalog.json').read_text(encoding='utf-8'))
    dynamic=json.loads((PROJECT/'outputs/spx006/dynamic_browser.json').read_text(encoding='utf-8'))['target']
    targets=[t for t in catalog['targets'] if t['id'] in ['r_dra','wise0855']]+[dynamic]
    result={}
    for target in targets:
        frames=[]
        for frame in target['sequence']['frames']:
            asset=frame['assets']['fits']
            root=PROJECT/('outputs/spx006b/assets' if asset.startswith('dynamic/') else 'frontend/public/data')
            with fits.open(root/asset) as hdus:
                data=hdus[0].data;wcs=WCS(hdus[0].header);points=[]
                step,edge=(2,3) if min(data.shape)<40 else (4,8)
                for y in range(edge,data.shape[0]-edge,step):
                    for x in range(edge,data.shape[1]-edge,step):
                        if not np.isfinite(data[y,x]):continue
                        sky=wcs.pixel_to_world(x,y).icrs
                        mirror=wcs.pixel_to_world(x,data.shape[0]-1-y).icrs
                        points.append({'pixel':[x,y],'sky':[float(sky.ra.deg),float(sky.dec.deg)],'value':float(data[y,x]),'mirrorSky':[float(mirror.ra.deg),float(mirror.dec.deg)]})
                assert len(points)>=50,(target['id'],frame['id'],len(points))
                frames.append(points)
        result[target['id']]=frames
    output=PROJECT/'outputs/spx006/completion_registration_samples.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print({k:[len(f) for f in v] for k,v in result.items()})

if __name__=='__main__':main()
