"""Synthetic FITS tests, with explicit units, missing metadata, and strict JSON."""

import json

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
import pytest

from spherex_explorer.fits_utils import (
    assess_spectral_pairs, display_mask, inspect_fits, validate_fits, write_manifest,
)
from spherex_explorer.visualization import plot_overview


def synthetic_fits(path, metadata=True):
    spatial = WCS(naxis=2)
    spatial.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    spatial.wcs.crpix = [3, 3]
    spatial.wcs.crval = [210.80227, 54.34895]
    spatial.wcs.cdelt = [-0.001, 0.001]
    header = spatial.to_header()
    # A linear alternate spectral WCS isolates key='W' and unit conversion.
    # The real integration additionally exercises SPHEREx's WCS-WAVE lookup table.
    spectral = WCS(naxis=2)
    spectral.wcs.ctype = ["WAVE", "LINEAR"]
    spectral.wcs.cunit = ["um", "um"]
    spectral.wcs.crpix = [3, 3]
    spectral.wcs.crval = [1.3, 0.03]
    spectral.wcs.cdelt = [0.001, 0.0001]
    header.update(spectral.to_header(key="W"))
    primary = fits.PrimaryHDU()
    if metadata:
        header.update({"OBSID": "synthetic-observation", "DETECTOR": 2, "BUNIT": "MJy / sr",
                       "DATE-OBS": "2025-05-01T00:00:00", "MJD-OBS": 60796.0})
        primary.header["VERSION"] = "synthetic-v1"
    header["DATE"] = "2026-11-14T00:00:00"
    image = np.arange(25, dtype=float).reshape(5, 5)
    image[0, 0] = np.nan
    flags = fits.ImageHDU(np.zeros((5, 5), dtype=np.int32), name="FLAGS")
    flags.header["MSKN0006"] = "NONFUNC"
    flags.header["MSKD0006"] = "Permanently unusable"
    flags.header["MSKN0021"] = "SOURCE"
    flags.data[1, 1] = 1 << 6
    flags.data[2, 2] = 1 << 21
    fits.HDUList([primary, fits.ImageHDU(image, header=header, name="IMAGE"), flags,
                  fits.ImageHDU(np.ones((5, 5)), name="VARIANCE"),
                  fits.ImageHDU(np.zeros((5, 5)), name="ZODI")]).writeto(path)


def test_read_synthetic_fits_and_spectral_units(tmp_path):
    path = tmp_path / "synthetic.fits"
    synthetic_fits(path)
    result = inspect_fits(path, 210.80227, 54.34895)
    assert result["observation_id"] == "synthetic-observation"
    assert result["processing_version"] == "synthetic-v1"
    assert result["image_shape"] == [5, 5]
    assert result["effective_wavelength_um"] == pytest.approx(1.3)
    assert result["spectral_bandwidth_um"] == pytest.approx(0.03)
    assert result["finite_pixel_fraction"] == pytest.approx(24 / 25)
    assert result["display_valid_pixel_fraction"] == pytest.approx(23 / 25)
    assert result["target_pixel"] == pytest.approx([2, 2])
    assert result["missing_extensions"] == ["EPSF", "WCS-WAVE"]
    assert result["quality_flags"]["definitions"][0]["pixel_count"] == 1


def test_missing_metadata_remain_null_and_date_is_not_observation_date(tmp_path):
    path = tmp_path / "missing.fits"
    synthetic_fits(path, metadata=False)
    result = inspect_fits(path, 210.80227, 54.34895)
    for key in ("observation_id", "processing_version", "detector", "image_units",
                "observation_timestamp", "observation_mjd"):
        assert result[key] is None
    assert any("Missing FITS metadata" in error for error in result["errors"])


def test_wave_tab_uses_lookup_table_and_cutout_pixel_offsets(tmp_path):
    path = tmp_path / "lookup.fits"
    synthetic_fits(path)
    with fits.open(path, mode="update") as hdus:
        header = hdus["IMAGE"].header
        for axis, offset in ((1, -9), (2, -19)):
            header[f"CTYPE{axis}W"] = "WAVE-TAB"
            header[f"CUNIT{axis}W"] = "um"
            header[f"CRPIX{axis}W"] = offset
            header[f"CRVAL{axis}W"] = 1
            header[f"CDELT{axis}W"] = 1
            header[f"PS{axis}_0W"] = "WCS-WAVE"
            header[f"PS{axis}_1W"] = "VALUES"
            header[f"PS{axis}_2W"] = "X" if axis == 1 else "Y"
            header[f"PV{axis}_3W"] = axis
        grid = np.array([1, 25], dtype=np.int32)
        x, y = np.meshgrid(grid, grid)
        values = np.stack([1.2 + 0.001 * x + 0.002 * y,
                           0.03 + 0.00001 * x + 0.00002 * y], axis=-1)
        table = fits.BinTableHDU.from_columns([
            fits.Column(name="X", format="2J", dim="(2)", array=[grid]),
            fits.Column(name="Y", format="2J", dim="(2)", array=[grid]),
            fits.Column(name="VALUES", format="8D", dim="(2,2,2)", array=[values]),
        ], name="WCS-WAVE")
        hdus.append(table)
    result = inspect_fits(path, 210.80227, 54.34895)
    assert result["effective_wavelength_um"] == pytest.approx(1.259)
    assert result["spectral_bandwidth_um"] == pytest.approx(0.03059)
    assert not result["errors"]


def test_missing_wcs_is_explicit(tmp_path):
    path = tmp_path / "no-wcs.fits"
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((4, 4)), name="IMAGE")]).writeto(path)
    result = inspect_fits(path, 0, 0)
    assert result["spatial_wcs"] is None
    assert result["effective_wavelength_um"] is None
    assert any("no celestial WCS" in message for message in result["errors"])


def test_target_outside_cutout_is_rejected(tmp_path):
    path = tmp_path / "outside.fits"
    synthetic_fits(path)
    result = inspect_fits(path, 211, 54)
    assert result["effective_wavelength_um"] is None
    assert any("outside" in error for error in result["errors"])


def test_strict_manifest_serialization(tmp_path):
    path = tmp_path / "observations.json"
    write_manifest(path, {"value": np.float32(1.5), "missing": None, "nan": np.nan,
                          "infinite": np.inf, "path": tmp_path, "array": np.array([1, 2])})
    result = json.loads(path.read_text())
    assert result["value"] == 1.5
    assert result["nan"] is None and result["infinite"] is None
    assert result["array"] == [1, 2]
    assert not path.with_suffix(".json.part").exists()


def observation(mjd, wave, bandwidth=0.03):
    return {"observation_id": str(mjd), "mjd": mjd, "timestamp": f"2025-05-{int(mjd):02d}T00:00:00",
            "inspection": {"effective_wavelength_um": wave, "spectral_bandwidth_um": bandwidth}}


def test_pair_screening_requires_distinct_dates_and_local_bandwidth():
    records = [observation(1, 1.3), observation(10, 1.31), observation(20, 1.6)]
    result = assess_spectral_pairs(records)
    assert result["similar_pair_count"] == 1
    pair = result["widest_temporal_candidate"]
    assert pair["time_separation_days"] == 9
    assert pair["wavelength_separation_um"] == pytest.approx(0.01)
    assert result["scientifically_comparable"] is None
    assert assess_spectral_pairs([observation(1, None), observation(2, 1.3)])["similar_pair_count"] == 0
    assert assess_spectral_pairs([observation(1, 1.3), observation(1, 1.3)])["similar_pair_count"] == 0


def test_source_flag_is_retained(tmp_path):
    path = tmp_path / "flags.fits"
    synthetic_fits(path)
    with fits.open(path) as hdus:
        mask = display_mask(hdus)
    assert mask[0, 0] and mask[1, 1]
    assert not mask[2, 2]


def test_missing_image_is_invalid(tmp_path):
    path = tmp_path / "empty.fits"
    fits.PrimaryHDU().writeto(path)
    with pytest.raises(ValueError, match="no IMAGE"):
        validate_fits(path)


def test_overview_handles_nan_flags_and_missing_wavelength(tmp_path):
    path = tmp_path / "image.fits"
    synthetic_fits(path)
    record = {**observation(1, None), "local_path": str(path), "release": "dr1", "detector": 2}
    output = tmp_path / "overview.png"
    plot_overview([record], output)
    assert output.read_bytes().startswith(b"\x89PNG")
    with pytest.raises(ValueError, match="No downloaded"):
        plot_overview([], output)
