"""Protected loopback WSGI demo, supervised scientific subprocess and durable limits."""
from dataclasses import dataclass
from datetime import datetime,timezone
from http import HTTPStatus
import argparse
import hashlib
import hmac
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs,urlsplit
import uuid

from .production_store import Store,InstanceLock
from .demo_access import DemoSessions

PROJECT=Path(__file__).resolve().parents[2]
ID=re.compile(r'^[0-9a-f]{20}$')


@dataclass(frozen=True)
class Settings:
    state:Path
    code:str
    origins:tuple[str,...]=('https://astrosentry.vercel.app','https://spherex-explorer-one.vercel.app','http://127.0.0.1:5173')
    acquisition_limit:int=12
    job_seconds:int=300
    retention_seconds:int=3600
    storage_bytes:int=1024**3
    max_field:float=.1
    access_mode:str='protected'
    public_until:float=0
    daily_acquisitions:int=2

    def __post_init__(self):
        state=self.state.expanduser().resolve()
        if state==PROJECT or PROJECT.is_relative_to(state) or (state.is_relative_to(PROJECT) and not state.is_relative_to(PROJECT/'.runtime')):
            raise ValueError('Use a dedicated state directory outside scientific/source directories (or .runtime).')
        object.__setattr__(self,'state',state)
        if not 32<=len(self.code)<=256 or not self.code.isascii() or self.code.startswith('REPLACE_') or any(ord(c)<33 or ord(c)>126 for c in self.code):
            raise ValueError('SPX_DEMO_CODE requires a private random code of 32–256 printable ASCII characters, without spaces.')
        if not self.origins:raise ValueError('An exact frontend origin is required.')
        for origin in self.origins:
            u=urlsplit(origin)
            if (u.scheme not in {'http','https'} or not u.netloc or u.username or u.password or u.path or u.query or u.fragment or '*' in origin
                    or (u.scheme=='http' and u.hostname not in {'127.0.0.1','localhost'})):
                raise ValueError('Origins must be exact HTTPS origins or explicit local development origins.')
        if self.access_mode not in {'protected','anonymous-cached'}:raise ValueError('Choose protected or anonymous-cached access.')
        if self.access_mode=='anonymous-cached' and not 0<self.public_until<=time.time()+604800+300:
            raise ValueError('Anonymous access needs an explicit UTC end within seven days; never renew it silently.')
        if not (1<=self.acquisition_limit<=12 and 10<=self.job_seconds<=300 and 60<=self.retention_seconds<=604800
                and 256*1024**2<=self.storage_bytes<=2*1024**3 and .05<=self.max_field<=.2):
            raise ValueError('Deployment limits exceed the supported bounded demo policy.')
        if type(self.daily_acquisitions) is not int or not 1<=self.daily_acquisitions<=2:raise ValueError('Use at most two operator acquisitions per rolling day.')

    @classmethod
    def environment(cls):
        return cls(Path(os.environ['SPX_STATE_DIR']),os.environ['SPX_DEMO_CODE'],
            tuple(o.strip() for o in os.environ.get('SPX_ALLOWED_ORIGINS',','.join(cls.origins)).split(',')),
            int(os.environ.get('SPX_ACQUISITION_LIMIT','12')),int(os.environ.get('SPX_JOB_SECONDS','300')),
            int(os.environ.get('SPX_RETENTION_SECONDS','3600')),int(os.environ.get('SPX_STORAGE_MIB','1024'))*1024**2,
            float(os.environ.get('SPX_MAX_FIELD_DEG','0.1')),os.environ.get('SPX_ACCESS_MODE','protected'),
            public_end(os.environ.get('SPX_PUBLIC_UNTIL','')),int(os.environ.get('SPX_ACQUISITIONS_PER_DAY','2')))


def public_end(value):
    if not value:return 0
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('SPX_PUBLIC_UNTIL must include an explicit UTC offset.')
    return parsed.timestamp()


class ApiError(Exception):
    def __init__(self,status,message):self.status=status;self.message=message


def atomic_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    partial=path.with_suffix('.part')
    with partial.open('w',encoding='utf-8') as stream:
        json.dump(data,stream,allow_nan=False);stream.flush();os.fsync(stream.fileno())
    partial.replace(path)
    if os.name=='posix':
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)


class Application:
    def __init__(self,settings):
        self.settings=settings;self.state=settings.state
        self.state.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.instance=InstanceLock(self.state/'instance.lock')
        try:
            self.workspace=self.state/'workspace';self.workspace.mkdir(exist_ok=True)
            for name in ['tasks','logs','tmp','cache']:(self.state/name).mkdir(exist_ok=True)
            ledger=self.workspace/'acquisition_ledger.json'
            if not ledger.exists():atomic_json(ledger,{'version':1,'limit':settings.acquisition_limit,'wiseReservation':0,'attempts':[]})
            existing=json.loads(ledger.read_text())
            if existing['limit']!=settings.acquisition_limit:raise ValueError('Existing acquisition limit cannot be silently changed; preserve its ledger.')
            for entry in existing['attempts']:
                if entry['status']=='running':entry.update(status='interrupted',error='Worker stopped; this attempt remains charged.')
            atomic_json(ledger,existing)
            self.store=Store(self.state/'control.sqlite')
        except Exception:
            self.instance.close();raise
        self.slot=threading.Lock();self.stopping=threading.Event();self.active=None;self.process=None
        self.thread=None;self.ready=False
        self.sessions=DemoSessions(settings.code,settings.public_until)

    def public_enabled(self):return self.settings.access_mode=='anonymous-cached' and time.time()<self.settings.public_until

    def cached_example(self):
        path=self.workspace/'demo_example.json'
        if not path.is_file():return None
        example=json.loads(path.read_text());source=self.workspace/'searches'/f'{example["searchId"]}.json'
        return example if source.is_file() else None

    def cached_metadata(self,data,stale_reason=None):
        from .metadata_cache import age_seconds,cached_result
        key=hashlib.sha256(f'{float(data["ra"]):.10f},{float(data["dec"]):.10f},{float(data.get("size",.1)):.4f},SPHEREx-D{int(data.get("detector",2))}'.encode()).hexdigest()[:20]
        identifier=hashlib.sha256((key+':sia2').encode()).hexdigest()[:20]
        path=self.workspace/'searches'/f'{identifier}.json'
        if not path.is_file() or age_seconds(path)>self.settings.retention_seconds:return None
        failure=path.with_suffix('.failure.json')
        if age_seconds(path)<=21600:result=cached_result(json.loads(path.read_text()),path,'fresh')
        elif failure.is_file() and age_seconds(failure)<300:result=cached_result(json.loads(path.read_text()),path,'stale',json.loads(failure.read_text()))
        elif stale_reason:result=cached_result(json.loads(path.read_text()),path,'stale',{'message':stale_reason})
        else:return None
        return {k:v for k,v in result.items() if k!='records'}

    def usage(self):
        return sum(p.stat().st_size for p in self.state.rglob('*') if p.is_file() and not p.is_symlink())

    def capacity(self,reserve):
        if self.usage()+reserve>self.settings.storage_bytes or shutil.disk_usage(self.state).free<reserve+128*1024**2:
            raise ApiError(507,'Processing storage is full. Existing sky navigation and static fields remain available.')

    def worker(self,operation,data,seconds,cancel=None):
        key=uuid.uuid4().hex;input_path=self.state/'tasks'/f'{key}.json';output=self.state/'tasks'/f'{key}.result.json'
        atomic_json(input_path,{**data,'_workspace':str(self.workspace)})
        env=os.environ.copy();env.pop('SPX_DEMO_CODE',None)
        env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',
                   TMPDIR=str(self.state/'tmp'),TMP=str(self.state/'tmp'),TEMP=str(self.state/'tmp'),MPLCONFIGDIR=str(self.state/'cache'))
        with (self.state/'logs'/f'{key}.log').open('wb') as log:
            p=subprocess.Popen([sys.executable,'-m','spherex_explorer.production_worker',operation,str(input_path),str(output),'--parent',str(os.getpid())],
                               stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env)
            self.process=p;deadline=time.monotonic()+seconds
            try:
                while p.poll() is None:
                    if self.stopping.is_set() or (cancel and cancel.is_set()):raise ApiError(409,'Processing canceled.')
                    if time.monotonic()>=deadline:raise ApiError(504,'Processing exceeded its hard time limit.')
                    if self.usage()>self.settings.storage_bytes:raise ApiError(507,'Processing storage limit reached.')
                    time.sleep(.15)
                if p.returncode or not output.is_file():
                    message='Scientific processing or IRSA access failed. This is not a no-data result.'
                    if output.is_file():message=json.loads(output.read_text()).get('error',message)
                    raise ApiError(502,message)
                return json.loads(output.read_text(encoding='utf-8'))
            finally:
                if p.poll() is None:
                    p.terminate()
                    try:p.wait(timeout=3)
                    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
                self.process=None
                input_path.unlink(missing_ok=True);output.unlink(missing_ok=True)
                ledger=self.workspace/'acquisition_ledger.json'
                snapshot=json.loads(ledger.read_text())
                if any(a['status']=='running' for a in snapshot['attempts']):
                    for attempt in snapshot['attempts']:
                        if attempt['status']=='running':attempt.update(status='interrupted',error='Worker exited; this attempt remains charged.')
                    atomic_json(ledger,snapshot)

    def probe(self):
        if not self.slot.acquire(blocking=False):raise ApiError(503,'Worker is busy.')
        try:
            result=self.worker('probe',{},60);self.ready=bool(result.get('scientificImports'));return result
        finally:self.slot.release()

    def ticket(self,identifier):
        expires=int(time.time())+min(3600,self.settings.retention_seconds)
        digest=hmac.new(self.settings.code.encode(),f'asset:{identifier}:{expires}'.encode(),hashlib.sha256).hexdigest()
        return f'{expires}.{digest}'

    def valid_ticket(self,identifier,token):
        try:
            expires,digest=token.split('.')
            if not time.time()<=int(expires)<=time.time()+min(3600,self.settings.retention_seconds)+5:return False
            expected=hmac.new(self.settings.code.encode(),f'asset:{identifier}:{expires}'.encode(),hashlib.sha256).hexdigest()
            return hmac.compare_digest(digest,expected)
        except (ValueError,AttributeError):return False

    def job(self,identifier):
        if not ID.fullmatch(identifier):raise ApiError(404,'Job unavailable.')
        job=self.store.job(identifier)
        if not job:raise ApiError(404,'Job unavailable.')
        if job['status']=='ready':
            if time.time()-job['finished']>self.settings.retention_seconds:
                self.store.expire(identifier);job=self.store.job(identifier)
            else:
                path=self.workspace/'jobs'/identifier/'target.json'
                if path.is_file():
                    job.update(target=json.loads(path.read_text(encoding='utf-8')),
                               assetAccess={'jobId':identifier,'ticket':self.ticket(identifier)})
                else:
                    self.store.finish(identifier,'error','Prepared assets are unavailable. Retry explicitly.');job=self.store.job(identifier)
        return {k:v for k,v in job.items() if k not in {'created','finished'}}

    def prepare(self,data,actor=None,cached_only=False):
        identifier=data.get('searchId');count=data.get('count',4)
        if not isinstance(identifier,str) or not ID.fullmatch(identifier) or type(count) is not int or count not in [2,3,4]:
            raise ApiError(400,'Choose a server-owned search and 2–4 observations.')
        source=self.workspace/'searches'/f'{identifier}.json'
        if not source.is_file():raise ApiError(400,'Run a successful search on this service first.')
        self.validate_parameters(json.loads(source.read_text())['parameters'])
        job_id=hashlib.sha256(f'{identifier}:{count}'.encode()).hexdigest()[:20]
        prior=self.store.job(job_id)
        if prior and prior['status'] in {'ready','preparing'}:
            result=self.job(job_id)
            if result['status'] in {'ready','preparing'}:
                if actor:self.store.grant(actor[0],job_id,actor[1])
                return result
        cached_only=cached_only or actor is not None
        if cached_only:
            records=json.loads(source.read_text())['records']
            count_cached=sum(bool(list((self.workspace/'raw').glob('*_'+hashlib.sha256(r['url'].encode()).hexdigest()[:16]+'.fits'))) for r in records)
            if count_cached<2:raise ApiError(409,'This public demo processes existing cached real FITS only. No cached pair covers this request; explore a prepared field. No acquisition was attempted.')
        if not self.slot.acquire(blocking=False):raise ApiError(503,'One scientific operation is already running. Retry later.')
        try:
            self.capacity(count*36*1024**2)
            if actor and not self.store.admit('prepare:'+actor[0],1,3600):raise ApiError(429,'Session preparation limit reached; reuse the prepared sequence.')
            if not self.store.admit('preparations',4,86400):raise ApiError(429,'Daily preparation quota reached.')
            self.store.start(job_id);cancel=threading.Event();self.active=(job_id,cancel)
            if actor:self.store.grant(actor[0],job_id,actor[1],owner=True)
            def run():
                try:
                    self.worker('prepare',{'searchId':identifier,'count':count,'acquisitionLimit':self.settings.acquisition_limit,
                        'cachedOnly':cached_only,'dailyAcquisitions':self.settings.daily_acquisitions},self.settings.job_seconds,cancel)
                    self.store.finish(job_id,'ready','Real observations prepared. Exploratory comparison; derived assets expire after the configured retention.')
                except ApiError as error:
                    self.store.finish(job_id,'canceled' if cancel.is_set() else 'error',error.message)
                except Exception:
                    self.store.finish(job_id,'error','Processing failed. Inspect private service logs.')
                finally:self.active=None;self.slot.release()
            self.thread=threading.Thread(target=run,daemon=True);self.thread.start()
            return {'id':job_id,'status':'preparing','message':'Preparing real observations in a bounded worker.'}
        except Exception:
            self.slot.release();raise

    def validate_parameters(self,data):
        try:
            ra,dec,size,detector=[data.get(k,d) for k,d in [('ra',None),('dec',None),('size',.1),('detector',2)]]
            if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in [ra,dec,size,detector]):raise ValueError()
            if not(0<=ra<360 and -90<=dec<=90 and .05<=size<=self.settings.max_field and detector in [1,2,3,4,5,6]):raise ValueError()
        except (ValueError,TypeError):raise ApiError(400,'Invalid finite ICRS coordinates, detector or permitted field width.') from None

    def cleanup(self):
        if not self.slot.acquire(blocking=False):return
        try:
            def remove(path):
                root=self.workspace.resolve();resolved=path.resolve()
                if not resolved.is_relative_to(root) or resolved==root or path.is_symlink():raise RuntimeError('Unsafe cleanup path refused.')
                if path.is_dir():shutil.rmtree(path)
                else:path.unlink(missing_ok=True)
            for identifier in self.store.expired(self.settings.retention_seconds):
                if not ID.fullmatch(identifier):continue
                for p in [self.workspace/'jobs'/identifier,self.workspace/'assets/dynamic'/identifier]:
                    if p.exists():remove(p)
                self.store.expire(identifier)
            self.store.prune()
            cutoff=time.time()-self.settings.retention_seconds
            for directory in ['raw','searches']:
                for path in (self.workspace/directory).glob('*'):
                    if path.stat().st_mtime<cutoff:remove(path)
            for directory in ['tasks','logs','tmp']:
                for path in (self.state/directory).glob('*'):
                    if path.stat().st_mtime<cutoff:
                        resolved=path.resolve()
                        if not resolved.is_relative_to((self.state/directory).resolve()) or path.is_symlink():continue
                        if path.is_dir():shutil.rmtree(path)
                        else:path.unlink(missing_ok=True)
        finally:self.slot.release()

    def __call__(self,environ,start_response):
        origin=environ.get('HTTP_ORIGIN');method=environ['REQUEST_METHOD'];path=environ.get('PATH_INFO','')
        headers=[('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),('Vary','Origin')]
        if origin in self.settings.origins:
            headers += [('Access-Control-Allow-Origin',origin),('Access-Control-Allow-Methods','GET, HEAD, POST, OPTIONS'),('Access-Control-Allow-Headers','Content-Type, Authorization')]
            if environ.get('HTTP_ACCESS_CONTROL_REQUEST_PRIVATE_NETWORK')=='true':headers.append(('Access-Control-Allow-Private-Network','true'))
        def respond(status,data):
            body=b'' if status==204 else json.dumps(data,allow_nan=False).encode();start_response(f'{status} {HTTPStatus(status).phrase}',headers+[('Content-Type','application/json'),('Content-Length',str(len(body)))])
            return [] if method=='HEAD' else [body]
        try:
            if origin is not None and origin not in self.settings.origins:raise ApiError(403,'Origin not allowed.')
            if not self.store.admit('http',240,60):raise ApiError(429,'Request limit reached. Retry later.')
            if method=='OPTIONS':return respond(204,{})
            if method not in {'GET','HEAD','POST'}:raise ApiError(405,'Method not allowed.')
            if path=='/api/health' and method in {'GET','HEAD'}:
                return respond(200 if self.ready else 503,{'status':'ready' if self.ready else 'starting','authenticationRequired':not self.public_enabled(),'localCoverage':False,
                    'maxFieldDeg':self.settings.max_field,'maxFrames':4,'retentionSeconds':self.settings.retention_seconds,
                    'publicExposureValidated':False,'accessMode':'anonymous-cached' if self.public_enabled() else 'protected',
                    'publicUntilUtc':datetime.fromtimestamp(self.settings.public_until,timezone.utc).isoformat() if self.settings.public_until else None,
                    'cachedExample':self.cached_example(),'anonymousAcquisitions':0,'mode':'bounded-single-instance-demo'})
            if path=='/api/session' and method=='POST':
                if not self.public_enabled() or origin not in self.settings.origins:raise ApiError(403,'Anonymous demonstration is unavailable.')
                if not self.ready:raise ApiError(503,'Scientific worker is not ready.')
                if environ.get('CONTENT_TYPE','').split(';')[0]!='application/json' or environ.get('CONTENT_LENGTH')!='2' or environ['wsgi.input'].read(2)!=b'{}':raise ApiError(400,'Send an empty JSON object.')
                if not self.store.admit('sessions-minute',6,60) or not self.store.admit('sessions-day',60,86400):raise ApiError(429,'Anonymous session quota reached; static fields remain available.')
                return respond(201,{'session':self.sessions.issue(),'scope':'metadata-and-cached-preparation','newAcquisitions':0})
            if path.startswith('/assets/dynamic/') and method in {'GET','HEAD'}:
                parts=path.strip('/').split('/');query=parse_qs(environ.get('QUERY_STRING',''));tokens=query.get('ticket',[])
                if len(parts)!=5 or not ID.fullmatch(parts[2]) or parts[3]!='frames' or len(tokens)!=1 or not self.valid_ticket(parts[2],tokens[0]):raise ApiError(403,'Asset access expired or invalid. Unlock and reopen the job.')
                if not re.fullmatch(r'[A-Za-z0-9_.-]+',parts[4]):raise ApiError(404,'Asset unavailable.')
                # Derived files live in workspace/assets/dynamic, never raw/.
                file=(self.workspace/'assets'/path.removeprefix('/assets/')).resolve();root=(self.workspace/'assets/dynamic').resolve()
                if not file.is_relative_to(root) or not file.is_file() or file.suffix not in {'.fits','.png','.json'} or file.stat().st_size>2*1024**2:raise ApiError(404,'Asset unavailable.')
                if self.job(parts[2])['status']!='ready':raise ApiError(410,'Assets expired or unavailable.')
                start_response('200 OK',headers+[('Content-Type','application/fits' if file.suffix=='.fits' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream'),('Content-Length',str(file.stat().st_size))])
                if method=='HEAD':return []
                def stream():
                    with file.open('rb') as f:
                        while chunk:=f.read(65536):yield chunk
                return stream()
            authorization=environ.get('HTTP_AUTHORIZATION','');provided=authorization.removeprefix('Bearer ')
            actor=self.sessions.read(authorization.removeprefix('Demo ')) if authorization.startswith('Demo ') and self.public_enabled() else None
            if not actor and not (authorization.startswith('Bearer ') and hmac.compare_digest(provided.encode('utf-8'),self.settings.code.encode('ascii'))):
                if not self.store.admit('failed-auth',10,60):raise ApiError(429,'Access attempts limited. Retry later.')
                raise ApiError(401,'Demo access code required or invalid.')
            if not self.ready:raise ApiError(503,'Scientific worker is not ready.')
            if path.startswith('/api/jobs/') and method in {'GET','HEAD'}:
                identifier=path.rsplit('/',1)[-1]
                if actor and not self.store.permitted(actor[0],identifier):raise ApiError(404,'Job is not available to this session. Repeat the cached preparation to obtain access.')
                return respond(200,self.job(identifier))
            if method!='POST':raise ApiError(404,'Route not found.')
            try:
                length=int(environ.get('CONTENT_LENGTH','0'))
                if not 0<length<=4096 or environ.get('CONTENT_TYPE','').split(';')[0]!='application/json':raise ValueError()
                data=json.loads(environ['wsgi.input'].read(length))
                if not isinstance(data,dict):raise ValueError()
            except (ValueError,TypeError):raise ApiError(400,'A bounded JSON object is required.') from None
            if path=='/api/access':return respond(200,{'authorized':True})
            if path=='/api/search':
                self.validate_parameters(data)
                if data.get('localOnly'):raise ApiError(400,'This deployment searches IRSA; historical local-cache search is unavailable.')
                if not self.slot.acquire(blocking=False):raise ApiError(503,'Scientific worker busy. Retry later.')
                try:
                    if actor and not self.store.admit('search:'+actor[0],3,3600):raise ApiError(429,'Session metadata search quota reached.')
                    cached=self.cached_metadata(data)
                    if cached:return respond(200,cached)
                    self.capacity(8*1024**2)
                    if not self.store.admit('searches',12,3600):
                        fallback=self.cached_metadata(data,'Live query skipped: hourly upstream metadata quota reached.')
                        if fallback:return respond(200,fallback)
                        raise ApiError(429,'Hourly metadata search quota reached.')
                    try:return respond(200,self.worker('search',{**data,'cacheSeconds':self.settings.retention_seconds},60))
                    except ApiError as error:
                        fallback=self.cached_metadata(data,error.message)
                        if fallback:return respond(200,fallback)
                        raise
                finally:self.slot.release()
            if path=='/api/prepare':return respond(202,self.prepare(data,actor=actor))
            match=re.fullmatch(r'/api/jobs/([0-9a-f]{20})/cancel',path)
            if match:
                if actor and not self.store.permitted(actor[0],match[1],cancel=True):raise ApiError(403,'This session cannot cancel that job.')
                if self.active and self.active[0]==match[1]:self.active[1].set()
                return respond(200,{'status':'cancellation-requested'})
            raise ApiError(404,'Route not found.')
        except ApiError as error:return respond(error.status,{'error':error.message})
        except sqlite3.OperationalError:return respond(503,{'error':'Quota store busy. Retry later.'})
        except Exception:return respond(500,{'error':'Processing service error. Inspect private service logs.'})

    def close(self):
        self.stopping.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        if self.thread:self.thread.join(timeout=5)
        self.instance.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8766);parser.add_argument('--check',action='store_true');parser.add_argument('--validate-cache',metavar='SEARCH_ID')
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Use a nonprivileged loopback port.')
    app=Application(Settings.environment())
    def terminate(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,terminate)
    try:
        result=app.probe()
        if args.check:print(json.dumps({'ready':app.ready,**result}));return
        if args.validate_cache:
            before=json.loads((app.workspace/'acquisition_ledger.json').read_text())
            job=app.prepare({'searchId':args.validate_cache,'count':4},cached_only=True)
            if app.thread:app.thread.join(timeout=app.settings.job_seconds+10)
            completed=app.job(job['id'])
            after=json.loads((app.workspace/'acquisition_ledger.json').read_text())
            if completed['status']!='ready' or before!=after:raise RuntimeError('Offline cache validation failed; inspect worker logs. No live retry is allowed.')
            print(json.dumps({'status':'ready','acquisitionMode':'existing-local-FITS-only','acquisitionsBefore':len(before['attempts']),
                'acquisitionsAfter':len(after['attempts']),'frames':[f['observation'] for f in completed['target']['sequence']['frames']]}));return
        from waitress import serve
        def maintain():
            while not app.stopping.wait(60):
                try:app.cleanup()
                except Exception:print('Retention cleanup failed; inspect the dedicated state directory.',file=sys.stderr)
        threading.Thread(target=maintain,daemon=True).start()
        print(f'Protected backend: http://127.0.0.1:{args.port}; one scientific subprocess; durable quotas.',flush=True)
        serve(app,host='127.0.0.1',port=args.port,threads=4,connection_limit=64,channel_timeout=30,
              max_request_body_size=4096,max_request_header_size=8192,clear_untrusted_proxy_headers=True)
    except KeyboardInterrupt:pass
    finally:app.close()


if __name__=='__main__':main()
