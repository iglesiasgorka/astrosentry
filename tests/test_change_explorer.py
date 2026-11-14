"""Offline synthetic tests; no fake observations enter prepared web assets."""
import base64
from copy import deepcopy
import json
from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS
from astropy.time import Time
from types import SimpleNamespace
import numpy as np
from PIL import Image
import pytest

from spherex_explorer.change_explorer import (assign_visit_ids, compatible_pair,
    signed_difference, export_difference, _export_frame, include_change_targets, inventory)


def test_inventory_checks_files_and_deduplicates_versions_without_inventing_quality(tmp_path, monkeypatch):
    manifests = ['outputs/observations.json', 'outputs/spx002/barnard/observations.json',
        'outputs/spx002b/epsilon_indi_b/observations.json',
        'outputs/spx004a/r_dra/preparation/observations.json',
        'outputs/spx004a/rw_aur/preparation/observations.json']
    raw = tmp_path/'data/raw';raw.mkdir(parents=True)
    records = []
    for name in ['a', 'b', 'unknown']:
        (raw/f'{name}.fits').write_bytes(b'offline inventory fixture')
        if name != 'unknown':
            records.append({'local_path': f'data/raw/{name}.fits', 'observation_id': 'one-observation',
                'release': 'dr1', 'detector': 6, 'processing_version': name,
                'inspection': {'effective_wavelength_um': 4.43, 'spectral_bandwidth_um': .036}})
    for index, relative in enumerate(manifests):
        path = tmp_path/relative;path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'observations': records if index == 0 else []}))
    monkeypatch.setattr('spherex_explorer.change_explorer.Observation.read', lambda path, release:
        SimpleNamespace(observation_id='one-observation', midpoint=Time(60000, format='mjd'),
            image=np.ones((2,2)), science_invalid=np.array([[True,False],[False,False]])))
    result = inventory(tmp_path)
    assert result['originalFitsCount'] == 3 and result['validOriginalFitsCount'] == 2
    assert result['uniqueObservationDetectorCount'] == 1
    accepted = [record for record in result['records'] if record['validFits']]
    assert len({record['visitId'] for record in accepted}) == 1
    assert all(record['sourceQuality'] is None and record['registeredAsset'] is None for record in accepted)
    assert all(record['wavelengthUm'] == 4.43 and record['originalScienceValidFraction'] == .75 for record in accepted)
    rejected = next(record for record in result['records'] if not record['validFits'])
    assert 'not represented' in rejected['error']


def grid():
    w = WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crval=[20,30]
    w.wcs.crpix=[16.5,16.5];w.wcs.cdelt=[-6.2/3600,6.2/3600]
    return w


def metadata(identifier='a',mjd=60000,wavelength=4.43):
    return {'observation_id':identifier,'midpoint_mjd':mjd,'midpoint_utc':'2023-02-25T00:00:00' if identifier=='a' else '2023-03-07T00:00:00',
            'detector':6,'release':'dr1','wavelength_um':wavelength,'bandwidth_um':.036,'processing_version':'synthetic-test',
            'aligned_asset':f'aligned/{identifier}.fits','url':'https://example.invalid/synthetic-unit-test'}


def test_signed_difference_recovers_brightness_change():
    a=np.zeros((32,32));b=a.copy();a[16,16]=2;b[16,16]=5
    result,valid=signed_difference(a,b,np.ones(a.shape,bool),np.ones(a.shape,bool),grid(),grid(),'MJy/sr','MJy/sr')
    assert result[16,16]==3;assert result.sum()==3;assert valid.all()


def test_synthetic_translation_has_signed_lobes_without_detection_claim():
    yy,xx=np.indices((32,32));a=np.exp(-((xx-14)**2+(yy-16)**2)/2)
    b=np.roll(a,1,axis=1)
    residual,_=signed_difference(a,b,np.ones(a.shape,bool),np.ones(a.shape,bool),grid(),grid(),'MJy/sr','MJy/sr')
    assert residual[16,14]<0;assert residual[16,16]>0
    assert residual.sum()==pytest.approx(0,abs=1e-12)


def test_intersection_masks_and_nonfinite_pixels_are_not_filled():
    a=np.ones((4,4));b=a*2;ma=np.ones((4,4),bool);mb=ma.copy()
    ma[0,0]=False;mb[1,1]=False;b[2,2]=np.nan
    residual,valid=signed_difference(a,b,ma,mb,grid(),grid(),'MJy/sr','MJy/sr')
    assert valid.sum()==13
    assert np.isnan(residual[0,0]) and np.isnan(residual[1,1]) and np.isnan(residual[2,2])
    np.testing.assert_array_equal(residual[valid],1)


@pytest.mark.parametrize('mismatch',['shape','mask','wcs','units','missingunits','nomask'])
def test_incompatible_scientific_inputs_are_rejected(mismatch):
    a=np.ones((4,4));b=a.copy();ma=np.ones((4,4),bool);mb=ma.copy();wa=grid();wb=grid();unit='MJy/sr'
    if mismatch=='shape':b=b[:3]
    if mismatch=='mask':mb=mb[:3]
    if mismatch=='wcs':wb.wcs.crval[0]+=.001
    if mismatch=='units':unit='Jy'
    if mismatch=='missingunits':unit=None
    if mismatch=='nomask':mb[:]=False
    with pytest.raises(ValueError):signed_difference(a,b,ma,mb,wa,wb,'MJy/sr',unit)


def test_equivalent_surface_brightness_units_are_converted_explicitly():
    a=np.ones((4,4));valid=np.ones_like(a,bool)
    residual,_=signed_difference(a,a*2e6,valid,valid,grid(),grid(),'MJy/sr','Jy/sr')
    np.testing.assert_allclose(residual,1)


def test_preliminary_spectral_filter_and_same_detector_release_are_required():
    a,b=metadata(),metadata('b',60010,4.44)
    assert compatible_pair(a,b)['timeSeparationDays']==10
    for field,value in [('detector',2),('release','qr3'),('wavelength_um',4.7),('bandwidth_um',None),('midpoint_mjd',60000.1)]:
        changed=deepcopy(b);changed[field]=value
        with pytest.raises(ValueError):compatible_pair(a,changed)


def test_chronological_visits_do_not_count_subexposures_as_epochs():
    records=[metadata('c',60002),metadata('b',60000.5),metadata('a',60000)]
    visits=assign_visit_ids(records,'test')
    assert visits['a']==visits['b'];assert visits['c']!=visits['a']
    assert len(set(visits.values()))==2


def aligned(path,values,valid):
    header=grid().to_header();header['BUNIT']='MJy/sr'
    fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(values,header,name='IMAGE'),fits.ImageHDU(values,header,name='DISPLAY'),
                  fits.ImageHDU(valid.astype(np.uint8),name='COVERAGE')]).writeto(path)


def test_difference_export_preserves_scientific_values_zero_center_and_wcs(tmp_path):
    a=np.ones((32,32))*.3;b=a.copy();b[16,16]+=.2;b[12,12]-=.1
    mask=np.ones(a.shape,bool);mask[0,0]=False
    pa,pb=tmp_path/'a.fits',tmp_path/'b.fits';aligned(pa,a,mask);aligned(pb,b,mask)
    result=export_difference(tmp_path/'web',tmp_path/'private',pa,pb,metadata(),metadata('b',60010,4.44))
    assert result['classification']=='exploratory';assert result['uncertainty'] is None
    assert result['display']['vmin']==-result['display']['vmax']
    assert result['display']['colors'][1]=='#f7f7f7'
    assert result['normalization'].startswith('None')
    data=fits.getdata(tmp_path/'private/difference.fits');np.testing.assert_allclose(data[mask],(b-a)[mask])
    assert np.isnan(data[0,0]);assert fits.getheader(tmp_path/'private/difference.fits')['BUNIT']=='MJy/sr'
    np.testing.assert_allclose(WCS(fits.getheader(tmp_path/'private/difference.fits')).wcs.crval,[20,30])
    packed=json.loads((tmp_path/'web'/result['assets']['mask']).read_text())
    recovered=np.unpackbits(np.frombuffer(base64.b64decode(packed['valid']),dtype=np.uint8),bitorder='little')[:mask.size].reshape(mask.shape)
    np.testing.assert_array_equal(recovered,mask)


def test_missing_positions_stay_null_and_display_is_not_science_mask(tmp_path):
    w=grid();values=np.arange(16,dtype=float).reshape(4,4);values[0,0]=np.nan
    valid=np.ones((4,4),bool);valid[2,2]=False
    h=w.to_header();h['BUNIT']='MJy/sr'
    record=metadata();record['target_centroid']={}
    cuts={'vmin':0,'vmax':15,'stretch':'asinh','common':True}
    frame=_export_frame(tmp_path,{'id':'epsilon_indi_b'},record,{'display':values,'image':values,'valid':valid,'wcs':w,'header':h},cuts)
    assert frame['expectedPosition'] is None and frame['measuredPosition'] is None
    assert frame['display']==cuts
    with Image.open(tmp_path/frame['assets']['png']) as image:
        assert image.size==(4,4)
        assert image.getpixel((0,3))[:3]==(104,58,104)


def test_absent_optional_extension_and_traversal_are_honest(tmp_path):
    catalog={'targets':[{'id':'epsilon_indi_b'}]}
    assert include_change_targets(tmp_path,tmp_path/'web',catalog)==catalog
    root=tmp_path/'outputs/spx004b';root.mkdir(parents=True)
    (root/'extension.json').write_text(json.dumps({'targets':[{'id':'epsilon_indi_b','sequence':{'frames':[{'assets':{'fits':'../private.fits'}}],'differences':[]}}]}))
    with pytest.raises(ValueError):include_change_targets(tmp_path,tmp_path/'web',catalog)
