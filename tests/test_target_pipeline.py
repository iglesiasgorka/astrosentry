"""Offline generic-target integration with explicitly synthetic FITS fixtures."""

import hashlib
import json
from pathlib import Path
import shutil

from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
import numpy as np
from PIL import Image
import pytest

from spherex_explorer.alignment import common_grid
from spherex_explorer.scientific_pipeline import run_target, run_barnard, initial_target_selection, initial_barnard_selection
from spherex_explorer.sequence_manifest import relative_asset
from spherex_explorer.targets import select_spectral_sequence


def target_model(key):
    return {"key": key, "name": "Synthetic " + key, "main_id": key,
            "ra_deg": 20., "dec_deg": 30., "reference_epoch_jyear": 2000.,
            "pm_ra_cosdec_mas_yr": 0., "pm_dec_mas_yr": 0., "parallax_mas": None}


def observation_record(number, detector=2):
    mjd = 60700. + number * 3
    return {"observation_id": f"synthetic_{number}", "detector": detector, "release": "dr1",
            "url": f"https://irsa.ipac.caltech.edu/synthetic_{number}D{detector}.fits?center=20,30d&size=0.1",
            "mjd": mjd, "timestamp": Time(mjd, format="mjd").isot, "processing_version": "synthetic-only"}


def cached_entry(key, records):
    return {"key": key, "field_center_ra_deg": 20., "field_center_dec_deg": 30., "size_deg": 0.1,
            "astrometry": {"main_id": key}, "detectors": {"SPHEREx-D2": {"observations": records}}}


def synthetic_point(path, record):
    grid, shape = common_grid(20, 30, 0.1, 6.2)
    header = grid.to_header()
    header["BUNIT"] = "MJy / sr"
    header["OBSID"] = record["observation_id"]
    header["DETECTOR"] = record["detector"]
    header["MJD-OBS"] = record["mjd"]
    header["MJD-AVG"] = record["mjd"] + 0.0005
    header["TIMESYS"] = "UTC"
    spectral = WCS(naxis=2)
    spectral.wcs.ctype = ["WAVE", "LINEAR"]
    spectral.wcs.cunit = ["um", "um"]
    spectral.wcs.crpix = [30, 30]
    spectral.wcs.crval = [1.3, 0.03]
    spectral.wcs.cdelt = [1e-8, 1e-8]
    header.update(spectral.to_header(key="W"))
    yy, xx = np.indices(shape)
    data = 2 + 20*np.exp(-((xx-29.25)**2+(yy-28.9)**2)/(2*0.8**2))
    flags = fits.ImageHDU(np.full(shape, 1 << 21, dtype=np.int32), name="FLAGS")
    flags.header["MSKN0021"] = "SOURCE"
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(data, header=header, name="IMAGE"), flags,
                  fits.ImageHDU(np.full(shape, 0.01), name="VARIANCE")]).writeto(path)


@pytest.fixture
def fake_renderers(monkeypatch):
    """Scientific/manifest code remains real; skip redundant large diagnostic charts."""
    for name in ("plot_aligned_overview", "write_blink", "plot_motion"):
        monkeypatch.setattr("spherex_explorer.scientific_pipeline." + name, lambda *a, **k: None)


def test_generic_pipeline_selects_correct_target_and_portable_assets(monkeypatch, tmp_path, fake_renderers):
    key = "epsilon_indi_b"
    records = [observation_record(0), observation_record(1)]
    sources = {}
    for record in records:
        path = tmp_path / (record["observation_id"] + ".fits")
        synthetic_point(path, record)
        sources[record["url"]] = path
    calls = []
    other_cache=tmp_path/'data/raw/spx002b/barnard'
    other_cache.mkdir(parents=True)
    for number in range(3):
        (other_cache/f'other_{number}.fits').write_bytes(b'Other target budget fixture, never inspected.')
    def download(url, directory, **kwargs):
        calls.append((url, directory))
        assert url in sources  # A Barnard row would fail here.
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".fits")
        shutil.copyfile(sources[url], path)
        return path
    monkeypatch.setattr("spherex_explorer.scientific_pipeline.download_cutout", download)
    availability = {"targets": [cached_entry("barnard", [observation_record(99)]), cached_entry(key, records)]}
    output = tmp_path / "outputs/spx002b" / key
    result = run_target(tmp_path, output, availability, target_model(key), max_downloads=2,
                        total_download_budget=2, size_deg=0.1)
    assert result["target_key"] == key
    assert len(calls) == 2
    assert all(directory == tmp_path / "data/raw/spx002b" / key for _, directory in calls)
    manifest = json.loads((output / "sequence_manifest.json").read_text())
    assert manifest["target_id"] == key
    assert manifest["sequence_classification"] == "exploratory"
    assert len(manifest["frames"]) == 2
    assert all(frame["measured_position"] is not None for frame in manifest["frames"])
    assert not any(str(tmp_path) in str(value) for value in manifest.values())
    for frame in manifest["frames"]:
        for asset in frame["assets"].values():
            assert relative_asset(asset) == asset
            assert (output / asset).exists()
        with Image.open(output / frame["assets"]["image"]) as image:
            assert image.size == (59, 59)
        expected = frame["expected_position"]
        assert expected["y_image"] == pytest.approx(58-expected["y_fits"])
    # A local rerun reuses the actual processed pool, without a new download.
    again = run_target(tmp_path, output, availability, target_model(key), max_downloads=2,
                       total_download_budget=2, size_deg=0.1, local_only=True)
    assert again["downloaded_count"] == 2 and len(calls) == 2
    # Output-scale changes require fresh overlay coordinates even for cached FITS.
    run_target(tmp_path, output, availability, target_model(key), max_downloads=2,
               total_download_budget=2, size_deg=0.1, pixel_scale_arcsec=3.1, local_only=True)
    scaled=json.loads((output/"sequence_manifest.json").read_text())
    assert scaled["image_dimensions"] == {"width":117,"height":117}
    assert scaled["frames"][0]["expected_position"]["x_fits"] == pytest.approx(58)
    assert len(calls)==2


def test_target_budget_isolated_from_other_targets(monkeypatch, tmp_path, fake_renderers):
    own = tmp_path / "data/raw/spx002b/epsilon_indi_b"
    other = tmp_path / "data/raw/spx002b/barnard"
    own.mkdir(parents=True); other.mkdir(parents=True)
    (own / "occupied.fits").write_bytes(b"Budget fixture only; not read as scientific data.")
    (other / "other.fits").write_bytes(b"Separate target cache.")
    def forbidden(*args, **kwargs):
        raise AssertionError("Budget exhaustion must prevent downloading.")
    monkeypatch.setattr("spherex_explorer.scientific_pipeline.download_cutout", forbidden)
    entry = cached_entry("epsilon_indi_b", [observation_record(0)])
    result = run_target(tmp_path, tmp_path / "outputs/spx002b/epsilon_indi_b", {"targets": [entry]},
                        target_model("epsilon_indi_b"), max_downloads=1, total_download_budget=1, size_deg=0.1)
    assert result["downloaded_count"] == 0
    assert "budget is exhausted" in result["failures"][0]["error"]
    unavailable = json.loads((tmp_path / "outputs/spx002b/epsilon_indi_b/sequence_manifest.json").read_text())
    assert unavailable["sequence_classification"] == "unavailable" and unavailable["frames"] == []


@pytest.mark.parametrize('key',['barnard','epsilon_indi_b','wise0855','rw_aur','r_dra'])
def test_empty_target_does_not_use_other_target_records(tmp_path, fake_renderers,key):
    availability = {"targets": [cached_entry("control_reference", [observation_record(0)]), cached_entry(key, [])]}
    result = run_target(tmp_path, tmp_path / "outputs/spx002b" / key, availability, target_model(key), size_deg=0.1)
    assert result["downloaded_count"] == 0 and result["sequence_classification"] == "unavailable"


def test_wrong_identity_and_output_location_are_rejected(tmp_path):
    availability = {"targets": [cached_entry("epsilon_indi_b", [])]}
    with pytest.raises(ValueError, match="disagree"):
        run_target(tmp_path, tmp_path / "outputs/spx002b/epsilon_indi_b", availability,
                   target_model("barnard"), target_key="epsilon_indi_b")
    with pytest.raises(ValueError, match="outputs/spx002b"):
        run_target(tmp_path, tmp_path / "outputs/spx002/barnard", availability, target_model("epsilon_indi_b"), size_deg=0.1)


def test_selection_requires_measured_centroids_without_relaxing_quality():
    records=[]
    for number, accepted in [(0, False), (1, True), (2, True)]:
        record=observation_record(number)
        record.update(wavelength_um=1.3, bandwidth_um=0.03, target_quality_ok=True,
                      target_centroid={"measurement": {"accepted": accepted}})
        records.append(record)
    selected=select_spectral_sequence(records, require_accepted_centroids=True)
    assert len(selected)==2 and all(r["target_centroid"]["measurement"]["accepted"] for r in selected)
    assert not records[0]["target_centroid"]["measurement"]["accepted"]
    assert initial_target_selection(records,2)==initial_barnard_selection(records,2)


@pytest.mark.parametrize("asset", ["C:/Users/test/image.png", "../image.png", "/tmp/image.png", "frames\\image.png"])
def test_absolute_or_escaping_asset_paths_are_rejected(asset):
    with pytest.raises(ValueError):
        relative_asset(asset)


def test_barnard_wrapper_preserves_signature_and_cache_scope(monkeypatch, tmp_path):
    calls=[]
    def generic(*args, **kwargs):
        calls.append((args,kwargs))
        return {"status":"compatibility-test"}
    monkeypatch.setattr("spherex_explorer.scientific_pipeline.run_target", generic)
    assert run_barnard(tmp_path,tmp_path/'outputs',{}, {},max_downloads=3)["status"]=="compatibility-test"
    args,kwargs=calls[0]
    assert args[3]["key"]=="barnard" and args[4]==3
    assert kwargs["legacy"] and kwargs["target_key"]=="barnard"
