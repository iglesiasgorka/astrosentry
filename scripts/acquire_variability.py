"""Budgeted SPX-004A preparation from cached availability; no TAP query."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
from spherex_explorer.data_access import download_cutout, select_observations
from spherex_explorer.scientific_pipeline import run_target
from spherex_explorer.targets import epoch_groups
from spherex_explorer.fits_utils import write_manifest

PROJECT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',choices=['r_dra','rw_aur'],default='r_dra')
    parser.add_argument('--count',type=int,default=6)
    parser.add_argument('--detector',choices=['SPHEREx-D1','SPHEREx-D2'],default='SPHEREx-D2')
    args=parser.parse_args()
    if not 1<=args.count<=16:
        parser.error('Count must be between 1 and 16.')
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    base=PROJECT/'outputs/spx004a';base.mkdir(parents=True,exist_ok=True)
    ledger_path=base/'requests.json'
    ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'budget':16,'requests':[]}
    availability=json.loads((PROJECT/'outputs/spx002/target_availability.json').read_text())
    entry=next(t for t in availability['targets'] if t['key']==args.target)
    records=[r for r in entry['detectors'][args.detector]['observations'] if r['release']=='dr1']
    attempted={r['url'] for r in ledger['requests']}
    groups=epoch_groups(records)
    representatives=[g[len(g)//2] for g in groups]
    untried=[r for r in representatives if r['url'] not in attempted]
    if len(untried)<args.count:
        untried += [r for r in records if r['url'] not in attempted and r not in untried]
    selected=select_observations(untried,args.count)
    if len(selected)>16-len(ledger['requests']):
        raise ValueError('The requested acquisition exceeds the remaining task-wide budget.')
    write_manifest(base/args.target/f'selection_{len(ledger["requests"]):02d}.json',selected)
    def guarded(url,directory,timeout):
        digest=hashlib.sha256(url.encode()).hexdigest()[:16]
        if list(Path(directory).glob(f'*_{digest}.fits')):
            return download_cutout(url,directory,timeout=timeout)
        if len(ledger['requests'])>=16 or url in {r['url'] for r in ledger['requests']}:
            raise ValueError('Task-wide cutout budget exhausted or candidate already attempted.')
        record={'target':args.target,'url':url,'status':'requested'}
        ledger['requests'].append(record);write_manifest(ledger_path,ledger)
        try:
            path=download_cutout(url,directory,timeout=timeout)
            record.update(status='downloaded',local_path=path.relative_to(PROJECT).as_posix())
            return path
        except Exception as error:
            record.update(status='failed',error=f'{type(error).__name__}: {error}')
            raise
        finally:
            write_manifest(ledger_path,ledger)
    run_target(PROJECT,base/args.target/'preparation',availability,entry['astrometry'],
        max_downloads=args.count,total_download_budget=16,target_key=args.target,detector=args.detector,
        selected_records=selected,raw_directory=PROJECT/'data/raw/spx004a'/args.target,download_function=guarded,timeout=45)
    print(f"Task-wide requests used: {len(ledger['requests'])}/16")


if __name__=='__main__':
    main()
