"""Read-only deployment assessment; never a public server or acquisition command."""
import argparse
import ctypes
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/spx007c'


def memory():
    """Return checked process counters; Windows private bytes are not Linux RSS."""
    if sys.platform == 'win32':
        names = ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
                 'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage',
                 'PagefileUsage','PeakPagefileUsage','PrivateUsage']
        class Counters(ctypes.Structure):
            _fields_ = [('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),
                        *[(name,ctypes.c_size_t) for name in names]]
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        api = ctypes.WinDLL('psapi',use_last_error=True)
        api.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
        api.GetProcessMemoryInfo.restype = ctypes.c_int
        c = Counters();c.cb=ctypes.sizeof(c)
        if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(c),c.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'rssMiB':round(c.WorkingSetSize/1048576,1),
                'peakRssMiB':round(c.PeakWorkingSetSize/1048576,1),
                'windowsPrivateMiB':round(c.PrivateUsage/1048576,1)}
    if sys.platform == 'linux':
        import resource
        return {'peakRssMiB':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1)}
    return {'error':'Memory measurement is not implemented for this platform.'}


def assess(measure=False):
    source = ROOT/'src/spherex_explorer/local_api.py'
    report = {'status':'blocked','productionReady':False,'python':sys.version,
              'reviewedLocalApiSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'newAcquisitions':0,'runtimeModified':False,
              'dependencies':{n:importlib.metadata.version(n) for n in
                  ['astropy','astroquery','numpy','matplotlib','requests','reproject','scipy','pillow']},
              'currentContract':{'host':'127.0.0.1','defaultPort':8765,'portSource':'--port, not PORT',
                  'server':'stdlib ThreadingHTTPServer','workerConcurrency':1,'maxFrames':4,
                  'perCutoutMaxMiB':32,'jobDeadline':'300 seconds, cooperative checks between acquisitions',
                  'storage':'local filesystem and process-local running jobs; no automatic cleanup',
                  'cors':'loopback Host and explicitly allowed localhost origins by default'},
              'blockers':['No production HTTP application/server entrypoint',
                  'No authentication or application request-rate limiter',
                  'Metadata requests can accumulate while waiting on the query lock',
                  'Acquisition quota is a local file; ephemeral restart can reset it',
                  'No hard isolated-job termination or restart-safe running-job state',
                  'No safe retention/cleanup policy for a separate cloud workspace',
                  'Render Free has no persistent disk; Vercel functions do not preserve this worker model'],
              'decision':'Keep the stable static deployment and loopback demo. Render with persistent storage is the preferred future platform, subject to budget and hardening; no deployment is approved by this assessment.'}
    if measure:
        from spherex_explorer.observation import Observation
        from spherex_explorer.alignment import common_grid,align_observation
        began=time.monotonic();before=memory()
        grid,shape=common_grid(304.693508808,42.4436872991,.05,6.2)
        inputs=sorted((ROOT/'outputs/spx007b/raw').glob('*.fits'))
        items=[align_observation(Observation.read(path,'dr1'),grid,shape) for path in inputs]
        report['cachedAlignmentMeasurement']={'platform':sys.platform,'frames':len(items),
            'shape':list(shape),'afterImports':before,'afterAlignment':memory(),
            'elapsedAlignmentSeconds':round(time.monotonic()-began,2),
            'limitation':'Cached small-field alignment only, no network/export/server load. Windows results do not certify Linux container capacity.'}
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--measure',action='store_true',help='Align existing phase-B cutouts in memory only.')
    parser.add_argument('--require-production',action='store_true',help='Exit 2 when production readiness is blocked.')
    args=parser.parse_args();report=assess(args.measure)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'runtime_assessment.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    raise SystemExit(2 if args.require_production and not report['productionReady'] else 0)
