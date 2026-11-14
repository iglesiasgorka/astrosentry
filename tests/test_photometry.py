"""Synthetic measurements are offline tests only, never web science assets."""
import numpy as np
import pytest
from astropy.wcs import WCS
from spherex_explorer.photometry import (ApertureConfig,aperture_measurement,pixel_solid_angles,
    relative_fluxes,spectral_subset,classify_variability,reference_positions)


def fixture():
    w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crval=[50,30]
    w.wcs.crpix=[26,26];w.wcs.cdelt=[-6.2/3600,6.2/3600]
    yy,xx=np.indices((51,51));source=np.exp(-((xx-25)**2+(yy-25)**2)/(.5**2*2));source/=source.sum()
    areas=pixel_solid_angles(w,source.shape)
    image=2+source*10000/(areas*1e12)
    return w,image,np.full(image.shape,.001),np.zeros(image.shape,dtype=bool),w.pixel_to_world(25,25)


def test_known_aperture_flux_and_surface_brightness_conversion():
    w,image,v,bad,position=fixture()
    r=aperture_measurement(image,v,bad,w,position,config=ApertureConfig(3,5,8))
    assert r['accepted'];assert r['fluxMicroJy']==pytest.approx(10000,rel=1e-4)
    assert r['backgroundMJySr']==pytest.approx(2);assert r['formalErrorMicroJy']>0
    assert 'not total' in r['uncertaintyKind']


def test_solid_angle_uses_angular_area_not_pixel_count():
    w,*_=fixture();area=pixel_solid_angles(w,(51,51))
    assert area[25,25]==pytest.approx((6.2*np.pi/(180*3600))**2,rel=1e-6)


def test_background_offset_and_deterministic_noise():
    w,image,v,bad,p=fixture();rng=np.random.default_rng(72)
    a=aperture_measurement(image,v,bad,w,p)
    b=aperture_measurement(image+7+rng.normal(0,.01,image.shape),v,bad,w,p)
    assert b['accepted'];assert b['fluxMicroJy']==pytest.approx(a['fluxMicroJy'],rel=.01)
    assert b['backgroundMJySr']==pytest.approx(9,abs=.01)


def test_a_displaced_bright_source_is_not_mistaken_for_the_catalog_target():
    w,image,v,bad,p=fixture()
    result=aperture_measurement(np.roll(image,2,axis=1),v,bad,w,p)
    assert result['accepted'] is False
    assert result['fluxMicroJy'] is None
    assert 'displaced' in result['reason']


@pytest.mark.parametrize('kind',['flag','nan','variance'])
def test_invalid_or_saturated_source_pixels_are_rejected(kind):
    w,image,v,bad,p=fixture()
    if kind=='flag':bad[25,25]=True
    if kind=='nan':image[25,25]=np.nan
    if kind=='variance':v[25,25]=0
    r=aperture_measurement(image,v,bad,w,p)
    assert not r['accepted'];assert r['fluxMicroJy'] is None


def test_background_mask_and_missing_variance():
    w,image,v,bad,p=fixture()
    assert not aperture_measurement(image,None,bad,w,p)['accepted']
    assert not aperture_measurement(image,v,bad,w,p,np.ones_like(bad))['accepted']
    with pytest.raises(ValueError):aperture_measurement(image,v,bad,w,p,units='Jy')
    with pytest.raises(ValueError):ApertureConfig(3,2,8)


def test_shared_reference_ratio_covariance():
    r=relative_fluxes([10,20,30],[1,2,3])
    assert r['ratios']==[1,2,3]
    assert r['formalCovariance'][1][2]==pytest.approx(.06)
    assert r['formalCovariance'][0]==[0,0,0]
    assert r['formalErrors'][1]==pytest.approx(np.sqrt(.08))
    with pytest.raises(ValueError):relative_fluxes([0],[1])


def records():
    return [{'id':str(i),'mjd':60000+i*10,'wavelengthUm':1.4+i*.001,'bandwidthUm':.04,
             'detector':'D2','release':'dr1','qualityAccepted':True,'fluxMicroJy':i*100} for i in range(4)]


def test_spectral_temporal_selection_never_ranks_by_flux():
    r=records();assert len(spectral_subset(r))==4
    r[0]['fluxMicroJy']=1e30;assert len(spectral_subset(r))==4
    r[3]['release']='qr3';assert len(spectral_subset(r))==3
    r[2]['wavelengthUm']=1.5;assert len(spectral_subset(r))==2
    r[1]['mjd']=r[0]['mjd']+.5;assert len(spectral_subset(r))==1


def test_honest_classifications():
    assert classify_variability([])=='unavailable'
    r=records();assert classify_variability(r)=='exploratory'
    for record in r:record['qualityAccepted']=False
    assert classify_variability(r)=='diagnostic'


def test_reference_selection_excludes_the_target_and_cannot_invent_peaks():
    from types import SimpleNamespace
    w,image,v,bad,p=fixture()
    observation=SimpleNamespace(image=image,science_invalid=bad,wcs=w)
    assert reference_positions(observation,p)==[]


def test_independent_reference_is_selected_from_real_test_pixels(tmp_path):
    from types import SimpleNamespace
    from astropy.io import fits
    w,image,v,bad,p=fixture();yy,xx=np.indices(image.shape)
    image+=20*np.exp(-((xx-12)**2+(yy-12)**2)/(.5**2*2))
    path=tmp_path/'synthetic.fits';header=fits.Header({'BUNIT':'MJy2 / sr2'})
    fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(v,header,name='VARIANCE')]).writeto(path)
    observation=SimpleNamespace(path=path,image=image,variance=v,science_invalid=bad,wcs=w,header={'BUNIT':'MJy/sr'},quality_metadata={'definitions':[]},quality_at=lambda position:{})
    positions=reference_positions(observation,p)
    assert len(positions)==1
    np.testing.assert_allclose(w.world_to_pixel(positions[0]),[12,12],atol=1e-6)


def test_missing_original_variance_hdu_is_an_explicit_rejection(tmp_path):
    from types import SimpleNamespace
    from astropy.io import fits
    from spherex_explorer.photometry import measure_observation
    path=tmp_path/'missing_variance.fits';fits.PrimaryHDU().writeto(path)
    observation=SimpleNamespace(path=path,header={'BUNIT':'MJy/sr'},quality_at=lambda p:{})
    result=measure_observation(observation,None)
    assert result['accepted'] is False
    assert result['fluxMicroJy'] is None
    assert 'VARIANCE units' in result['reason']
