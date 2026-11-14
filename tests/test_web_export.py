"""Offline export tests with synthetic local reports; no science fixtures required."""

import base64
import copy
import hashlib
import json
from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
from PIL import Image
import pytest

from spherex_explorer.web_export import export_web_data, portable_asset, sky_geometry


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def aligned_fixture(path, center, shape, observation_id):
    """Make a labeled synthetic fixed TAN DISPLAY, never a real scientific output."""
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.radesys = "ICRS"
    wcs.wcs.crval = center
    wcs.wcs.crpix = [(shape[1]+1)/2, (shape[0]+1)/2]
    wcs.wcs.cdelt = [-6.2/3600, 6.2/3600]
    header = wcs.to_header()
    header["BUNIT"] = "MJy / sr"
    header["OBSID"] = observation_id
    values = np.arange(np.prod(shape), dtype=float).reshape(shape)
    values[0, 0] = np.nan
    path.parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(values, header=header, name="DISPLAY")]).writeto(path)
    return wcs, values


@pytest.fixture
def export_project(tmp_path):
    project = tmp_path / "synthetic-project"
    write_json(project / "config/targets.json", [
        {"key": "epsilon_indi_b", "object_type": "Synthetic unresolved binary"},
        {"key": "barnard", "object_type": "Synthetic star"},
    ])
    eps_dir = project / "outputs/spx002b/epsilon_indi_b"
    _, epsilon = aligned_fixture(eps_dir / "aligned/epsilon.fits", [20., 30.], (8, 10), "epsilon")
    (eps_dir / "frames").mkdir()
    exact = np.zeros((8, 10, 4), dtype=np.uint8)
    exact[..., 0] = 41; exact[..., 3] = 255
    Image.fromarray(exact).save(eps_dir / "frames/exact.png")
    write_json(eps_dir / "sequence_manifest.json", {
        "target_id": "epsilon_indi_b", "display_name": "Synthetic Epsilon B",
        "fixed_field_center": {"ra_deg": 20., "dec_deg": 30.}, "angular_pixel_scale_arcsec": 6.2,
        "sequence_classification": "exploratory", "quality_warnings": ["Synthetic warning"],
        "display_stretch": {"vmin": 0., "vmax": 100.},
        "frames": [{"observation_id": "epsilon", "timestamp_utc": "2025-01-01T00:01:00",
                    "start_utc": "2025-01-01T00:00:00", "detector": "SPHEREx-D6", "release": "dr1",
                    "effective_wavelength_um": 4.43, "quality_warnings": [],
                    "assets": {"aligned_fits": "aligned/epsilon.fits", "image": "frames/exact.png"}}],
    })
    m_dir = project / "outputs/spx002/m101"
    wcs, _ = aligned_fixture(m_dir / "aligned/m101.fits", [200., -20.], (9, 9), "m101")
    write_json(m_dir / "alignment_report.json", {
        "pair_ids": ["m101", "unused"], "grid": {"header": dict(wcs.to_header())}, "pixel_scale_arcsec": 6.2,
        "observations": [{"observation_id": "m101", "midpoint_utc": "2025-02-02T00:01:00",
                          "start_utc": "2025-02-02T00:00:00", "detector": 2, "release": "dr1"}],
        "spectral_caution": "Synthetic registration caution",
    })
    write_json(project / "outputs/observations.json", {
        "observations": [{"observation_id": "m101", "inspection": {"effective_wavelength_um": 1.5}}],
    })
    b_dir = project / "outputs/spx002/barnard"
    aligned_fixture(b_dir / "aligned/barnard.fits", [350., 60.], (12, 12), "barnard")
    write_json(b_dir / "alignment_report.json", {
        "sequence_ids": ["barnard", "unused"], "pixel_scale_arcsec": 6.2,
        "conclusion": "Synthetic target has no measured centroid.",
    })
    write_json(b_dir / "observations.json", {
        "field_center_ra_deg": 350., "field_center_dec_deg": 60., "target": {"name": "Synthetic Barnard"},
        "sequence_mode": "Diagnostic only", "observations": [{"observation_id": "barnard", "detector": 2,
        "midpoint_utc": "2025-03-03T00:01:00", "start_utc": "2025-03-03T00:00:00", "release": "dr1", "wavelength_um": 1.46}],
    })
    # Complete synthetic pairs exercise the SPX-003B extension while retaining
    # the original first-frame assertions and synthetic-only offline fixtures.
    manifest = json.loads((eps_dir / "sequence_manifest.json").read_text())
    manifest["image_dimensions"] = {"width": 10, "height": 8}
    second = copy.deepcopy(manifest["frames"][0])
    second.update({"observation_id": "epsilon_second", "timestamp_utc": "2025-06-01T00:01:00",
                   "start_utc": "2025-06-01T00:00:00", "assets": {"aligned_fits": "aligned/epsilon_second.fits", "image": "frames/second.png"}})
    manifest["frames"].append(second)
    aligned_fixture(eps_dir / "aligned/epsilon_second.fits", [20., 30.], (8, 10), "epsilon_second")
    Image.fromarray(exact).save(eps_dir / "frames/second.png")
    write_json(eps_dir / "sequence_manifest.json", manifest)
    write_json(eps_dir / "alignment_report.json", {"measurements": [], "motion": None})
    write_json(eps_dir / "observations.json", {"observations": [{"observation_id": "epsilon"}, {"observation_id": "epsilon_second"}]})
    m_report = json.loads((m_dir / "alignment_report.json").read_text())
    metadata = dict(m_report["observations"][0], observation_id="unused", midpoint_utc="2026-02-02T00:01:00",
                    start_utc="2026-02-02T00:00:00", release="qr3")
    m_report["observations"].append(metadata)
    write_json(m_dir / "alignment_report.json", m_report)
    aligned_fixture(m_dir / "aligned/unused.fits", [200., -20.], (9, 9), "unused")
    with fits.open(m_dir / "aligned/unused.fits", mode="update") as hdus:
        hdus["DISPLAY"].data += 150.0
    m_original = json.loads((project / "outputs/observations.json").read_text())
    m_original["observations"].append({"observation_id": "unused", "inspection": {"effective_wavelength_um": 1.51}})
    write_json(project / "outputs/observations.json", m_original)
    b_original = json.loads((b_dir / "observations.json").read_text())
    b_original["observations"].append(dict(b_original["observations"][0], observation_id="unused",
                                         midpoint_utc="2026-03-03T00:01:00", start_utc="2026-03-03T00:00:00"))
    write_json(b_dir / "observations.json", b_original)
    aligned_fixture(b_dir / "aligned/unused.fits", [350., 60.], (12, 12), "unused")
    b_report = json.loads((b_dir / "alignment_report.json").read_text())
    b_report["observations"] = b_original["observations"]
    b_report["measurements"] = []
    write_json(b_dir / "alignment_report.json", b_report)
    return project


def test_catalog_uses_three_processed_sources_and_retains_classifications(export_project, tmp_path):
    destination = tmp_path / "web"
    catalog = export_web_data(export_project, destination)
    assert catalog["version"] == 1
    fields = {field["id"]: field for field in catalog["targets"]}
    assert set(fields) == {"epsilon_indi_b", "m101", "barnard"}
    assert fields["epsilon_indi_b"]["center"] == {"raDeg": 20., "decDeg": 30.}
    assert fields["m101"]["center"] == {"raDeg": 200., "decDeg": -20.}
    assert fields["barnard"]["center"] == {"raDeg": 350., "decDeg": 60.}
    assert fields["epsilon_indi_b"]["classification"] == "exploratory"
    assert fields["m101"]["classification"] == "registration example"
    assert fields["barnard"]["classification"] == "diagnostic"
    assert fields["epsilon_indi_b"]["observation"]["wavelengthUm"] == 4.43
    assert fields["barnard"]["observation"]["timestampUtc"] == "2025-03-03T00:01:00"
    assert fields["epsilon_indi_b"]["dimensions"] == {"width": 10, "height": 8}
    assert fields["m101"]["dimensions"] == {"width": 9, "height": 9}
    assert all("motion" not in field for field in catalog["targets"])


def test_assets_exist_are_portable_and_source_inputs_unchanged(export_project, tmp_path):
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in export_project.rglob("*") if path.is_file()}
    destination = tmp_path / "web"
    catalog = export_web_data(export_project, destination)
    for field in catalog["targets"]:
        for asset in field["assets"].values():
            assert portable_asset(asset) == asset
            assert (destination / asset).exists()
        assert not Path(field["provenance"]["sourceAlignedFits"]).is_absolute()
    assert str(export_project) not in (destination / "catalog.json").read_text()
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == value for path, value in before.items())


def test_fits_is_single_primary_display_with_original_tan_and_nan(export_project, tmp_path):
    destination = tmp_path / "web"
    catalog = export_web_data(export_project, destination)
    for field in catalog["targets"]:
        with fits.open(destination / field["assets"]["fits"]) as exported, fits.open(destination / field["assets"]["alignedFits"]) as source:
            assert len(exported) == 1
            assert isinstance(exported[0], fits.PrimaryHDU)
            np.testing.assert_allclose(exported[0].data, source["DISPLAY"].data, equal_nan=True)
            assert exported[0].header["BUNIT"] == "MJy / sr"
            assert exported[0].header["CTYPE1"] == "RA---TAN"
            assert exported[0].header["DATE-AVG"] == field["observation"]["timestampUtc"]
            assert exported[0].header["DATE-OBS"] == field["observation"]["startUtc"]
            assert exported[0].header["DATE-AVG"] != exported[0].header["DATE-OBS"]


def test_footprint_represents_outer_wcs_edges_not_pixel_centers(export_project, tmp_path):
    catalog = export_web_data(export_project, tmp_path / "web")
    for field in catalog["targets"]:
        width, height = field["dimensions"]["width"], field["dimensions"]["height"]
        wcs = WCS(field["wcsHeader"])
        ra, dec = np.asarray(field["footprint"]).T
        x, y = wcs.all_world2pix(ra, dec, 0)
        np.testing.assert_allclose(x, [-0.5, width - 0.5, width - 0.5, -0.5], atol=1e-8)
        np.testing.assert_allclose(y, [-0.5, -0.5, height - 0.5, height - 0.5], atol=1e-8)
        assert field["geometryValidation"]["northUp"] and field["geometryValidation"]["eastLeft"]
        assert field["geometryValidation"]["centerErrorArcsec"] < 1e-5
        assert field["angularSizeDeg"]["width"] == pytest.approx(width * 6.2 / 3600, rel=1e-5)


def test_exact_epsilon_png_is_copied_and_generated_pngs_are_north_up(export_project, tmp_path):
    destination = tmp_path / "web"
    catalog = export_web_data(export_project, destination)
    fields = {field["id"]: field for field in catalog["targets"]}
    exact = export_project / "outputs/spx002b/epsilon_indi_b/frames/exact.png"
    assert exact.read_bytes() == (destination / fields["epsilon_indi_b"]["assets"]["png"]).read_bytes()
    for key in ("m101", "barnard"):
        with Image.open(destination / fields[key]["assets"]["png"]) as image:
            pixels = np.asarray(image)
            assert image.size == (fields[key]["dimensions"]["width"], fields[key]["dimensions"]["height"])
            assert pixels[0, 1, 0] > pixels[-1, 1, 0]  # Synthetic row values increase north.
            assert pixels[-1, 0, :3].tolist() == [104, 58, 104]  # FITS [0,0] NaN is south-west.


def test_repeated_export_is_deterministic(export_project, tmp_path):
    destination = tmp_path / "web"
    first = export_web_data(export_project, destination)
    checksums = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in destination.rglob("*") if path.is_file()}
    assert export_web_data(export_project, destination) == first
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in checksums.items())


@pytest.mark.parametrize("asset", ["C:/Users/test/frame.png", "../frame.png", "/frame.png", "folder\\frame.png", ""])
def test_nonportable_paths_are_rejected(asset):
    with pytest.raises(ValueError):
        portable_asset(asset)


def test_wrong_center_or_orientation_is_not_silently_exported():
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10., 20.]; wcs.wcs.crpix = [3., 3.]
    wcs.wcs.cdelt = [-6.2/3600, 6.2/3600]
    with pytest.raises(ValueError, match="center differs"):
        sky_geometry(wcs, (5, 5), 11., 20., 6.2)
    wcs.wcs.cdelt = [6.2/3600, 6.2/3600]
    with pytest.raises(ValueError, match="north-up"):
        sky_geometry(wcs, (5, 5), 10., 20., 6.2)


def test_temporal_pairs_are_chronological_and_have_portable_existing_assets(export_project, tmp_path):
    destination = tmp_path / "web"
    catalog = export_web_data(export_project, destination)
    for target in catalog["targets"]:
        sequence = target["sequence"]
        frames = sequence["frames"]
        assert len(frames) == 2
        assert frames[0]["observation"]["timestampUtc"] < frames[1]["observation"]["timestampUtc"]
        assert sequence["classification"] == target["classification"]
        assert sequence["warnings"] == target["warnings"]
        for frame in frames:
            for path in frame["assets"].values():
                assert portable_asset(path) == path
                assert (destination / path).is_file()
            assert "alignedFits" not in frame["assets"]  # No original science copies per epoch.
            assert str(export_project) not in json.dumps(frame)
    assert "motion" not in next(t for t in catalog["targets"] if t["id"] == "m101")
    assert next(t for t in catalog["targets"] if t["id"] == "m101")["sequence"]["motion"] is None


def test_temporal_common_normalization_does_not_autoscale_each_frame(export_project, tmp_path):
    destination = tmp_path / "web"
    catalog = export_web_data(export_project, destination)
    for target in catalog["targets"]:
        sequence = target["sequence"]
        cuts = sequence["display"]
        assert cuts["common"] is True
        assert target["display"] == cuts
        all_finite = []
        for frame in sequence["frames"]:
            assert frame["display"] == cuts
            with fits.open(destination / frame["assets"]["fits"]) as hdus:
                assert hdus[0].header["DATAMIN"] == cuts["vmin"]
                assert hdus[0].header["DATAMAX"] == cuts["vmax"]
                all_finite.extend(hdus[0].data[np.isfinite(hdus[0].data)])
        if target["id"] == "m101":
            assert cuts["vmax"] > 150  # Shared with the much brighter synthetic second epoch.
            np.testing.assert_allclose([cuts["vmin"], cuts["vmax"]], np.percentile(all_finite, [0.5, 99.5]))
        if target["id"] == "epsilon_indi_b":
            assert (cuts["vmin"], cuts["vmax"]) == (0.0, 100.0)


def test_temporal_masks_retain_distinct_display_and_science_coverage(export_project, tmp_path):
    source = export_project / "outputs/spx002/m101/aligned/m101.fits"
    with fits.open(source, mode="update", memmap=False) as hdus:
        mask = np.zeros(hdus["DISPLAY"].data.shape, dtype=np.uint8)
        mask[3:5, 3:5] = 1
        hdus.append(fits.ImageHDU(mask, name="COVERAGE"))
    destination = tmp_path / "web"
    target = next(t for t in export_web_data(export_project, destination)["targets"] if t["id"] == "m101")
    frame = target["sequence"]["frames"][0]
    masks = json.loads((destination / frame["assets"]["masks"]).read_text())
    decoded = np.unpackbits(np.frombuffer(base64.b64decode(masks["scienceValid"]), dtype=np.uint8), bitorder="little")[:81].reshape(9, 9)
    np.testing.assert_array_equal(decoded, mask)
    display = np.unpackbits(np.frombuffer(base64.b64decode(masks["displayValid"]), dtype=np.uint8), bitorder="little")[:81].reshape(9, 9)
    assert display.sum() == 80
    assert decoded.sum() == 4
    assert frame["masks"]["scienceValidFraction"] == pytest.approx(4 / 81)
    missing = target["sequence"]["frames"][1]
    assert missing["masks"]["scienceMaskAvailable"] is False
    assert missing["masks"]["scienceValidFraction"] is None


def test_temporal_missing_measurements_remain_null(export_project, tmp_path):
    target = next(t for t in export_web_data(export_project, tmp_path / "web")["targets"] if t["id"] == "barnard")
    for frame in target["sequence"]["frames"]:
        assert frame["measuredPosition"] is None
        assert frame["formalCentroidErrorArcsec"] is None
        assert frame["formalCentroidErrorOriginalPixels"] is None
    assert "invalid and saturated" in target["sequence"]["interpretation"]


def test_temporal_different_wcs_is_rejected(export_project, tmp_path):
    source = export_project / "outputs/spx002/m101/aligned/unused.fits"
    with fits.open(source, mode="update") as hdus:
        hdus["DISPLAY"].header["CRVAL1"] += 0.001
    with pytest.raises(ValueError, match="same fixed WCS"):
        export_web_data(export_project, tmp_path / "web")


def test_temporal_missing_selected_observation_is_an_explicit_error(export_project, tmp_path):
    source = export_project / "outputs/spx002/m101/alignment_report.json"
    report = json.loads(source.read_text())
    report["pair_ids"][1] = "nonexistent"
    write_json(source, report)
    with pytest.raises(ValueError, match="no source metadata"):
        export_web_data(export_project, tmp_path / "web")


def test_temporal_expected_and_measured_positions_use_distinct_coordinates(export_project, tmp_path):
    source = export_project / "outputs/spx002b/epsilon_indi_b/sequence_manifest.json"
    manifest = json.loads(source.read_text())
    for index, record in enumerate(manifest["frames"]):
        wcs = WCS(fits.getheader(export_project / "outputs/spx002b/epsilon_indi_b" / record["assets"]["aligned_fits"], "DISPLAY"))
        for key, x, y in (("expected_position", 4 + index * .2, 3.), ("measured_position", 4.1 + index * .3, 3.1)):
            sky = wcs.pixel_to_world(x, y)
            record[key] = {"ra_deg": float(sky.ra.deg), "dec_deg": float(sky.dec.deg), "x_fits": x, "y_fits": y,
                           "x_image": x, "y_image": 7 - y}
        record["centroid_accepted"] = True
    write_json(source, manifest)
    target = next(t for t in export_web_data(export_project, tmp_path / "web")["targets"] if t["id"] == "epsilon_indi_b")
    first = target["sequence"]["frames"][0]
    assert first["expectedPosition"]["xFits"] == 4.
    assert first["measuredPosition"]["xFits"] == 4.1
    assert first["measuredPosition"]["yImage"] == 7 - 3.1


def test_temporal_motion_diagnostics_are_imported_without_reinterpreting_formal_errors(export_project, tmp_path):
    directory = export_project / "outputs/spx002b/epsilon_indi_b"
    write_json(directory / "alignment_report.json", {
        "motion": {"measured_displacement_arcsec": 1.23, "expected_displacement_arcsec": 1.41,
                   "measured_displacement_pixels": .198, "expected_displacement_pixels": .227,
                   "formal_endpoint_error_arcsec": .12, "time_separation_days": 151.5,
                   "expected_east_north_arcsec": [1., -1.], "measured_east_north_arcsec": [.8, -.93]},
        "background_reference_residuals": {"rms_arcsec": .77, "matched_source_count": 4},
        "measurements": [{"observation_id": "epsilon", "measurement": {"formal_error_arcsec": .08}}],
        "target": {"source": "Synthetic astrometric fixture", "coordinate_bibcode": "Synthetic bibcode"},
    })
    catalog = export_web_data(export_project, tmp_path / "web")
    sequence = next(t["sequence"] for t in catalog["targets"] if t["id"] == "epsilon_indi_b")
    assert sequence["motion"]["measuredDisplacementArcsec"] == 1.23
    assert sequence["motion"]["expectedDisplacementArcsec"] == 1.41
    assert sequence["motion"]["referenceRmsArcsec"] == .77
    assert sequence["motion"]["formalEndpointErrorArcsec"] == .12
    assert sequence["motion"]["referenceCount"] == 4
    assert sequence["motion"]["significantDetectionClaimed"] is False
    assert sequence["frames"][0]["formalCentroidErrorArcsec"] == .08
    assert "incomplete" in sequence["motion"]["formalErrorWarning"]
    assert sequence["astrometricReference"]["source"] == "Synthetic astrometric fixture"


def test_temporal_processing_provenance_and_versions_are_retained(export_project, tmp_path):
    directory = export_project / "outputs/spx002b/epsilon_indi_b"
    source = directory / "sequence_manifest.json"
    manifest = json.loads(source.read_text())
    manifest["frames"][0].update({"processing_version": "synthetic-version-1", "bandwidth_um": .04})
    write_json(source, manifest)
    write_json(directory / "observations.json", {"observations": [
        {"observation_id": "epsilon", "url": "https://example.invalid/synthetic-source-only", "midpoint_mjd": 60000.5},
        {"observation_id": "epsilon_second"},
    ]})
    destination = tmp_path / "web"
    target = next(t for t in export_web_data(export_project, destination)["targets"] if t["id"] == "epsilon_indi_b")
    frame = target["sequence"]["frames"][0]
    assert frame["observation"]["processingVersion"] == "synthetic-version-1"
    assert frame["observation"]["bandwidthUm"] == .04
    assert frame["observation"]["mjd"] == 60000.5
    assert frame["provenance"]["sourceUrl"] == "https://example.invalid/synthetic-source-only"
    assert fits.getheader(destination / frame["assets"]["fits"])["PROCVER"] == "synthetic-version-1"
