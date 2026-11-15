"""Audit scientific inputs, public data and historical evidence for SPX-007A."""
from pathlib import Path
import hashlib
import json

PROJECT=Path(__file__).resolve().parents[1]

def main():
    output=PROJECT/'outputs/spx007a'
    baseline=json.loads((output/'baseline_sha256.json').read_text(encoding='utf-8'))
    changed=[];missing=[]
    for name,value in baseline.items():
        path=PROJECT/name
        if not path.is_file():missing.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=value:changed.append(name)
    report={'protectedFiles':len(baseline),'unchangedFiles':len(baseline)-len(changed)-len(missing),
        'changed':changed,'missing':missing,'originalFits':len(list((PROJECT/'data/raw').rglob('*.fits'))),
        'publicDataFiles':len([p for p in (PROJECT/'frontend/public/data').rglob('*') if p.is_file()]),
        'passed':not changed and not missing}
    (output/'preservation_check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
