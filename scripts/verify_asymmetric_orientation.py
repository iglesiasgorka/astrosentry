"""Check signed spatial asymmetries when radial symmetry weakens rank flip control.

This supplements, never overwrites, the retained generic orientation result.
A monotonic display must preserve the sign of f(x,y)-f(x,height-1-y).
It checks image orientation/content, not physical variability or significance.
"""
from pathlib import Path
import json
import argparse
import numpy as np
from astropy.io import fits
from PIL import Image
from scipy.stats import spearmanr

PROJECT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=PROJECT/'outputs/spx006/completion-registration')
    directory=parser.parse_args().directory;report={}
    for path in sorted(directory.glob('r_dra*_screen.json')):
        metadata=json.loads(path.read_text(encoding='utf-8'));image=np.asarray(Image.open(path.with_name(path.stem.removesuffix('_screen')+'.png')).convert('RGB'),float)
        data=fits.getdata(PROJECT/'frontend/public/data'/metadata['frame']['assets']['fits'])
        expected=[];observed=[]
        def gray(point):
            if point is None:return None
            x,y=(int(round(v)) for v in point)
            if not (2<=x<image.shape[1]-2 and 2<=y<image.shape[0]-2):return None
            return float(image[y-1:y+2,x-1:x+2].mean())
        for sample in metadata['samples']:
            x,y=sample['pixel'];a=gray(sample['screen']);b=gray(sample.get('mirrorScreen'));wrong=data[data.shape[0]-1-y,x]
            if a is None or b is None or not np.isfinite(wrong):continue
            expected.append(sample['value']-float(wrong));observed.append(a-b)
        expected=np.asarray(expected);observed=np.asarray(observed)
        if not len(expected):raise ValueError('Capture the independent native-WCS mirror points first.')
        select=(np.abs(expected)>=np.percentile(np.abs(expected),40))&(np.abs(observed)>=2)
        e,o=expected[select],observed[select]
        correlation=float(spearmanr(e,o).statistic);sign=float(np.mean(np.sign(e)==np.sign(o)))
        passed=len(e)>=50 and correlation>.90 and sign>.95
        report[path.stem]={'asymmetricPairs':len(e),'signedDifferenceRankCorrelation':correlation,'signAgreement':sign,'invertedSignAgreement':1-sign,'passed':passed}
        print(path.stem,report[path.stem])
    passed=len(report)==7 and all(r['passed'] for r in report.values())
    (directory/'asymmetric_orientation_check.json').write_text(json.dumps({'method':'Native WCS mirrored-pixel signed differences; pairs with >=2 gray levels and upper 60% native asymmetry; no source-fit or motion inference.','captures':report,'passed':passed},indent=2),encoding='utf-8')
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
