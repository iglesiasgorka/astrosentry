"""Offline selection and catalog motion tests with explicitly synthetic astrometry."""

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
import pytest

from spherex_explorer.targets import predict_position,epoch_groups,select_spectral_sequence,summarize_availability
from spherex_explorer.scientific_pipeline import initial_barnard_selection


def record(day,wave=1.3,release='dr1',quality=True):
    return {'observation_id':str(day),'mjd':60000+day,'timestamp':f'2025-01-{day+1:02d}T00:00:00',
            'wavelength_um':wave,'bandwidth_um':0.03,'release':release,'target_quality_ok':quality}


def test_linear_prediction_has_documented_epoch_and_pm_cosdec_convention():
    target={'ra_deg':20.,'dec_deg':60.,'reference_epoch_jyear':2000.,
            'pm_ra_cosdec_mas_yr':1000.,'pm_dec_mas_yr':2000.}
    initial=SkyCoord(20*u.deg,60*u.deg)
    time=Time(2010,format='jyear',scale='tcb')
    result=predict_position(target,time)
    east,north=initial.spherical_offsets_to(result)
    assert east.arcsec==pytest.approx(10,abs=0.001)
    assert north.arcsec==pytest.approx(20,abs=0.001)
    assert initial.separation(predict_position(target,Time(2000,format='jyear',scale='tcb'))).arcsec<1e-8


def test_spectral_selection_retains_three_separated_same_release_epochs():
    records=[record(0,1.3),record(5,1.305),record(10,1.31),record(15,1.6),record(20,1.3,'qr3')]
    selected=select_spectral_sequence(records)
    assert len(selected)==3
    assert all(r['release']=='dr1' for r in selected)
    assert selected[-1]['mjd']-selected[0]['mjd']==10


def test_bad_quality_and_missing_wavelength_are_not_selected():
    assert select_spectral_sequence([record(0,None),record(1,quality=False)])==[]
    assert select_spectral_sequence([])==[]
    assert initial_barnard_selection([],12)==[]
    assert summarize_availability([])['start_utc'] is None
    assert epoch_groups([])==[]


def test_selection_never_exceeds_budget_and_groups_distinct_epochs():
    records=[record(day) for day in range(20)]
    selected=initial_barnard_selection(records,12)
    assert len(selected)==12
    assert selected[0]['mjd']==60000 and selected[-1]['mjd']==60019
    assert len({r['observation_id'] for r in selected})==12
    assert len(epoch_groups(records))==20
    assert len(select_spectral_sequence(records,3))==3


def test_each_spectral_pair_must_pass_the_bandwidth_threshold():
    selected=select_spectral_sequence([record(0,1.29),record(2,1.3),record(4,1.31)])
    assert len(selected)==2
    for first in selected:
        for second in selected:
            assert abs(first['wavelength_um']-second['wavelength_um'])<=0.5*min(first['bandwidth_um'],second['bandwidth_um'])
    with pytest.raises(ValueError):
        select_spectral_sequence([],0)


def test_unknown_bandwidth_and_detector_mixing_are_rejected():
    missing=record(0)
    missing['bandwidth_um']=None
    assert select_spectral_sequence([missing])==[]
    first,second=record(0),record(5)
    first['detector']=2
    second['detector']=3
    assert len(select_spectral_sequence([first,second]))==1


def test_existing_case_budget_prevents_any_new_download(monkeypatch,tmp_path):
    from spherex_explorer.scientific_pipeline import run_barnard
    folder=tmp_path/'data/raw/spx002/barnard'
    folder.mkdir(parents=True)
    (folder/'existing.fits').write_bytes(b'Already occupies the download budget; never read by this test.')
    def forbidden(*args,**kwargs):
        raise AssertionError('A budget-exhausted run must not call the downloader.')
    monkeypatch.setattr('spherex_explorer.scientific_pipeline.download_cutout',forbidden)
    r=record(0)
    r['url']='https://irsa.ipac.caltech.edu/unique-new-cutout.fits?center=20,30d&size=0.15'
    availability={'targets':[{'key':'barnard','field_center_ra_deg':20.,'field_center_dec_deg':30.,
                             'detectors':{'SPHEREx-D2':{'observations':[r]}}}]}
    result=run_barnard(tmp_path,tmp_path/'outputs',availability,{},max_downloads=1)
    assert result['downloaded_count']==0
    assert result['status']=='no_usable_observations'
    assert 'budget is exhausted' in result['failures'][0]['error']


def test_availability_cache_is_invalidated_when_field_size_changes(monkeypatch,tmp_path):
    import json
    from astropy.table import Table
    from spherex_explorer.targets import query_target_availability
    target={'key':'synthetic','name':'Synthetic only','ra_deg':20.,'dec_deg':30.,
            'reference_epoch_jyear':2000.,'pm_ra_cosdec_mas_yr':None,'pm_dec_mas_yr':None}
    calls=[]
    def query(parameters,timeout):
        calls.append(parameters)
        return Table()
    monkeypatch.setattr('spherex_explorer.targets.query_observations',query)
    destination=tmp_path/'availability.json'
    query_target_availability([target],destination,size_deg=0.15)
    assert len(calls)==6
    query_target_availability([target],destination,size_deg=0.15)
    assert len(calls)==6
    query_target_availability([target],destination,size_deg=0.2)
    assert len(calls)==12
    result=json.loads(destination.read_text())
    assert result['targets'][0]['size_deg']==0.2
