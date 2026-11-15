"""Offline anonymous capability, ownership, expiry and zero-acquisition policy."""
from io import BytesIO
import hashlib
import json
import time

import pytest

from spherex_explorer.production_api import Application,Settings,atomic_json
from spherex_explorer.acquisition import AcquisitionBudget

CODE='controlled-unit-code-not-a-deployment-credential'
SEARCH='a'*20
URL='https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/test/level2_2025W01_1A_0001_1D2_spx_v1.fits?center=10,20&size=0.05'


@pytest.fixture
def app(tmp_path):
    instance=Application(Settings(tmp_path/'state',CODE,retention_seconds=604800,access_mode='anonymous-cached',public_until=time.time()+86400));instance.ready=True
    yield instance
    instance.close()


def request(app,path,body=None,token=None,origin=True):
    payload=json.dumps(body).encode() if body is not None else b''
    env={'REQUEST_METHOD':'POST' if body is not None else 'GET','PATH_INFO':path,'wsgi.input':BytesIO(payload),'CONTENT_LENGTH':str(len(payload)),'CONTENT_TYPE':'application/json'}
    if origin:env['HTTP_ORIGIN']=app.settings.origins[0]
    if token:env['HTTP_AUTHORIZATION']='Demo '+token
    result={}
    def start(status,headers):result['status']=int(status.split()[0])
    result['body']=json.loads(b''.join(app(env,start)));return result


def session(app):
    reply=request(app,'/api/session',{});assert reply['status']==201;return reply['body']['session']


def source(app,cached=True):
    records=[{'url':URL},{'url':URL.replace('0001_1','0002_1')}]
    atomic_json(app.workspace/'searches'/f'{SEARCH}.json',{'parameters':{'ra':10,'dec':20,'size':.05,'detector':2},'records':records})
    if cached:
        raw=app.workspace/'raw';raw.mkdir()
        for r in records:(raw/('fixture_'+hashlib.sha256(r['url'].encode()).hexdigest()[:16]+'.fits')).write_bytes(b'unit fixture; scientific worker is mocked')


def test_anonymous_is_explicit_temporary_and_origin_scoped(app):
    assert request(app,'/api/health')['body']['authenticationRequired'] is False
    assert request(app,'/api/session',{},origin=False)['status']==403
    token=session(app);assert app.sessions.read(token)
    assert not app.sessions.read(token[:-1]+('0' if token[-1]!='0' else '1'))
    app.sessions.until=time.time()-1
    assert not app.sessions.read(token)
    with pytest.raises(ValueError):Settings(app.state,CODE,access_mode='anonymous-cached')
    with pytest.raises(ValueError):Settings(app.state,CODE,access_mode='anonymous-cached',public_until=time.time()+700000)


def test_no_session_cannot_search_and_uncached_preparation_never_launches_worker(app,monkeypatch):
    source(app,cached=False)
    def forbidden(*args):raise AssertionError('No worker may start for uncached anonymous preparation.')
    monkeypatch.setattr(app,'worker',forbidden)
    assert request(app,'/api/search',{'ra':10,'dec':20})['status']==401
    reply=request(app,'/api/prepare',{'searchId':SEARCH,'count':4},session(app))
    assert reply['status']==409 and 'No acquisition was attempted' in reply['body']['error']


def test_job_grants_cancel_ownership_and_ready_reuse_are_separate(app,monkeypatch):
    source(app);first=session(app);second=session(app);calls=[]
    identifier=hashlib.sha256(f'{SEARCH}:4'.encode()).hexdigest()[:20]
    def worker(operation,data,*args):
        calls.append(data);assert data['cachedOnly'] is True
        atomic_json(app.workspace/'jobs'/identifier/'target.json',{'id':'unit fixture','assets':{}})
    monkeypatch.setattr(app,'worker',worker)
    reply=request(app,'/api/prepare',{'searchId':SEARCH,'count':4},first);assert reply['status']==202
    app.thread.join(5)
    assert request(app,'/api/jobs/'+identifier,token=first)['status']==200
    assert request(app,'/api/jobs/'+identifier,token=second)['status']==404
    assert request(app,'/api/jobs/'+identifier+'/cancel',{},second)['status']==403
    shared=request(app,'/api/prepare',{'searchId':SEARCH,'count':4},second)
    assert shared['body']['status']=='ready' and len(calls)==1
    assert request(app,'/api/jobs/'+identifier,token=second)['status']==200
    assert request(app,'/api/jobs/'+identifier+'/cancel',{},second)['status']==403
    assert 'ticket' not in json.dumps(shared['body']['target'])
    app.store.start(identifier)
    assert not app.store.permitted(app.sessions.read(first)[0],identifier,cancel=True)


def test_durable_session_quota_and_per_session_metadata_bound(app,monkeypatch):
    fixed=int(time.time()//60)*60+15
    monkeypatch.setattr('spherex_explorer.production_store.time.time',lambda:fixed)
    monkeypatch.setattr(app,'worker',lambda *args:{'count':0})
    token=session(app)
    for _ in range(3):assert request(app,'/api/search',{'ra':10,'dec':20},token)['status']==200
    assert request(app,'/api/search',{'ra':10,'dec':20},token)['status']==429
    for _ in range(5):session(app)
    assert request(app,'/api/session',{})['status']==429


def test_cached_only_and_daily_budget_do_not_spend_lifetime_attempts(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('HTTP is forbidden.')
    monkeypatch.setattr('spherex_explorer.acquisition.download_cutout',forbidden)
    budget=AcquisitionBudget(tmp_path,tmp_path/'state/ledger.json',12,0,allow_download=False)
    with pytest.raises(ValueError,match='no HTTP acquisition'):budget.download(URL,tmp_path/'raw')
    assert budget.snapshot()['attempts']==[]
    ledger=budget.snapshot();ledger['attempts']=[{'startedUtc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'purpose':'dynamic'}]*2
    budget._save(ledger);budget.allow_download=True;budget.daily_limit=2
    with pytest.raises(ValueError,match='24-hour'):budget.download(URL,tmp_path/'raw')
    assert len(budget.snapshot()['attempts'])==2


def test_retained_metadata_remains_available_when_upstream_quota_is_full(app,monkeypatch):
    import os
    from spherex_explorer.dynamic import search_key
    from spherex_explorer.data_access import SearchParameters
    identifier=hashlib.sha256((search_key(SearchParameters(10,20,.05))+':sia2').encode()).hexdigest()[:20]
    path=app.workspace/'searches'/f'{identifier}.json'
    atomic_json(path,{'id':identifier,'records':[],'count':0,'source':'Previously successful empty fixture'})
    for _ in range(12):assert app.store.admit('searches',12,3600)
    def forbidden(*args):raise AssertionError('Cached metadata must not launch a worker.')
    monkeypatch.setattr(app,'worker',forbidden);token=session(app)
    assert request(app,'/api/search',{'ra':10,'dec':20,'size':.05},token)['body']['cache']['status']=='fresh'
    os.utime(path,(time.time()-25200,time.time()-25200))
    reply=request(app,'/api/search',{'ra':10,'dec':20,'size':.05},token)
    assert reply['status']==200 and reply['body']['cache']['status']=='stale'
    assert 'quota' in reply['body']['cache']['upstreamError']['message']


def test_import_refuses_unsafe_archive_and_active_state(app,tmp_path):
    from zipfile import ZipFile
    from spherex_explorer.demo_cache import import_bundle
    bundle=tmp_path/'malicious.zip'
    with ZipFile(bundle,'w') as archive:archive.writestr('../escaped.fits','forbidden')
    with pytest.raises(RuntimeError,match='Another backend'):import_bundle(bundle,app.state)
    with pytest.raises(ValueError,match='bounded metadata'):import_bundle(bundle,tmp_path/'new-state')
    assert not (tmp_path/'escaped.fits').exists()
