"""Offline tests for the observed SIA2 contract, coverage and acquisition guards."""
from io import BytesIO
from pathlib import Path

from astropy.coordinates import SkyCoord
from astropy.table import Table
import pytest

from spherex_explorer.data_access import SearchParameters, download_cutout
from spherex_explorer.sia_access import parse_sia_response, polygon_contains, sia_parameters
from spherex_explorer.acquisition import AcquisitionBudget


def response(rows=None):
    url = 'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/test/level2_2025W01_1A_0001_1D2_spx_l2b-v27.fits'
    rows = rows if rows is not None else [(url,'2025W01_1A_0001_1','spherex_dr1','SPHEREx-D2',60000.,60000.01,'POLYGON ICRS 9 19 11 19 11 21 9 21')]
    table = Table(rows=rows, names=['access_url','obs_id','obs_collection','energy_bandpassname','t_min','t_max','s_region'],
                  dtype=['U300','U40','U30','U20','f8','f8','U150'])
    stream=BytesIO();table.write(stream,format='votable')
    return stream.getvalue().replace(b'<RESOURCE type="results">',b'<RESOURCE type="results"><INFO name="QUERY_STATUS" value="OK"/>')


def test_sia_contract_normalizes_identity_dates_urls_and_local_wavelength_absence():
    rows,report=parse_sia_response(response(),SearchParameters(10,20,.05))
    assert len(rows)==1 and report['rawRows']==1
    r=rows[0]
    assert r['release']=='dr1' and r['detector']==2 and r['mjd']==60000
    assert '?center=10,20&size=0.05' in r['url']
    assert r['sia']['requestedGridCoveredByMetadata'] is True
    assert 'wavelength_um' not in r


def test_sia_empty_is_real_empty_but_overflow_and_invalid_contract_are_errors():
    rows,_=parse_sia_response(response([]),SearchParameters(10,20,.05));assert rows==[]
    with pytest.raises(ValueError):parse_sia_response(response().replace(b'value="OK"',b'value="OVERFLOW"'),SearchParameters(10,20,.05))
    with pytest.raises(ValueError):parse_sia_response(response().replace(b'name="t_min"',b'name="not_t_min"'),SearchParameters(10,20,.05))
    with pytest.raises(ValueError):parse_sia_response(response(),SearchParameters(10,20,.05),maxrec=1)


def test_sia_filters_detector_and_rejects_cloud_access_or_mismatched_identity():
    assert parse_sia_response(response(),SearchParameters(10,20,.05,'SPHEREx-D6'))[0]==[]
    for altered in [response().replace(b'irsa.ipac.caltech.edu',b'evil.invalid'),response().replace(b'<TD>2025W01_1A_0001_1</TD>',b'<TD>wrong</TD>')]:
        with pytest.raises(ValueError):parse_sia_response(altered,SearchParameters(10,20,.05))


def test_polygon_coverage_handles_ra_zero_and_does_not_claim_unsupported_shapes():
    inside=SkyCoord([359.99,.01],[0,0],unit='deg')
    assert polygon_contains('POLYGON ICRS 359 -1 1 -1 1 1 359 1',inside,(0,0))
    assert polygon_contains('CIRCLE ICRS 0 0 1',inside,(0,0)) is None
    assert not polygon_contains('POLYGON ICRS 359 -1 1 -1 1 1 359 1',SkyCoord([2],[0],unit='deg'),(0,0))
    assert len([v for k,v in sia_parameters(SearchParameters()) if k=='COLLECTION'])==4


def test_cutout_rejects_credentials_redirects_and_nonfits_content(tmp_path,monkeypatch):
    url='https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/test/level2_2025W01_1A_0001_1D2_spx_v1.fits?center=10,20&size=0.05'
    with pytest.raises(ValueError):download_cutout(url.replace('https://','https://user:pass@'),tmp_path)
    class Response:
        status_code=302;headers={}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
    def get(*args,**kwargs):
        assert kwargs['allow_redirects'] is False
        return Response()
    monkeypatch.setattr('requests.get',get)
    with pytest.raises(RuntimeError,match='redirects'):download_cutout(url,tmp_path)
    Response.status_code=200;Response.headers={'Content-Type':'text/html'}
    with pytest.raises(RuntimeError,match='content type'):download_cutout(url,tmp_path)


def test_phase_budget_is_separate_and_enforces_twelve_attempts(tmp_path,monkeypatch):
    def fail(*args,**kwargs):raise RuntimeError('Controlled failure')
    monkeypatch.setattr('spherex_explorer.acquisition.download_cutout',fail)
    budget=AcquisitionBudget(tmp_path,tmp_path/'outputs/spx007b/acquisition_ledger.json',12,0)
    url='https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/test/level2_2025W01_1A_0001_1D2_spx_v1.fits?center=10,20&size=0.05'
    for _ in range(12):
        with pytest.raises(RuntimeError):budget.download(url,tmp_path/'outputs/spx007b/raw')
    with pytest.raises(ValueError,match='exhausted'):budget.download(url,tmp_path/'outputs/spx007b/raw')
    assert len(budget.snapshot()['attempts'])==12
    assert not (tmp_path/'outputs/spx006').exists()


def test_successful_sia_cache_keeps_canonical_cutout_urls_for_the_worker(tmp_path):
    import hashlib,json
    from spherex_explorer.dynamic import search,search_key
    p=SearchParameters(10,20,.05)
    identifier=hashlib.sha256((search_key(p)+':sia2').encode()).hexdigest()[:20]
    path=tmp_path/'outputs/spx007b/searches'/f'{identifier}.json';path.parent.mkdir(parents=True)
    url='https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/test/level2_2025W01_1A_0001_1D2_spx_v1.fits'
    path.write_text(json.dumps({'records':[{'url':url+'?center=10%2C20&size=0.05','sia':{'access_url':url}}]}))
    result=search(tmp_path,p)
    assert result['records'][0]['url']==url+'?center=10,20&size=0.05'
    assert json.loads(path.read_text())==result
