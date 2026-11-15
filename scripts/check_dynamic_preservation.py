"""Read-only audit of all SPX-007B protected inputs, historical outputs and reports."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/spx007b'

if __name__=='__main__':
    baseline=json.loads((OUT/'baseline_sha256.json').read_text());missing=[];changed=[]
    for name,expected in baseline.items():
        p=ROOT/name
        if not p.is_file():missing.append(name)
        elif hashlib.sha256(p.read_bytes()).hexdigest()!=expected:changed.append(name)
    catalog=json.loads((ROOT/'frontend/public/data/catalog.json').read_text())
    ledger=json.loads((OUT/'acquisition_ledger.json').read_text())
    start=(OUT/'baseline_sha256.json').stat().st_mtime
    outside=[p.relative_to(ROOT).as_posix() for p in (ROOT/'outputs').rglob('*')
             if p.is_file() and not p.is_relative_to(OUT) and p.stat().st_mtime>start]
    report={'protectedFiles':len(baseline),'unchanged':len(baseline)-len(changed)-len(missing),
        'changed':changed,'missing':missing,'newEvidenceOutsidePhase':outside,
        'originalFits':len(list((ROOT/'data/raw').rglob('*.fits'))),
        'staticFields':len(catalog['targets']),'staticObservations':sum(len(t['sequence']['frames']) for t in catalog['targets']),
        'newValidRawFits':len(list((OUT/'raw').glob('*.fits'))),'acquisitionAttempts':len(ledger['attempts']),
        'indexEmpty':subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0}
    report['passed']=not missing and not changed and not outside and report['originalFits']==52 and report['staticObservations']==23 and len(ledger['attempts'])<=12
    (OUT/'preservation_check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['passed'] else 1)
