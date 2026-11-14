"""Check actual browser color/sign/registration against independent residual FITS.

This verifies a displayed signed surface-brightness pattern, not significance,
photometric calibration, PSF matching or a new motion/variability measurement.
"""
import json
import argparse
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.stats import spearmanr
from astropy.io import fits

PROJECT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=PROJECT/'outputs/spx004b')
    directory=parser.parse_args().directory;report={}
    for suffix in ['', '_panned','_resized']:
        name='difference'+suffix
        metadata=json.loads((directory/(name+'_screen.json')).read_text(encoding='utf-8'))
        screenshot=np.asarray(Image.open(directory/(name+'.png')).convert('RGB'),dtype=float)
        with fits.open(PROJECT/'frontend/public/data'/metadata['difference']['assets']['fits']) as hdus:
            data=hdus[0].data.copy()
        expected=[];observed=[];inverted=[];paired=[];sign_correct=[]
        for point in metadata['samples']:
            if point['screen'] is None:continue
            x,y=(int(round(v)) for v in point['screen'])
            if not (2<=x<screenshot.shape[1]-2 and 2<=y<screenshot.shape[0]-2):continue
            rgb=screenshot[y-1:y+2,x-1:x+2].mean(axis=(0,1))
            color=float(rgb[0]-rgb[2]) # Custom blue/white/red palette, increasing D.
            expected.append(point['value']);observed.append(color)
            if abs(point['value'])>.015:sign_correct.append(np.sign(color)==np.sign(point['value']))
            px,py=point['pixel'];wrong=data[data.shape[0]-1-py,px]
            if np.isfinite(wrong):inverted.append(float(wrong));paired.append(color)
        correlation=float(spearmanr(expected,observed).statistic)
        wrong=float(spearmanr(inverted,paired).statistic)
        signs=float(np.mean(sign_correct))
        passed=len(expected)>=50 and correlation>.9 and correlation-wrong>.1 and signs>.9
        report[name]={'samples':len(expected),'signedColorRankCorrelation':correlation,'verticalFlipControlCorrelation':wrong,'nonzeroSignAgreement':signs,'passed':passed}
        print(name,report[name])
    (directory/'rendered_difference_check.json').write_text(json.dumps({'captures':report,'passed':all(r['passed'] for r in report.values())},indent=2),encoding='utf-8')
    return 0 if all(r['passed'] for r in report.values()) else 1


if __name__=='__main__':raise SystemExit(main())
