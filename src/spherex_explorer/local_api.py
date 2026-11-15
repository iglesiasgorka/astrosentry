"""Loopback-only bounded demo API; no remote deployment or persistent-worker claim."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import mimetypes
import re
import threading
from urllib.parse import unquote, urlsplit

from .dynamic import parameters, search, local_search, public_search, prepare_region
from .fits_utils import write_manifest
from .acquisition import AcquisitionBudget


class Service:
    def __init__(self, project):
        self.project = Path(project).resolve()
        self.root = self.project/'outputs/spx006b'
        self.root.mkdir(parents=True, exist_ok=True)
        ledger = self.project/'outputs/spx006/acquisition_ledger.json'
        if not ledger.exists():
            write_manifest(ledger, {'version':1,'limit':24,'wiseReservation':8,'attempts':[]})
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.lock = threading.RLock()
        self.jobs = {}

    def prepare(self, search_id, count):
        if not re.fullmatch(r'[0-9a-f]{20}', str(search_id)) or type(count) is not int or count not in [2,3,4]:
            raise ValueError('Invalid search identifier or observation count.')
        source = self.root/'searches'/f'{search_id}.json'
        if not source.exists():
            raise ValueError('Run a successful metadata search before preparation.')
        result = json.loads(source.read_text())
        import hashlib
        job_id = hashlib.sha256(f'{search_id}:{count}'.encode()).hexdigest()[:20]
        previous = self.root/'jobs'/job_id/'public.json'
        with self.lock:
            if job_id in self.jobs:
                if self.jobs[job_id]['public']['status'] in {'ready','preparing'}:return self.jobs[job_id]['public']
                self.jobs.pop(job_id)
            if previous.exists():
                cached = json.loads(previous.read_text())
                if cached['status'] == 'ready':
                    return cached
            if any(job['public']['status']=='preparing' for job in self.jobs.values()):
                raise RuntimeError('One preparation is already running. Wait or cancel it first.')
            if len(self.jobs)>=8:
                finished=next((key for key,value in self.jobs.items() if value['public']['status']!='preparing'),None)
                if finished:self.jobs.pop(finished)
            public={'id':job_id,'status':'preparing','message':'Preparing a bounded sequence from real cutouts.'}
            cancel=threading.Event();self.jobs[job_id]={'public':public,'cancel':cancel}
            self.executor.submit(self._run, job_id, result, count, cancel)
            return dict(public)

    def _run(self, job_id, result, count, cancel):
        try:
            target=prepare_region(self.project,result,count,cancel)
            public={'id':job_id,'status':'ready','target':target,'message':'Real observations prepared locally; not a deployed public processing service.'}
        except InterruptedError:
            public={'id':job_id,'status':'canceled','message':'Preparation canceled; completed downloads remain cached.'}
        except Exception as error:
            write_manifest(self.root/'jobs'/job_id/'failure.json',{'type':type(error).__name__,'error':str(error)})
            public={'id':job_id,'status':'error','message':'A real sequence could not be prepared. The archive, coverage, quality or acquisition budget may prevent two usable frames. See the local preparation report.'}
        with self.lock:
            self.jobs[job_id]['public']=public
            write_manifest(self.root/'jobs'/job_id/'public.json',public)

    def job(self, job_id):
        if not re.fullmatch(r'[0-9a-f]{20}',job_id):
            raise ValueError('Invalid job identifier.')
        with self.lock:
            if job_id in self.jobs:return dict(self.jobs[job_id]['public'])
        path=self.root/'jobs'/job_id/'public.json'
        if path.exists():return json.loads(path.read_text())
        raise FileNotFoundError('Job not found.')


def handler(service, origins):
    class Handler(BaseHTTPRequestHandler):
        def allowed(self):
            host=self.headers.get('Host','').split(':')[0]
            origin=self.headers.get('Origin')
            return host in {'127.0.0.1','localhost'} and (origin is None or origin in origins)

        def cors(self):
            origin=self.headers.get('Origin')
            if origin in origins:self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
            self.send_header('Access-Control-Allow-Methods','GET, HEAD, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers','Content-Type')

        def respond(self,status,data):
            body=json.dumps(data,allow_nan=False).encode()
            self.send_response(status);self.cors();self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers()
            if self.command!='HEAD':self.wfile.write(body)

        def do_OPTIONS(self):
            self.respond(200 if self.allowed() else 403,{})

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self.allowed():return self.respond(403,{'error':'Origin or Host is not allowed.'})
            path=urlsplit(self.path).path
            if path=='/api/health':
                ledger=AcquisitionBudget(service.project).snapshot()
                return self.respond(200,{'mode':'local-demo','preparation':True,'acquisitionLimit':ledger['limit'],'attemptsUsed':len(ledger['attempts'])})
            if path.startswith('/api/jobs/'):
                try:return self.respond(200,service.job(path.rsplit('/',1)[-1]))
                except (ValueError,FileNotFoundError):return self.respond(404,{'error':'Job unavailable.'})
            if path.startswith('/assets/dynamic/'):
                root=(service.root/'assets').resolve();file=(root/unquote(path[len('/assets/'):])).resolve()
                if not file.is_relative_to(root) or not file.is_file() or file.suffix not in {'.fits','.png','.json'}:
                    return self.respond(404,{'error':'Asset unavailable.'})
                self.send_response(200);self.cors();self.send_header('Content-Type','application/fits' if file.suffix=='.fits' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length',str(file.stat().st_size));self.send_header('Cache-Control','public, max-age=3600');self.end_headers()
                if self.command!='HEAD':
                    with file.open('rb') as stream:
                        while chunk:=stream.read(65536):self.wfile.write(chunk)
                return
            self.respond(404,{'error':'Route not found.'})

        def do_POST(self):
            if not self.allowed():return self.respond(403,{'error':'Origin or Host is not allowed.'})
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=16384:raise ValueError('Request body must be 1–16384 bytes.')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('A JSON object is required.')
                path=urlsplit(self.path).path
                if path=='/api/search':
                    p=parameters(data)
                    try:return self.respond(200,public_search(local_search(service.project,p) if data.get('localOnly') is True else search(service.project,p)))
                    except Exception as error:
                        write_manifest(service.root/'last_query_error.json',{'type':type(error).__name__,'error':str(error),'parameters':data})
                        return self.respond(502,{'error':'IRSA metadata query failed or timed out. This is an archive/network error, not a no-data result.'})
                if path=='/api/prepare':return self.respond(202,service.prepare(data.get('searchId'),data.get('count',4)))
                match=re.fullmatch(r'/api/jobs/([0-9a-f]{20})/cancel',path)
                if match:
                    with service.lock:
                        if match[1] in service.jobs:service.jobs[match[1]]['cancel'].set()
                    return self.respond(200,{'status':'cancellation-requested'})
                return self.respond(404,{'error':'Route not found.'})
            except (ValueError,KeyError,TypeError):self.respond(400,{'error':'Invalid parameters. Require finite RA 0–360 exclusive, Dec ±90, FoV 0.05–0.20 degrees and detector 1–6.'})
            except RuntimeError as error:self.respond(409,{'error':str(error)})

    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--origin',action='append',default=['http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:5179'])
    args=parser.parse_args();service=Service(Path(__file__).resolve().parents[2])
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(service,set(args.origin)))
    print(f'Local demo API: http://127.0.0.1:{args.port}; one preparation worker; persistent task-wide budget.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        for job in service.jobs.values():job['cancel'].set()
        server.server_close();service.executor.shutdown(wait=True,cancel_futures=True)


if __name__=='__main__':main()
