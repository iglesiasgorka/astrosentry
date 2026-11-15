"""Create a source update and separately labeled real cached inputs; never acquire data."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

root=Path(__file__).resolve().parents[1];out=root/'outputs/spx007d';out.mkdir(parents=True,exist_ok=True)
source=root/'outputs/spx007b';search=source/'searches/f369d59a4aca8645a101.json'
files={'search.json':search,**{'raw/'+p.name:p for p in sorted((source/'raw').glob('*.fits'))}}
manifest={'source':'Existing real SPX-007B inputs; not a live IRSA acquisition',
          'files':{n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()}}
bundle=out/'spx007b-validation-inputs.zip'
if bundle.exists():
    with ZipFile(bundle) as archive:
        assert json.loads(archive.read('manifest.json'))==manifest,'Do not replace previously validated scientific input bundles.'
        assert all(hashlib.sha256(archive.read(n)).hexdigest()==h for n,h in manifest['files'].items())
else:
    with ZipFile(bundle,'w',ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(manifest,indent=2))
        for name,path in files.items():archive.write(path,name)
paths=list((root/'src/spherex_explorer').glob('*.py'))+list((root/'deploy/raspberry-pi').glob('*'))
paths += [root/p for p in ['pyproject.toml','PUBLIC_DEMO.md','tests/conftest.py','tests/test_production_api.py','tests/test_public_demo.py','tests/test_irsa_resilience.py']]
with ZipFile(out/'spherex-backend-update.zip','w',ZIP_DEFLATED) as archive:
    for path in paths:archive.write(path,path.relative_to(root).as_posix())
frontend=list((root/'frontend/src').rglob('*'))+[root/'frontend'/n for n in ['package.json','package-lock.json','vite.config.ts','tsconfig.json']]
with ZipFile(out/'frontend-source-update.zip','w',ZIP_DEFLATED) as archive:
    for path in frontend:
        if path.is_file():archive.write(path,path.relative_to(root/'frontend').as_posix())
report={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.glob('*.zip')}
(out/'packages.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
