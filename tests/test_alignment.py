"""Offline synthetic validation; none of these arrays are scientific outputs."""

from copy import deepcopy

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS, Sip
import numpy as np
import pytest

from spherex_explorer.alignment import common_grid, masked_reproject, align_observation, validate_grid
from spherex_explorer.observation import Observation
from spherex_explorer.astrometry import fit_centroid
from test_fits_utils import synthetic_fits


def test_grid_center_orientation_scale_and_roundtrip():
    wcs, shape = common_grid(210.80227, 54.34895, 0.1, 6.2)
    report = validate_grid(wcs, shape, SkyCoord(210.80227*u.deg, 54.34895*u.deg))
    assert shape == (59, 59)
    assert report["east_left"] and report["north_up"]
    assert report["center_error_arcsec"] < 1e-7
    assert report["x_step_arcsec"] == pytest.approx(6.2, rel=1e-7)
    assert report["y_step_arcsec"] == pytest.approx(6.2, rel=1e-7)
    assert report["maximum_roundtrip_error_pixels"] < 1e-7
    assert wcs.sip is None


@pytest.mark.parametrize("scale", [0, -1, np.nan, np.inf, 1e-6])
def test_bad_grid_scale_is_rejected(scale):
    with pytest.raises(ValueError):
        common_grid(1, 2, pixel_scale_arcsec=scale)


def rotated_grid(base, degrees=25, offset=(2, -3)):
    wcs = deepcopy(base)
    angle = np.deg2rad(degrees)
    wcs.wcs.pc = [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    wcs.wcs.crpix += np.array(offset)
    a = np.zeros((3, 3)); b = np.zeros((3, 3))
    a[2, 0] = 8e-5; b[0, 2] = -7e-5
    wcs.sip = Sip(a, b, None, None, wcs.wcs.crpix)
    wcs.wcs.ctype = ["RA---TAN-SIP", "DEC--TAN-SIP"]
    return wcs


def sky_sources(native, output, shape, positions):
    yy, xx = np.indices(shape)
    array = np.ones(shape)
    for x, y in positions:
        nx, ny = native.world_to_pixel(output.pixel_to_world(x, y))
        array += 40*np.exp(-((xx-nx)**2+(yy-ny)**2)/(2*1.3**2))
    return array


def centroid_near(array, x, y):
    x0, y0 = round(x), round(y)
    section = array[y0-3:y0+4, x0-3:x0+4]-1
    yy, xx = np.indices(section.shape)
    return ((xx*section).sum()/section.sum()+x0-3, (yy*section).sum()/section.sum()+y0-3)


def test_rotated_translated_sip_sources_keep_celestial_coordinates():
    output, shape = common_grid(210, 54, 0.1, 6.2)
    native = rotated_grid(output)
    positions = [(17, 18), (40, 16), (19, 41), (39, 40)]
    array = sky_sources(native, output, shape, positions)
    result, footprint, support, coverage = masked_reproject(array, ~np.isfinite(array), native, output, shape)
    for x, y in positions:
        xc, yc = centroid_near(result, x, y)
        assert np.hypot(xc-x, yc-y) < 0.08
        assert output.pixel_to_world(xc,yc).separation(output.pixel_to_world(x,y)).arcsec < 0.5
    assert native.sip is not None
    assert not coverage[0,0]
    assert (footprint == 0).any()


def test_bad_pixels_and_nan_never_leak_through_interpolation():
    output, shape = common_grid(10, 20, 0.03, 6.2)
    native = deepcopy(output)
    native.wcs.crpix += [0.35, 0.2]
    array = np.ones(shape)
    bad = np.zeros(shape, dtype=bool)
    array[7,7] = 1e12; bad[7,7] = True
    array[8,8] = np.nan
    result, footprint, support, coverage = masked_reproject(array, bad, native, output, shape)
    assert np.nanmax(result) == pytest.approx(1)
    assert np.nanmin(result) == pytest.approx(1)
    assert np.isnan(result[7,7])
    assert (support < 0.999).any()
    assert np.array_equal(np.isfinite(result), coverage)


def test_fixed_grid_does_not_erase_synthetic_source_motion():
    output, shape = common_grid(20, -20, 0.1, 6.2)
    static = [(17,17),(42,18),(20,42)]
    native_a, native_b = rotated_grid(output, -17, (-2,1)), rotated_grid(output, 32, (3,-2))
    frames=[]
    for native,moving in [(native_a,(30,29)),(native_b,(30,32))]:
        array = sky_sources(native, output, shape, static+[moving])
        frames.append(masked_reproject(array,np.zeros(shape,bool),native,output,shape)[0])
    for x,y in static:
        a=centroid_near(frames[0],x,y); b=centroid_near(frames[1],x,y)
        assert np.linalg.norm(np.array(a)-b)<0.12
    a=centroid_near(frames[0],30,29); b=centroid_near(frames[1],30,32)
    assert b[1]-a[1] == pytest.approx(3,abs=0.12)


def test_observation_distinguishes_science_and_display_masks(tmp_path):
    path=tmp_path/'fixture.fits'
    synthetic_fits(path)
    with fits.open(path,mode='update') as hdus:
        hdus['FLAGS'].header['MSKN0017']='PERSIST'
        hdus['FLAGS'].data[3,3]=1<<17
    obs=Observation.read(path,'dr1')
    assert not obs.science_invalid[2,2]  # SOURCE remains usable.
    assert obs.science_invalid[3,3] and not obs.display_invalid[3,3]
    assert obs.midpoint is None  # DATE is not substituted for missing midpoint.
    assert obs.epsf_metadata is None
    assert obs.spectral_at(SkyCoord(210.80227*u.deg,54.34895*u.deg))['wavelength_um']==pytest.approx(1.3)


def test_surface_brightness_is_preserved_and_variance_is_diagnostic(tmp_path):
    path=tmp_path/'constant.fits'
    synthetic_fits(path)
    with fits.open(path,mode='update') as hdus:
        hdus['IMAGE'].data[:]=3.5
        hdus['FLAGS'].data[:]=0
    obs=Observation.read(path,'dr1')
    grid,shape=common_grid(210.80227,54.34895,0.003,2)
    aligned=align_observation(obs,grid,shape)
    assert np.nanmedian(aligned.image)==pytest.approx(3.5)
    assert np.nanmedian(aligned.variance_diagnostic)==pytest.approx(1)


def test_centroid_is_a_fit_not_the_prediction(tmp_path):
    grid,shape=common_grid(20,30,0.1,6.2)
    yy,xx=np.indices(shape)
    image=2+20*np.exp(-((xx-29.35)**2+(yy-28.8)**2)/(2*0.8**2))
    header=grid.to_header(); header['BUNIT']='MJy / sr'; header['OBSID']='synthetic-only'
    path=tmp_path/'point.fits'
    fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(image,header=header,name='IMAGE'),
                  fits.ImageHDU(np.zeros(shape,dtype=np.int32),name='FLAGS'),
                  fits.ImageHDU(np.full(shape,0.01),name='VARIANCE')]).writeto(path)
    obs=Observation.read(path)
    fit=fit_centroid(obs,grid.pixel_to_world(29,29))
    assert fit['accepted']
    assert fit['x_original']==pytest.approx(29.35,abs=0.01)
    assert fit['y_original']==pytest.approx(28.8,abs=0.01)
    obs.science_invalid[28:31,28:31]=True
    assert not fit_centroid(obs,grid.pixel_to_world(29,29))['accepted']
