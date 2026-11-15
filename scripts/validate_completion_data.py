"""Validate local delivery assets and preservation without queries or acquisition."""
from pathlib import Path
import hashlib
import json
import subprocess
import base64
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image
import numpy as np

PROJECT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    root=PROJECT/'outputs/spx006';baseline=json.loads((root/'baseline_sha256.json').read_text())
    intentional='frontend/public/data/catalog.json'
    changed=[name for name,old in baseline.items() if not (PROJECT/name).is_file() or digest(PROJECT/name)!=old]
    preserved=[name for name in baseline if name not in changed]
    original=json.loads(subprocess.check_output(['git','show','HEAD:frontend/public/data/catalog.json'],cwd=PROJECT))
    catalog=json.loads((PROJECT/intentional).read_text(encoding='utf-8'))
    retained={t['id']:next(n for n in catalog['targets'] if n['id']==t['id'])==t for t in original['targets']}
    assets=PROJECT/'frontend/public/data';validation={}
    for target in catalog['targets']:
        frames=target['sequence']['frames'];dates=[f['observation']['timestampUtc'] for f in frames]
        assert dates==sorted(dates)
        if target['id'] not in {'wise0855','r_dra'}:continue
        grids=[];cuts=[]
        for frame in frames:
            for asset in frame['assets'].values():
                p=Path(asset);assert not p.is_absolute() and '..' not in p.parts and '\\' not in asset
                assert (assets/p).is_file(),asset
            with fits.open(assets/frame['assets']['fits']) as hdus:
                hdus.verify('exception');shape=hdus[0].data.shape;h=hdus[0].header
                # Astropy retains epoch ancillary cards in WCS.to_header; epochs must differ.
                grids.append({k:v for k,v in dict(WCS(h).to_header()).items() if k not in {'DATE-AVG','MJD-AVG'}});cuts.append([h['DATAMIN'],h['DATAMAX']])
                assert np.isfinite(hdus[0].data).any()
            mask=json.loads((assets/frame['assets']['masks']).read_text())
            assert mask['shape']==list(shape)
            for name in ['displayValid','scienceValid']:
                bits=np.unpackbits(np.frombuffer(base64.b64decode(mask[name]),np.uint8),bitorder='little')[:np.prod(shape)]
                assert len(bits)==np.prod(shape)
            with Image.open(assets/frame['assets']['png']) as image:assert image.size==shape[::-1]
            assert frame['measuredPosition'] is None
        assert all(g==grids[0] for g in grids)
        assert all(np.allclose(c,cuts[0],rtol=0,atol=1e-12) for c in cuts)
        validation[target['id']]={'frames':len(frames),'commonWcs':True,'commonCuts':cuts[0],'dimensions':shape[::-1],'masksAndPngGrid':True,'measuredPositionsNull':True}
    originals=list((PROJECT/'data/raw').rglob('*.fits'))
    for path in originals:
        with fits.open(path) as hdus:hdus.verify('exception');assert 'IMAGE' in hdus
    ledger=json.loads((root/'acquisition_ledger.json').read_text())
    missing=[n for n in changed if not (PROJECT/n).exists()]
    unexpected_modified=[n for n in changed if n!=intentional and n not in missing]
    science_changed=[n for n in changed if n!=intentional and not n.startswith('outputs/spx005/browser-tests/')]
    prior=json.loads((PROJECT/'outputs/spx005/prior_artifacts_sha256.json').read_text())
    historical_changed=[n for n,h in prior.items() if not (PROJECT/n).is_file() or digest(PROJECT/n)!=h]
    science_passed=not science_changed and all(retained.values()) and len(originals)==52
    functional=all(retained.values()) and len(originals)==52 and sum(r['status']=='downloaded' for r in ledger['attempts'])==5
    passed=not missing and not unexpected_modified and science_passed
    report={'protectedFiles':len(baseline),'unchangedFiles':len(preserved),'intentionalModifiedFiles':[intentional],
        'missingHistoricalBrowserEvidence':missing,'unexpectedModifiedFiles':unexpected_modified,
        'scienceAndOriginalAssetsPreserved':science_passed,'historical604Unchanged':len(prior)-len(historical_changed),
        'historical604IntentionalChanges':historical_changed,'oldTargetEntriesEqual':retained,'originalFits':len(originals),
        'newFits':5,'acquisitionAttempts':len(ledger['attempts']),'catalogFields':len(catalog['targets']),
        'webObservations':sum(len(t['sequence']['frames']) for t in catalog['targets']),'newAssets':validation,
        'assetValidationPassed':functional,'completeHistoricalEvidencePreserved':not missing and not unexpected_modified,
        'incident':'An early SPX-006 Playwright invocation retained the previous SPX-005 output directory and cleaned eleven scenario videos plus .last-run.json. No identical backup was found. The separate spectral-tour and spectral-layout recording remain; missing evidence is not fabricated or replaced.',
        'passed':passed}
    (root/'delivery_preservation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
