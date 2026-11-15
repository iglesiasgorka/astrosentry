"""Package source for an owner-operated private Pi test, without data or secrets."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root=Path(__file__).resolve().parents[1]
destination=root/'outputs/spx007c_pi/spherex-backend-pi.zip'
destination.parent.mkdir(parents=True,exist_ok=True)
paths=sorted((root/'src/spherex_explorer').glob('*.py'))
paths+=sorted((root/'deploy/raspberry-pi').glob('*'))
paths += [root/name for name in ['pyproject.toml','RASPBERRY_PI.md','tests/conftest.py','tests/test_production_api.py']]
with ZipFile(destination,'w',compression=ZIP_DEFLATED) as archive:
    for path in paths:
        if path.is_file():archive.write(path,path.relative_to(root).as_posix())
result={'path':destination.name,'bytes':destination.stat().st_size,'files':len(paths),
        'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
        'contains':'Python source, deployment templates, installation guide and offline production-control tests only.'}
destination.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
