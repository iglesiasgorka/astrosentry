"""Offline bounded dynamic-preparation and API-contract tests."""
import json
from pathlib import Path
from types import SimpleNamespace
import threading

from astropy.io import fits
from astropy.time import Time
import numpy as np
import pytest

from spherex_explorer.acquisition import AcquisitionBudget
from spherex_explorer.dynamic import parameters, search_key, export_aligned_sequence, local_search
from spherex_explorer.alignment import common_grid
from spherex_explorer.local_api import Service


def test_dynamic_parameters_and_fov_are_bounded():
    p=parameters({'ra':0,'dec':-90,'size':.05,'detector':6})
    assert p.size==.05 and p.bandpass=='SPHEREx-D6'
    for field,value in [('ra',360),('dec',91),('size',.21),('size',float('nan')),('detector',1.5),('detector',float('inf')),('ra',True)]:
        record={'ra':1,'dec':2,'size':.1,'detector':2};record[field]=value
        with pytest.raises(ValueError):parameters(record)
    assert search_key(p)==search_key(p)


def test_acquisition_counts_failures_and_reserves_eight_wise_attempts(tmp_path,monkeypatch):
    path=tmp_path/'outputs/spx006/acquisition_ledger.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'limit':24,'wiseReservation':8,'attempts':[]}))
    def failed(*args,**kwargs):
        assert kwargs['attempts']==1
        raise RuntimeError('Controlled HTTP 503')
    monkeypatch.setattr('spherex_explorer.acquisition.download_cutout',failed)
    budget=AcquisitionBudget(tmp_path)
    url='https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/test/level2_2025W01_1A_0001_1D6_spx_l2b-v1.fits?center=1,2d&size=0.1'
    for _ in range(16):
        with pytest.raises(RuntimeError):budget.download(url,tmp_path/'data/raw/spx006')
    with pytest.raises(ValueError):budget.download(url,tmp_path/'data/raw/spx006')
    assert len(budget.snapshot()['attempts'])==16
    for _ in range(8):
        with pytest.raises(RuntimeError):budget.download(url,tmp_path/'data/raw/spx006',purpose='wise0855')
    with pytest.raises(ValueError):budget.download(url,tmp_path/'data/raw/spx006',purpose='wise0855')
    assert len(budget.snapshot()['attempts'])==24
    assert all(r['status']=='failed' for r in budget.snapshot()['attempts'])


def test_exported_dynamic_sequence_keeps_fixed_wcs_common_cuts_and_null_motion(tmp_path):
    wcs,shape=common_grid(20,30,.05,6.2);items=[];records=[]
    for index in range(2):
        source=tmp_path/f'fixture{index}.fits';fits.PrimaryHDU(np.ones(shape)).writeto(source)
        obs=SimpleNamespace(observation_id=f'fixture{index}',midpoint=Time(60000+index*100,format='mjd'),
            path=source,header={'BUNIT':'MJy/sr'},spectral_at=lambda p:{'wavelength_um':4.43,'bandwidth_um':.04},quality_at=lambda p:{'science_valid_fraction':1})
        image=np.arange(np.prod(shape),dtype=float).reshape(shape)+index
        items.append(SimpleNamespace(observation=obs,wcs=wcs,image=image,display_image=image,display_coverage=np.ones(shape,bool),coverage=np.ones(shape,bool)))
        records.append({'detector':6,'release':'dr1','processing_version':'test-only','url':'https://example.invalid/offline-fixture'})
    target=export_aligned_sequence(items,records,tmp_path/'web','dynamic/test','region_test','Offline unit fixture')
    assert target['sequence']['motion'] is None and target['classification']=='diagnostic'
    assert len(target['sequence']['frames'])==2
    assert target['sequence']['groups'][0]['comparison']
    headers=[]
    for frame in target['sequence']['frames']:
        assert frame['expectedPosition'] is None and frame['measuredPosition'] is None
        assert frame['display']==target['display']
        p=tmp_path/'web'/frame['assets']['fits'];headers.append(fits.getheader(p));assert fits.getdata(p).shape==shape
    assert headers[0]['CRVAL1']==headers[1]['CRVAL1']==20
    assert headers[0]['DATAMIN']==headers[1]['DATAMIN']


def test_preparation_requires_cached_search_and_rejects_arbitrary_urls(tmp_path):
    service=Service(tmp_path)
    try:
        with pytest.raises(ValueError):service.prepare('https://arbitrary.invalid',4)
        with pytest.raises(ValueError):service.prepare('a'*20,4)
        with pytest.raises(ValueError):service.prepare('a'*20,10)
    finally:service.executor.shutdown()


def test_local_coverage_is_explicitly_incomplete_and_honors_the_requested_fov(tmp_path):
    grid,shape=common_grid(20,30,.1,6.2)
    raw=tmp_path/'data/raw/test.fits';raw.parent.mkdir(parents=True)
    header=grid.to_header();header['OBSID']='offline-coverage';header['DETECTOR']=6
    fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(np.ones(shape),header,name='IMAGE')]).writeto(raw)
    record={'observation_id':'offline-coverage','detector':6,'local_path':'data/raw/test.fits','release':'dr1',
        'processing_version':'test-only','artifact_uri':'ibe/data/spherex/dr1/level2/test.fits',
        'url':'https://example.invalid/offline-fixture','mjd':60000,'timestamp':'2023-02-25T00:00:00'}
    manifest=tmp_path/'outputs/observations.json';manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'observations':[record]}))
    # The query needs headers/coverage; a full scientific read is tested separately.
    from unittest.mock import patch
    with patch('spherex_explorer.dynamic.Observation.read',return_value=SimpleNamespace(spectral_at=lambda p:{'wavelength_um':4.43,'bandwidth_um':.04})):
        small=local_search(tmp_path,parameters({'ra':20,'dec':30,'size':.05,'detector':6}))
        large=local_search(tmp_path,parameters({'ra':20,'dec':30,'size':.2,'detector':6}))
        empty=local_search(tmp_path,parameters({'ra':40,'dec':30,'size':.05,'detector':6}))
    assert small['count']==1 and small['completeArchiveSearch'] is False
    assert small['records'][0]['cachedRequestedRegionCovered'] is True
    assert large['records'][0]['cachedRequestedRegionCovered'] is False
    assert empty['count']==0 and 'not a complete' in empty['source']
    assert 'cached_local_path' not in small['observations'][0]


@pytest.fixture
def local_http(tmp_path):
    service=Service(tmp_path)
    try:yield service,service
    finally:service.executor.shutdown()


def api_request(service,path,body=None,origin='http://127.0.0.1:5173',host=None):
    """Exercise the actual HTTP parser/handler through in-memory streams, no sockets."""
    from io import BytesIO
    from spherex_explorer.local_api import handler
    payload=json.dumps(body).encode() if body is not None else b''
    method='POST' if body is not None else 'GET'
    headers=f'{method} {path} HTTP/1.0\r\nHost: {host or "127.0.0.1:8765"}\r\nOrigin: {origin}\r\nContent-Length: {len(payload)}\r\n\r\n'
    output=BytesIO()
    class Connection:
        def makefile(self,*args):return BytesIO(headers.encode()+payload)
        def sendall(self,data):output.write(data)
    handler(service,{'http://127.0.0.1:5173'})(Connection(),('127.0.0.1',1),None)
    response,value=output.getvalue().split(b'\r\n\r\n',1)
    return int(response.split()[1]),json.loads(value)


def test_http_api_rejects_wrong_origins_hosts_invalid_numbers_and_user_urls(local_http):
    port,service=local_http
    assert api_request(port,'/api/health',origin='https://untrusted.invalid')[0]==403
    assert api_request(port,'/api/health',host='untrusted.invalid')[0]==403
    assert api_request(port,'/api/search',{'ra':20,'dec':30,'detector':float('inf')})[0]==400
    assert api_request(port,'/api/prepare',{'searchId':'https://untrusted.invalid','count':4})[0]==400
    assert api_request(port,'/api/prepare',{'searchId':'a'*20,'count':2.0})[0]==400
    assert api_request(port,'/api/health')[1]['attemptsUsed']==0


def test_http_api_distinguishes_real_empty_metadata_from_failure_without_private_paths(local_http,monkeypatch):
    port,service=local_http
    monkeypatch.setattr('spherex_explorer.local_api.search',lambda *args:{'id':'a'*20,'count':0,'records':[],'observations':[]})
    status,value=api_request(port,'/api/search',{'ra':20,'dec':30})
    assert status==200 and value['count']==0 and 'records' not in value
    def failed(*args):raise RuntimeError('/private/science/path: controlled timeout')
    monkeypatch.setattr('spherex_explorer.local_api.search',failed)
    status,value=api_request(port,'/api/search',{'ra':20,'dec':30})
    assert status==502 and 'not a no-data result' in value['error'] and '/private' not in value['error']


def test_http_asset_paths_stay_within_derivative_root_and_cancellation_is_bounded(local_http):
    port,service=local_http
    assert api_request(port,'/assets/dynamic/%2e%2e/%2e%2e/last_query_error.json')[0]==404
    assert api_request(port,'/api/jobs/invalid')[0]==404
    assert api_request(port,'/api/jobs/'+'a'*20+'/cancel',{})[1]['status']=='cancellation-requested'
    assert api_request(port,'/api/health')[1]['acquisitionLimit']==24
