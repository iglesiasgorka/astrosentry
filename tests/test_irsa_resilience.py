"""Offline transient-status/deadline and successful-cache provenance checks."""
import hashlib
import json
import os
import time

import pytest

from spherex_explorer.data_access import SearchParameters
from spherex_explorer.dynamic import search,search_key
from spherex_explorer.sia_access import query_sia_observations,SiaQueryError


def responses(monkeypatch,statuses):
    calls=[]
    class Response:
        def __init__(self,status):self.status_code=status
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,*args):yield b'controlled parser fixture'
    def get(*args,**kwargs):
        calls.append(kwargs);return Response(statuses[len(calls)-1])
    monkeypatch.setattr('spherex_explorer.sia_access.requests.get',get)
    monkeypatch.setattr('spherex_explorer.sia_access.time.sleep',lambda _:None)
    monkeypatch.setattr('spherex_explorer.sia_access.parse_sia_response',lambda *_:([],{'queryStatus':'OK'}))
    return calls


def test_transient_statuses_retry_then_parse_success_once(monkeypatch):
    calls=responses(monkeypatch,[502,503,200])
    rows,report=query_sia_observations(SearchParameters(),timeout=20)
    assert rows==[] and len(calls)==3 and report['attemptStatuses']==[502,503,200]
    assert all(c['allow_redirects'] is False for c in calls)


@pytest.mark.parametrize('statuses',[[502,504,503],[400]])
def test_errors_never_become_empty_observations(monkeypatch,statuses):
    calls=responses(monkeypatch,statuses)
    with pytest.raises(SiaQueryError,match='not a no-data result'):query_sia_observations(SearchParameters(),20)
    assert len(calls)==len(statuses)


def test_backoff_stops_inside_original_deadline(monkeypatch):
    calls=responses(monkeypatch,[502]);clock=[0.0]
    monkeypatch.setattr('spherex_explorer.sia_access.time.monotonic',lambda:clock[0])
    def get(*args,**kwargs):clock[0]+=.7;calls.append(kwargs);return type('Response',(),{'status_code':502,'__enter__':lambda s:s,'__exit__':lambda *a:None})()
    monkeypatch.setattr('spherex_explorer.sia_access.requests.get',get)
    with pytest.raises(SiaQueryError):query_sia_observations(SearchParameters(),1)
    assert len(calls)==1 and clock[0]<1


def cache(tmp_path,age):
    p=SearchParameters(10,20,.05);identifier=hashlib.sha256((search_key(p)+':sia2').encode()).hexdigest()[:20]
    path=tmp_path/'state/searches'/f'{identifier}.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'id':identifier,'count':0,'records':[],'source':'Controlled successful empty metadata fixture'}))
    os.utime(path,(time.time()-age,time.time()-age));return p,path


def test_stale_cache_is_labeled_and_failure_cooldown_does_not_refresh_its_age(tmp_path,monkeypatch):
    p,path=cache(tmp_path,25200);original=path.read_bytes();mtime=path.stat().st_mtime;calls=[]
    def fail(*args):calls.append(1);raise SiaQueryError(502,3)
    monkeypatch.setattr('spherex_explorer.dynamic.query_sia_observations',fail)
    first=search(tmp_path,p,workspace=tmp_path/'state',fresh_seconds=21600)
    second=search(tmp_path,p,workspace=tmp_path/'state',fresh_seconds=21600)
    assert first['count']==second['count']==0 and first['cache']['status']=='stale'
    assert first['cache']['archiveRetrievedAtUtc'] is None
    assert 'not a no-data result' in first['cache']['upstreamError']['message']
    assert len(calls)==1 and path.read_bytes()==original and path.stat().st_mtime==mtime


def test_fresh_cache_avoids_network_but_expired_cache_does_not_hide_failure(tmp_path,monkeypatch):
    p,path=cache(tmp_path,30)
    def fail(*args):raise SiaQueryError(504,3)
    monkeypatch.setattr('spherex_explorer.dynamic.query_sia_observations',fail)
    assert search(tmp_path,p,workspace=tmp_path/'state',fresh_seconds=21600)['cache']['status']=='fresh'
    os.utime(path,(time.time()-700000,time.time()-700000))
    with pytest.raises(SiaQueryError):search(tmp_path,p,workspace=tmp_path/'state',fresh_seconds=21600)
