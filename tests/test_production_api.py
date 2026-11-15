"""Offline deployment controls, including real supervised child termination."""
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from spherex_explorer.production_api import Application, ApiError, Settings, atomic_json
from spherex_explorer.production_store import Store, InstanceLock

CODE='offline-test-code-that-is-never-a-real-secret'
JOB='a'*20


@pytest.fixture
def app(tmp_path):
    service=Application(Settings(tmp_path/'state',CODE));service.ready=True
    yield service
    service.close()


def request(app,path='/api/health',method='GET',data=None,code=None,origin=None,query=''):
    body=json.dumps(data).encode() if data is not None else b''
    env={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':query,'wsgi.input':BytesIO(body),
         'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'application/json'}
    if code is not None:env['HTTP_AUTHORIZATION']='Bearer '+code
    if origin is not None:env['HTTP_ORIGIN']=origin
    result={}
    def start(status,headers):result.update(status=int(status.split()[0]),headers=dict(headers))
    output=app(env,start)
    try:result['body']=b''.join(output)
    finally:
        if hasattr(output,'close'):output.close()
    return result


def prepared(app):
    app.store.start(JOB);app.store.finish(JOB,'ready','Ready')
    atomic_json(app.workspace/'jobs'/JOB/'target.json',{'assets':{'fits':f'dynamic/{JOB}/frames/test.fits'}})
    path=app.workspace/'assets/dynamic'/JOB/'frames/test.fits';path.parent.mkdir(parents=True);path.write_bytes(b'fixture')
    return path


def test_configuration_fails_closed(tmp_path):
    for options in [dict(code='short'),dict(code='REPLACE_WITH_A_RANDOM_PRIVATE_CODE_BEFORE_START'),dict(origins=('https://*.vercel.app',)),dict(origins=('http://evil.example',)),
                    dict(acquisition_limit=13),dict(job_seconds=301),dict(max_field=.3)]:
        with pytest.raises(ValueError):Settings(tmp_path,options.pop('code',CODE),**options)
    with pytest.raises(ValueError):Settings(Path(__file__).resolve().parents[1]/'data',CODE)


def test_authentication_cors_and_bounds(app):
    assert request(app)['status']==200
    assert request(app,'/api/search','POST',{},origin='https://evil.example')['status']==403
    assert request(app,'/api/search','POST',{})['status']==401
    assert request(app,'/api/access','POST',{},CODE)['status']==200
    assert request(app,'/api/access','POST',{},'é'*40)['status']==401
    preflight=request(app,method='OPTIONS',origin=app.settings.origins[0])
    assert preflight['status']==204 and preflight['body']==b''
    assert preflight['headers']['Access-Control-Allow-Origin']==app.settings.origins[0]
    for data in [dict(ra=360,dec=0),dict(ra=0,dec=float('nan')),dict(ra=True,dec=0),dict(ra=0,dec=0,size=.2),dict(ra=0,dec=0,detector=7)]:
        assert request(app,'/api/search','POST',data,CODE)['status']==400
    assert request(app,'/api/prepare','POST',{'searchId':'../../x','count':4},CODE)['status']==400


def test_astrosentry_origin_transition_keeps_explicit_local_testing(app):
    for origin in ['https://astrosentry.vercel.app','https://spherex-explorer-one.vercel.app','http://127.0.0.1:5173']:
        result=request(app,origin=origin)
        assert result['status']==200
        assert result['headers']['Access-Control-Allow-Origin']==origin
    assert request(app,origin='https://unapproved.vercel.app')['status']==403


def test_persistent_quota_recovery_and_exclusive_lock(tmp_path):
    db=tmp_path/'control.sqlite';store=Store(db)
    assert store.admit('acquisition-demo',1,3600)
    store.start(JOB)
    second=Store(db)
    assert not second.admit('acquisition-demo',1,3600)
    assert second.job(JOB)['status']=='error'
    lock=InstanceLock(tmp_path/'lock')
    try:
        with pytest.raises(RuntimeError):InstanceLock(tmp_path/'lock')
    finally:lock.close()
    InstanceLock(tmp_path/'lock').close()


def test_scientific_slot_and_quotas_block_before_worker(app,monkeypatch):
    calls=[]
    monkeypatch.setattr(app,'worker',lambda *a:calls.append(a) or {'count':0})
    app.slot.acquire()
    try:assert request(app,'/api/search','POST',{'ra':10,'dec':20},CODE)['status']==503
    finally:app.slot.release()
    for _ in range(12):assert app.store.admit('searches',12,3600)
    assert request(app,'/api/search','POST',{'ra':10,'dec':20},CODE)['status']==429
    assert not calls
    monkeypatch.setattr(app,'usage',lambda:app.settings.storage_bytes)
    with pytest.raises(ApiError,match='Processing storage is full'):app.capacity(1)


def test_assets_are_scoped_expiring_and_raw_is_private(app):
    prepared(app);ticket=app.ticket(JOB)
    path=f'/assets/dynamic/{JOB}/frames/test.fits'
    assert request(app,path)['status']==403
    assert request(app,path,query='ticket='+ticket)['body']==b'fixture'
    assert request(app,path.replace(JOB,'b'*20),query='ticket='+ticket)['status']==403
    assert request(app,path,query='ticket=1.'+'0'*64)['status']==403
    assert request(app,'/assets/raw/test.fits',code=CODE)['status']==404
    public=json.loads(request(app,'/api/jobs/'+JOB,code=CODE)['body'])
    assert public['assetAccess']['jobId']==JOB
    assert 'ticket' not in json.dumps(public['target'])
    assert str(app.state) not in json.dumps(public)


def test_cleanup_preserves_ledger_and_skips_active_work(app,monkeypatch):
    asset=prepared(app);ledger=app.workspace/'acquisition_ledger.json';before=ledger.read_bytes()
    with app.store.connect() as db:db.execute('UPDATE jobs SET finished=?',(time.time()-7200,))
    app.slot.acquire()
    try:app.cleanup();assert asset.exists()
    finally:app.slot.release()
    app.cleanup()
    assert not asset.exists() and ledger.read_bytes()==before
    assert app.job(JOB)['status']=='expired'


def test_hard_timeout_kills_real_child(app,monkeypatch):
    original=subprocess.Popen;children=[]
    def sleeping_child(*args,**kwargs):
        child=original([sys.executable,'-c','import time; time.sleep(30)'],**kwargs);children.append(child);return child
    monkeypatch.setattr('spherex_explorer.production_api.subprocess.Popen',sleeping_child)
    started=time.monotonic()
    with pytest.raises(ApiError,match='hard time limit'):app.worker('probe',{},.25)
    assert time.monotonic()-started<8 and children[0].poll() is not None
    assert not list((app.state/'tasks').glob('*.json'))


def test_cancellation_kills_real_child(app,monkeypatch):
    import threading
    original=subprocess.Popen;children=[]
    def sleeping_child(*args,**kwargs):
        child=original([sys.executable,'-c','import time; time.sleep(30)'],**kwargs);children.append(child);return child
    monkeypatch.setattr('spherex_explorer.production_api.subprocess.Popen',sleeping_child)
    cancel=threading.Event();cancel.set()
    with pytest.raises(ApiError,match='canceled'):app.worker('probe',{},20,cancel)
    assert children[0].poll() is not None


def test_external_state_records_paths_and_charges_before_http(tmp_path,monkeypatch):
    from spherex_explorer.acquisition import AcquisitionBudget
    project=tmp_path/'clone';project.mkdir();state=tmp_path/'persistent'
    budget=AcquisitionBudget(project,state/'acquisition_ledger.json',limit=1,reservation=0)
    url='https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/test/level2_2025W01_1A_0001_1D6_spx_l2b-v1.fits?center=1,2d&size=0.1'
    def offline_download(url,directory,**kwargs):
        assert len(budget.snapshot()['attempts'])==1
        assert budget.snapshot()['attempts'][0]['status']=='running'
        directory.mkdir(parents=True,exist_ok=True);file=directory/'fixture.fits';file.write_bytes(b'unit fixture');return file
    monkeypatch.setattr('spherex_explorer.acquisition.download_cutout',offline_download)
    budget.download(url,state/'raw')
    assert budget.snapshot()['attempts'][0]['localPath']=='raw/fixture.fits'
    assert not (state/'acquisition_ledger.part').exists()
    with pytest.raises(ValueError,match='exhausted'):budget.download(url,state/'raw')


def test_restart_preserves_interrupted_attempts_and_recovers_jobs(tmp_path):
    state=tmp_path/'persistent';workspace=state/'workspace';workspace.mkdir(parents=True)
    atomic_json(workspace/'acquisition_ledger.json',{'limit':12,'wiseReservation':0,'attempts':[{'status':'running'}]})
    store=Store(state/'control.sqlite');store.start(JOB)
    service=Application(Settings(state,CODE))
    try:
        assert service.store.job(JOB)['status']=='error'
        ledger=json.loads((workspace/'acquisition_ledger.json').read_text())
        assert len(ledger['attempts'])==1 and ledger['attempts'][0]['status']=='interrupted'
    finally:service.close()
