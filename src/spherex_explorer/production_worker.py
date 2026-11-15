"""Isolated scientific work; parent enforces wall time and terminates this process."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import signal
import sys


def execute(operation, data, project, workspace):
    from .dynamic import parameters, search, public_search, prepare_region
    if operation=='probe':
        from .alignment import common_grid
        grid,shape=common_grid(10,20,.05,6.2)
        return {'scientificImports':True,'gridShape':list(shape)}
    if operation=='search':
        return public_search(search(project,parameters(data),timeout=20,workspace=workspace,
                                   fresh_seconds=21600,stale_seconds=data.get('cacheSeconds',604800)))
    if operation=='prepare':
        from .acquisition import AcquisitionBudget
        result=json.loads((workspace/'searches'/f'{data["searchId"]}.json').read_text())
        budget=AcquisitionBudget(project,workspace/'acquisition_ledger.json',limit=data['acquisitionLimit'],reservation=0,
                                 allow_download=not data.get('cachedOnly',False),daily_limit=data.get('dailyAcquisitions',2))
        return {'target':prepare_region(project,result,data['count'],budget=budget,workspace=workspace,cached_only=data.get('cachedOnly',False))}
    raise ValueError('Unsupported worker operation.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['probe','search','prepare'])
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--parent',type=int,required=True)
    args=parser.parse_args()
    if sys.platform=='linux':
        # Avoid an orphan acquiring data after its supervisor has died.
        if os.getppid()!=args.parent:raise SystemExit(1)
        libc=ctypes.CDLL(None,use_errno=True)
        if libc.prctl(1,signal.SIGTERM,0,0,0)!=0:raise RuntimeError('Cannot install worker parent-death guard.')
        if os.getppid()!=args.parent:raise SystemExit(1)
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(240,245))
        resource.setrlimit(resource.RLIMIT_FSIZE,(40*1024**2,40*1024**2))
    data=json.loads(args.input.read_text())
    try:
        result=execute(args.operation,data,Path(__file__).resolve().parents[2],Path(data.pop('_workspace')))
        args.output.write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
    except Exception as error:
        import traceback
        traceback.print_exc()
        args.output.write_text(json.dumps({'error':getattr(error,'public_message','Scientific work failed; inspect the private service logs.')}))
        raise SystemExit(1)


if __name__=='__main__':main()
