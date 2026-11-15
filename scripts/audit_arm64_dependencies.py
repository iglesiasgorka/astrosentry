"""Read PyPI release metadata for CPython 3.13/Linux ARM64; never install packages."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

from packaging.specifiers import SpecifierSet
from packaging.tags import cpython_tags, compatible_tags
from packaging.utils import parse_wheel_filename
import requests

PROJECT=Path(__file__).resolve().parents[1]
PLATFORMS=['manylinux2014_aarch64']+[f'manylinux_2_{n}_aarch64' for n in range(17,42)]+['linux_aarch64']
TAGS=set(cpython_tags((3,13),platforms=PLATFORMS))|set(compatible_tags((3,13),interpreter='cp313',platforms=PLATFORMS))


def inspect(requirement):
    name,_,version=requirement.partition('==')
    url=f'https://pypi.org/pypi/{name}/{version+"/" if version else ""}json'
    response=requests.get(url,timeout=30);response.raise_for_status();data=response.json()
    files=[]
    for entry in data['urls']:
        if entry['filename'].endswith('.whl') and not entry.get('yanked'):
            if TAGS & parse_wheel_filename(entry['filename'])[3]:files.append(entry['filename'])
    return {'package':name,'version':data['info']['version'],'requiresPython':data['info']['requires_python'],
        'python313':SpecifierSet(data['info']['requires_python'] or '').contains('3.13.5'),
        'wheels':files,'source':url,'requiresDist':data['info']['requires_dist']}


if __name__=='__main__':
    requirements=[r for r in (PROJECT/'requirements-lock.txt').read_text().splitlines() if r and not r.startswith('pywin32-ctypes')]
    requirements+=['waitress==3.0.2','SecretStorage','jeepney','cryptography','cffi','pycparser']
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(inspect,requirements))
    destination=PROJECT/'outputs/spx007c_pi/arm64_all_dependencies.json'
    destination.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps({'checked':len(results),'withoutWheel':[r['package'] for r in results if not r['wheels']],
                      'incompatiblePython':[r['package'] for r in results if not r['python313']]}))
