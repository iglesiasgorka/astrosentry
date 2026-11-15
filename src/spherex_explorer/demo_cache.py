"""Operator-only import of hash-verified real SPX-007B inputs; never uses the network."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile

from .metadata_cache import utc_now
from .production_api import Settings,atomic_json
from .production_store import InstanceLock


def import_bundle(bundle,state):
    # Reuse state-path protection without reading or requiring the HTTP credential.
    state=Settings(Path(state),'offline-import-validation-not-an-http-credential').state
    state.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=InstanceLock(state/'instance.lock')
    try:
        from astropy.io import fits
        from .observation import Observation
        from .dynamic import parameters,search_key
        with ZipFile(bundle) as archive:
            infos=archive.infolist()
            if len(infos)>6 or len({i.filename for i in infos})!=len(infos) or sum(i.file_size for i in infos)>160*1024**2:
                raise ValueError('Unexpected validation archive size or duplicate entries.')
            for info in infos:
                if info.file_size>32*1024**2 or (info.filename not in {'manifest.json','search.json'} and not re.fullmatch(r'raw/[A-Za-z0-9_.-]+\.fits',info.filename)):
                    raise ValueError('Only bounded metadata and original FITS inputs are accepted.')
            manifest=json.loads(archive.read('manifest.json'))
            expected=manifest['files']
            if set(archive.namelist())!={'manifest.json',*expected}:raise ValueError('Validation bundle contents disagree with its manifest.')
            for name,digest in expected.items():
                if hashlib.sha256(archive.read(name)).hexdigest()!=digest:raise ValueError('Validation input checksum mismatch.')
            metadata=json.loads(archive.read('search.json'));p=parameters(metadata['parameters'])
            identifier=hashlib.sha256((search_key(p)+':sia2').encode()).hexdigest()[:20]
            if metadata['id']!=identifier:raise ValueError('Search identity does not match its parameters.')
            workspace=state/'workspace';raw=workspace/'raw';raw.mkdir(parents=True,exist_ok=True)
            imported=[]
            for name in expected:
                if name=='search.json':continue
                matching=[r for r in metadata['records'] if name.endswith('_'+hashlib.sha256(r['url'].encode()).hexdigest()[:16]+'.fits')]
                if len(matching)!=1:raise ValueError('FITS does not match an exact original cutout request.')
                destination=raw/Path(name).name;body=archive.read(name)
                if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest()!=expected[name]:raise ValueError('Refusing to replace a different existing FITS.')
                temporary=destination.with_suffix('.import.part');temporary.write_bytes(body)
                try:
                    with fits.open(temporary) as hdus:
                        hdus.verify('exception')
                        if not {'PRIMARY','IMAGE','FLAGS','VARIANCE','ZODI','EPSF','WCS-WAVE'}.issubset({h.name for h in hdus}):raise ValueError('Original scientific HDUs are missing.')
                    obs=Observation.read(temporary,matching[0]['release'])
                    if obs.observation_id!=matching[0]['observation_id'] or int(obs.header['DETECTOR'])!=matching[0]['detector']:raise ValueError('FITS identity or detector mismatch.')
                    temporary.replace(destination)
                finally:temporary.unlink(missing_ok=True)
                imported.append(destination.name)
            if len(imported)<2:raise ValueError('At least two original FITS are required.')
            metadata['cacheImport']={'origin':'SPX-007B original cutouts','bundleSha256':hashlib.sha256(Path(bundle).read_bytes()).hexdigest(),
                'sourceSearchSha256':expected['search.json'],'importedAtUtc':utc_now(),'newAcquisitions':0}
            atomic_json(workspace/'searches'/f'{identifier}.json',metadata)
            atomic_json(workspace/'demo_example.json',{'searchId':identifier,'parameters':metadata['parameters'],
                'label':'Real SPX-007B cached field','provenance':metadata['cacheImport']})
            return {'searchId':identifier,'importedFiles':imported,'newAcquisitions':0,'provenance':metadata['cacheImport']}
    finally:lock.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--state',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(import_bundle(args.bundle,args.state),indent=2))


if __name__=='__main__':main()
