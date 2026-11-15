"""Export existing fixed-grid SPHEREx observations as small, portable web assets.

No archive requests, reprojection, recentering, or science-result writes occur here.
The web FITS is a derived display product retaining the original TAN registration.
"""

from dataclasses import dataclass
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
from astropy.time import Time
from astropy.visualization import AsinhStretch, ImageNormalize
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from .fits_utils import write_manifest


@dataclass(frozen=True)
class WebField:
    """One already processed field and the exact existing observation to expose."""

    target_id: str
    name: str
    object_type: str
    aligned_fits: Path
    center_ra_deg: float
    center_dec_deg: float
    pixel_scale_arcsec: float
    classification: str
    observation: dict
    warnings: list[str]
    exact_png: Path | None = None
    display_limits: tuple[float, float] | None = None


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def portable_asset(value: str) -> str:
    """Return a relative POSIX asset path, rejecting host paths and traversal."""
    value = str(value)
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError(f"Asset must be a portable relative path: {value}")
    return path.as_posix()


def sky_geometry(wcs: WCS, shape: tuple[int, int], center_ra: float, center_dec: float,
                 expected_scale_arcsec: float) -> dict:
    """Derive outer-boundary footprint, angular extent and orientation from WCS."""
    height, width = shape
    x, y = (width - 1) / 2, (height - 1) / 2
    actual = wcs.pixel_to_world(x, y).icrs
    requested = SkyCoord(center_ra * u.deg, center_dec * u.deg, frame="icrs")
    center_error = float(actual.separation(requested).arcsec)
    if center_error > 1e-5:
        raise ValueError(f"Fixed catalog center differs from aligned WCS by {center_error} arcsec.")
    right, up = wcs.pixel_to_world(x + 1, y), wcs.pixel_to_world(x, y + 1)
    east_right, _ = actual.spherical_offsets_to(right)
    _, north_up = actual.spherical_offsets_to(up)
    if east_right.arcsec >= 0 or north_up.arcsec <= 0:
        raise ValueError("Expected the existing north-up, east-left aligned grid.")
    scale = np.asarray(proj_plane_pixel_scales(wcs)) * 3600
    if not np.allclose(scale, expected_scale_arcsec, rtol=1e-8, atol=1e-8):
        raise ValueError("Aligned WCS scale differs from its scientific metadata.")
    corners_xy = np.array([[-0.5, -0.5], [width - 0.5, -0.5],
                           [width - 0.5, height - 0.5], [-0.5, height - 0.5]])
    corners = wcs.pixel_to_world(corners_xy[:, 0], corners_xy[:, 1]).icrs
    recovered_x, recovered_y = wcs.world_to_pixel(corners)
    footprint_error = float(np.max(np.hypot(recovered_x - corners_xy[:, 0],
                                           recovered_y - corners_xy[:, 1])))
    horizontal = wcs.pixel_to_world(-0.5, y).separation(wcs.pixel_to_world(width - 0.5, y)).deg
    vertical = wcs.pixel_to_world(x, -0.5).separation(wcs.pixel_to_world(x, height - 0.5)).deg
    return {
        "center": {"raDeg": float(center_ra), "decDeg": float(center_dec)},
        "dimensions": {"width": width, "height": height},
        "pixelScaleArcsec": float(expected_scale_arcsec),
        "wcsHeader": dict(wcs.to_header(relax=True)),
        "footprint": [[float(ra), float(dec)] for ra, dec in zip(corners.ra.deg, corners.dec.deg)],
        "angularSizeDeg": {"width": float(horizontal), "height": float(vertical)},
        "geometryValidation": {"centerErrorArcsec": center_error,
                               "cornerRoundtripErrorPixels": footprint_error,
                               "northUp": True, "eastLeft": True,
                               "footprintConvention": "Outer pixel edges, ordered bottom-left, bottom-right, top-right, top-left in FITS coordinates."},
    }


def display_limits(values: np.ndarray, limits=None) -> tuple[float, float]:
    """Use recorded common cuts when available, otherwise robust display-only cuts."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError("A web display cannot be exported without any finite pixels.")
    low, high = limits if limits is not None else np.percentile(finite, [0.5, 99.5])
    low, high = float(low), float(high)
    if not np.isfinite(low + high):
        raise ValueError("Display limits must be finite.")
    if high <= low:
        high = low + max(abs(low) * 1e-6, 1e-6)
    return low, high


def export_field(field: WebField, output: Path, project: Path) -> dict:
    """Create a primary-HDU display FITS while preserving scientific inputs exactly."""
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", field.target_id):
        raise ValueError("A safe target ID is required for exported assets.")
    output, project = Path(output), Path(project).resolve()
    source = Path(field.aligned_fits).resolve()
    with fits.open(source, memmap=False) as hdus:
        if "DISPLAY" not in hdus or hdus["DISPLAY"].data is None:
            raise ValueError(f"Aligned file has no DISPLAY extension: {source.name}")
        values = np.array(hdus["DISPLAY"].data, dtype=float, copy=True)
        if values.ndim != 2:
            raise ValueError("Only an existing two-dimensional aligned display is supported.")
        header = hdus["DISPLAY"].header.copy()
    wcs = WCS(header)
    if not wcs.has_celestial or list(wcs.wcs.ctype) != ["RA---TAN", "DEC--TAN"] or wcs.sip is not None:
        raise ValueError("Web export requires the validated fixed TAN grid, without output SIP.")
    geometry = sky_geometry(wcs, values.shape, field.center_ra_deg, field.center_dec_deg, field.pixel_scale_arcsec)
    low, high = display_limits(values, field.display_limits)
    target_dir = output / field.target_id
    target_dir.mkdir(parents=True, exist_ok=True)
    fits_asset = portable_asset(f"{field.target_id}/observation.fits")
    png_asset = portable_asset(f"{field.target_id}/frame.png")
    aligned_asset = portable_asset(f"{field.target_id}/aligned.fits")

    web_header = wcs.to_header(relax=True)
    for key in ("BUNIT", "OBSID"):
        if key in header:
            web_header[key] = header[key]
    web_header["DATE-AVG"] = field.observation["timestampUtc"]
    if field.observation.get("startUtc") is not None:
        web_header["DATE-OBS"] = field.observation["startUtc"]
    web_header["TIMESYS"] = "UTC"
    web_header["DETECTOR"] = field.observation["detector"]
    web_header["RELEASE"] = field.observation["release"]
    web_header["HISTORY"] = "SPX-003A display derivative of validated aligned DISPLAY; no recentering or resampling."
    web_header["HISTORY"] = "NaN retains missing/invalid display coverage. Scientific arrays remain in aligned.fits."
    fits.PrimaryHDU(values.astype(np.float32), header=web_header).writeto(output / fits_asset, overwrite=True)
    shutil.copyfile(source, output / aligned_asset)
    if field.exact_png is not None:
        with Image.open(field.exact_png) as image:
            if image.size != (values.shape[1], values.shape[0]):
                raise ValueError("Existing exact frame PNG dimensions differ from the aligned FITS.")
        shutil.copyfile(field.exact_png, output / png_asset)
    else:
        normalization = ImageNormalize(vmin=low, vmax=high, stretch=AsinhStretch())
        cmap = plt.get_cmap("gray").with_extremes(bad="#683a68")
        rgba = cmap(normalization(np.ma.masked_invalid(values)), bytes=True)
        # FITS row zero is south; web PNG row zero is north.
        Image.fromarray(np.flipud(rgba)).save(output / png_asset)
    try:
        source_relative = source.relative_to(project).as_posix()
    except ValueError:
        source_relative = source.name
    return {
        "id": field.target_id, "name": field.name, "objectType": field.object_type,
        **geometry, "classification": field.classification, "observation": dict(field.observation),
        "assets": {"fits": fits_asset, "png": png_asset, "alignedFits": aligned_asset},
        "display": {"vmin": low, "vmax": high, "stretch": "asinh", "invalidColor": "#683a68",
                    "sourceHdu": "DISPLAY", "pngOrigin": "top-left; north up", "fitsOrigin": "bottom-left; north up"},
        "warnings": list(field.warnings),
        "provenance": {"sourceAlignedFits": source_relative,
                       "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                       "webFitsKind": "Primary-HDU float32 display derivative; same dimensions and TAN WCS, no resampling.",
                       "exactPngCopied": field.exact_png is not None},
    }


def prepared_fields(project: Path) -> list[WebField]:
    """Read exactly the three already processed fields, without scientific queries."""
    project = Path(project)
    configured = {entry["key"]: entry for entry in load_json(project / "config/targets.json")}

    epsilon_dir = project / "outputs/spx002b/epsilon_indi_b"
    epsilon = load_json(epsilon_dir / "sequence_manifest.json")
    frame = epsilon["frames"][0]
    e = WebField(
        epsilon["target_id"], epsilon["display_name"], configured["epsilon_indi_b"]["object_type"],
        epsilon_dir / portable_asset(frame["assets"]["aligned_fits"]),
        epsilon["fixed_field_center"]["ra_deg"], epsilon["fixed_field_center"]["dec_deg"],
        epsilon["angular_pixel_scale_arcsec"], epsilon["sequence_classification"],
        {"id": frame["observation_id"], "timestampUtc": frame["timestamp_utc"], "startUtc": frame["start_utc"],
         "timestampKind": "Observation midpoint, UTC", "detector": frame["detector"], "release": frame["release"],
         "wavelengthUm": frame["effective_wavelength_um"],
         "wavelengthReference": "Existing target-position spectral metadata; not a global detector wavelength."},
        epsilon["quality_warnings"] + frame.get("quality_warnings", []),
        exact_png=epsilon_dir / portable_asset(frame["assets"]["image"]),
        display_limits=(epsilon["display_stretch"]["vmin"], epsilon["display_stretch"]["vmax"]),
    )

    m101_dir = project / "outputs/spx002/m101"
    m101 = load_json(m101_dir / "alignment_report.json")
    m101_id = m101["pair_ids"][0]
    metadata = next(item for item in m101["observations"] if item["observation_id"] == m101_id)
    old = load_json(project / "outputs/observations.json")
    record = next(item for item in old["observations"] if item["observation_id"] == m101_id)
    m = WebField(
        "m101", "M101", "Galaxy / registration field", m101_dir / "aligned" / f"{m101_id}.fits",
        m101["grid"]["header"]["CRVAL1"], m101["grid"]["header"]["CRVAL2"], m101["pixel_scale_arcsec"],
        "registration example",
        {"id": m101_id, "timestampUtc": metadata["midpoint_utc"], "startUtc": metadata["start_utc"], "timestampKind": "Observation midpoint, UTC",
         "detector": f"SPHEREx-D{int(metadata['detector'])}", "release": metadata["release"],
         "wavelengthUm": record["inspection"]["effective_wavelength_um"], "wavelengthReference": "Fixed requested ICRS field center."},
        [m101["spectral_caution"], "Registration/exploration example; no object motion is measured.",
         "Each displayed SPHEREx frame is one individual observation; the context survey is a different data product."],
    )

    barnard_dir = project / "outputs/spx002/barnard"
    barnard = load_json(barnard_dir / "alignment_report.json")
    original = load_json(barnard_dir / "observations.json")
    barnard_id = barnard["sequence_ids"][0]
    record = next(item for item in original["observations"] if item["observation_id"] == barnard_id)
    b = WebField(
        "barnard", original["target"]["name"], configured["barnard"]["object_type"],
        barnard_dir / "aligned" / f"{barnard_id}.fits", original["field_center_ra_deg"], original["field_center_dec_deg"],
        barnard["pixel_scale_arcsec"], "diagnostic",
        {"id": barnard_id, "timestampUtc": record["midpoint_utc"], "startUtc": record["start_utc"], "timestampKind": "Observation midpoint, UTC",
         "detector": f"SPHEREx-D{int(record['detector'])}", "release": record["release"],
         "wavelengthUm": record["wavelength_um"], "wavelengthReference": "Predicted catalog target position at the observation midpoint."},
        [barnard["conclusion"], original["sequence_mode"],
         "Target core is invalid; no reliable observed motion or target centroid exists."],
    )
    return [e, m, b]


def _position(ra, dec, x, y, height: int) -> dict | None:
    """Retain real sky and fixed-grid positions, never synthesizing a centroid."""
    if any(value is None for value in (ra, dec, x, y)):
        return None
    if not np.all(np.isfinite([ra, dec, x, y])):
        raise ValueError("Temporal positions must be finite or null.")
    return {"raDeg": float(ra), "decDeg": float(dec), "xFits": float(x), "yFits": float(y),
            "xImage": float(x), "yImage": float(height - 1 - y)}


def _manifest_position(position: dict | None, height: int) -> dict | None:
    if position is None:
        return None
    result = _position(position.get("ra_deg"), position.get("dec_deg"), position.get("x_fits"),
                       position.get("y_fits"), height)
    if result is not None and (not np.isclose(result["yImage"], position["y_image"], atol=1e-10, rtol=0)
                               or not np.isclose(result["xImage"], position["x_image"], atol=1e-10, rtol=0)):
        raise ValueError("Manifest PNG/FITS position conventions disagree.")
    return result


def temporal_sources(project: Path, field: WebField) -> tuple[list[dict], dict]:
    """Read selected existing pairs, including accepted/null positions and provenance.

    Private source paths remain Python-only; exported frame paths are relative.
    No new astrometric fit, spectral query, or motion estimate is performed.
    """
    if field.target_id == "epsilon_indi_b":
        directory = project / "outputs/spx002b/epsilon_indi_b"
        manifest = load_json(directory / "sequence_manifest.json")
        report = load_json(directory / "alignment_report.json")
        originals = {record["observation_id"]: record for record in load_json(directory / "observations.json")["observations"]}
        measurements = {record["observation_id"]: record for record in report.get("measurements", [])}
        frames = []
        height = manifest["image_dimensions"]["height"]
        for record in manifest["frames"]:
            identifier = record["observation_id"]
            original = originals.get(identifier, {})
            measurement = measurements.get(identifier, {}).get("measurement", {})
            frames.append({
                "id": identifier, "source": directory / portable_asset(record["assets"]["aligned_fits"]),
                "exactPng": directory / portable_asset(record["assets"]["image"]),
                "observation": {"id": identifier, "timestampUtc": record["timestamp_utc"],
                                "startUtc": record.get("start_utc"), "timestampKind": record.get("timestamp_kind"),
                                "detector": record["detector"], "release": record["release"],
                                "processingVersion": record.get("processing_version"),
                                "wavelengthUm": record.get("effective_wavelength_um"),
                                "bandwidthUm": record.get("bandwidth_um"), "mjd": original.get("midpoint_mjd"),
                                "wavelengthReference": "Existing target-position spectral metadata."},
                "expectedPosition": _manifest_position(record.get("expected_position"), height),
                "measuredPosition": _manifest_position(record.get("measured_position"), height)
                                    if record.get("centroid_accepted") else None,
                "formalCentroidErrorOriginalPixels": record.get("formal_centroid_error_original_pixels"),
                "formalCentroidErrorArcsec": measurement.get("formal_error_arcsec"),
                "warnings": record.get("quality_warnings", []), "sourceUrl": original.get("url"),
                "measurementReason": measurement.get("reason"),
            })
        details = {"report": report, "sourceManifest": directory / "sequence_manifest.json",
                   "limits": (manifest["display_stretch"]["vmin"], manifest["display_stretch"]["vmax"]),
                   "predictionModel": manifest.get("prediction_model"), "astrometricReference": report.get("target"),
                   "interpretation": "Exploratory apparent photocenter displacement measured from two real SPHEREx observations. Unvalidated instrumental and astrometric systematics prevent a significant-motion detection claim."}
    else:
        directory = project / "outputs/spx002" / field.target_id
        report = load_json(directory / "alignment_report.json")
        is_m101 = field.target_id == "m101"
        raw_manifest = project / "outputs/observations.json" if is_m101 else directory / "observations.json"
        raw = load_json(raw_manifest)
        originals = {record["observation_id"]: record for record in raw["observations"]}
        records = {record["observation_id"]: record for record in report.get("observations", [])}
        measurements = {record["observation_id"]: record for record in report.get("measurements", [])}
        identifiers = report["pair_ids"] if is_m101 else report["sequence_ids"]
        # Dimensions come from the actual aligned image, not an inferred sky size.
        with fits.open(field.aligned_fits) as hdus:
            height = hdus["DISPLAY"].data.shape[0]
        frames = []
        for identifier in identifiers:
            if identifier not in originals or identifier not in records:
                raise ValueError(f"Selected temporal observation has no source metadata: {identifier}")
            original, metadata = originals[identifier], records[identifier]
            inspection = original.get("inspection", {})
            centroid = measurements.get(identifier, {})
            measurement = centroid.get("measurement", {})
            frames.append({
                "id": identifier, "source": directory / "aligned" / f"{identifier}.fits", "exactPng": None,
                "observation": {"id": identifier, "timestampUtc": metadata["midpoint_utc"],
                                "startUtc": metadata.get("start_utc"), "timestampKind": "Observation midpoint, UTC",
                                "detector": f"SPHEREx-D{int(metadata['detector'])}", "release": metadata["release"],
                                "processingVersion": original.get("processing_version"),
                                "wavelengthUm": inspection.get("effective_wavelength_um") if is_m101 else original.get("wavelength_um"),
                                "bandwidthUm": inspection.get("spectral_bandwidth_um") if is_m101 else original.get("bandwidth_um"),
                                "mjd": metadata.get("midpoint_mjd"),
                                "wavelengthReference": "Fixed requested ICRS field center." if is_m101 else "Predicted catalog target position at the observation midpoint."},
                "expectedPosition": _position(centroid.get("expected_ra_deg"), centroid.get("expected_dec_deg"),
                                              centroid.get("expected_x"), centroid.get("expected_y"), height),
                "measuredPosition": _position(measurement.get("ra_deg"), measurement.get("dec_deg"),
                                              centroid.get("measured_x"), centroid.get("measured_y"), height)
                                    if measurement.get("accepted") else None,
                "formalCentroidErrorOriginalPixels": measurement.get("formal_error_pixels") if measurement.get("accepted") else None,
                "formalCentroidErrorArcsec": measurement.get("formal_error_arcsec") if measurement.get("accepted") else None,
                "warnings": [measurement["reason"]] if measurement.get("reason") else [],
                "sourceUrl": original.get("url"), "measurementReason": measurement.get("reason"),
            })
        details = {"report": report, "sourceManifest": directory / "alignment_report.json", "limits": None,
                   "predictionModel": raw.get("predicted_motion_model"), "astrometricReference": report.get("astrometric_reference"),
                   "interpretation": "Registration/exploration example across distinct releases; no quantitative temporal change or object motion has been validated."
                                     if is_m101 else "Diagnostic comparison: invalid and saturated target cores prevent a reliable measured displacement. Expected positions are predictions only."}
    if len(frames) != 2:
        raise ValueError(f"The selected {field.target_id} sequence must contain exactly two existing observations.")
    frames.sort(key=lambda frame: Time(frame["observation"]["timestampUtc"], scale="utc").mjd)
    return frames, details


def _read_temporal_display(source: Path) -> tuple[np.ndarray, fits.Header, np.ndarray | None]:
    """Read display and conservative coverage separately, retaining missing masks as null."""
    with fits.open(source, memmap=False) as hdus:
        values = np.array(hdus["DISPLAY"].data, dtype=float, copy=True)
        header = hdus["DISPLAY"].header.copy()
        coverage = np.array(hdus["COVERAGE"].data, dtype=bool, copy=True) if "COVERAGE" in hdus else None
    if values.ndim != 2 or (coverage is not None and coverage.shape != values.shape):
        raise ValueError("Temporal display/mask dimensions must share one two-dimensional grid.")
    return values, header, coverage


def _pack_mask(values: np.ndarray | None) -> str | None:
    if values is None:
        return None
    return base64.b64encode(np.packbits(values.ravel(), bitorder="little").tobytes()).decode("ascii")


def export_sequence(field: WebField, target: dict, project: Path, output: Path) -> dict:
    """Export the selected real pair with common cuts and fixed WCS.

    Catalog contract: sequence.frames carry observation metadata, local assets,
    nullable expected/measured positions and incomplete formal errors. Masks are
    separate packed-bit JSON products in FITS row order. sequence.display is the
    one shared normalization, and sequence.motion imports existing diagnostics.
    """
    frames, details = temporal_sources(project, field)
    arrays = [_read_temporal_display(frame["source"]) for frame in frames]
    reference_wcs = WCS(arrays[0][1]).to_header(relax=True)
    reference_shape = arrays[0][0].shape
    for values, header, _ in arrays:
        if values.shape != reference_shape or dict(WCS(header).to_header(relax=True)) != dict(reference_wcs):
            raise ValueError("Temporal frames must retain exactly the same fixed WCS and dimensions.")
        if header.get("BUNIT") != arrays[0][1].get("BUNIT"):
            raise ValueError("Temporal display units disagree.")
        sky_geometry(WCS(header), values.shape, field.center_ra_deg, field.center_dec_deg, field.pixel_scale_arcsec)
    low, high = display_limits(np.concatenate([values[np.isfinite(values)] for values, _, _ in arrays]), details["limits"])
    display = {"vmin": low, "vmax": high, "stretch": "asinh", "common": True,
               "pngAsinhParameter": 0.1, "invalidColor": "#683a68", "units": arrays[0][1].get("BUNIT"),
               "sourceHdu": "DISPLAY", "limitsSource": "Existing sequence_manifest display_stretch" if details["limits"] else "Common 0.5/99.5 percentiles across the selected pair's finite DISPLAY pixels",
               "warning": "Display normalization only; no PNG or visual-intensity quantitative photometry."}
    exported = []
    normalization = ImageNormalize(vmin=low, vmax=high, stretch=AsinhStretch())
    cmap = plt.get_cmap("gray").with_extremes(bad="#683a68")
    for frame, (values, source_header, coverage) in zip(frames, arrays):
        identifier = frame["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
            raise ValueError("Unsafe observation identifier in temporal assets.")
        prefix = portable_asset(f"{field.target_id}/frames/{identifier}")
        assets = {"fits": prefix + ".fits", "png": prefix + ".png", "masks": prefix + ".masks.json"}
        (output / assets["fits"]).parent.mkdir(parents=True, exist_ok=True)
        header = reference_wcs.copy()
        for key in ("BUNIT", "OBSID"):
            if key in source_header:
                header[key] = source_header[key]
        header["DATE-AVG"] = frame["observation"]["timestampUtc"]
        if frame["observation"]["startUtc"] is not None:
            header["DATE-OBS"] = frame["observation"]["startUtc"]
        header["TIMESYS"] = "UTC"
        header["DETECTOR"] = frame["observation"]["detector"]
        header["RELEASE"] = frame["observation"]["release"]
        if frame["observation"]["processingVersion"] is not None:
            header["PROCVER"] = frame["observation"]["processingVersion"]
        header["DATAMIN"], header["DATAMAX"] = low, high
        header["HISTORY"] = "SPX-003B DISPLAY derivative; unchanged fixed TAN grid and pixels."
        header["HISTORY"] = "Shared sequence cuts in DATAMIN/DATAMAX; preserve NaN; not quantitative photometry."
        fits.PrimaryHDU(values.astype(np.float32), header=header).writeto(output / assets["fits"], overwrite=True)
        if frame["exactPng"] is not None:
            with Image.open(frame["exactPng"]) as image:
                if image.size != (reference_shape[1], reference_shape[0]):
                    raise ValueError("Exact sequence PNG dimensions disagree with FITS.")
            shutil.copyfile(frame["exactPng"], output / assets["png"])
        else:
            rgba = cmap(normalization(np.ma.masked_invalid(values)), bytes=True)
            Image.fromarray(np.flipud(rgba)).save(output / assets["png"])
        valid = np.isfinite(values)
        masks = {"encoding": "packed-bits-base64", "bitOrder": "little", "shape": list(reference_shape),
                 "origin": "FITS bottom-left; row-major y,x", "displayValid": _pack_mask(valid), "scienceValid": _pack_mask(coverage),
                 "semantics": "displayValid is finite DISPLAY coverage; scienceValid is the distinct conservative aligned COVERAGE mask, not the display mask."}
        write_manifest(output / assets["masks"], masks)
        for position in (frame["expectedPosition"], frame["measuredPosition"]):
            if position is not None:
                px, py = WCS(header).all_world2pix(position["raDeg"], position["decDeg"], 0)
                if not np.allclose([px, py], [position["xFits"], position["yFits"]], atol=1e-7, rtol=0):
                    raise ValueError("Recorded temporal position disagrees with the fixed WCS.")
        exported.append({key: value for key, value in frame.items() if key not in ("source", "exactPng", "sourceUrl")} | {
            "assets": assets, "display": dict(display),
            "masks": {"displayValidFraction": float(valid.mean()), "scienceValidFraction": float(coverage.mean()) if coverage is not None else None,
                      "semantics": masks["semantics"], "scienceMaskAvailable": coverage is not None},
            "provenance": {"sourceAlignedFits": frame["source"].relative_to(project).as_posix(),
                           "sourceSha256": hashlib.sha256(frame["source"].read_bytes()).hexdigest(),
                           "sourceUrl": frame["sourceUrl"], "exactPngCopied": frame["exactPng"] is not None},
        })
    report = details["report"]
    raw_motion = report.get("motion")
    motion = None
    if raw_motion is not None:
        references = report.get("background_reference_residuals", {})
        mapping = {"measuredDisplacementArcsec": "measured_displacement_arcsec", "expectedDisplacementArcsec": "expected_displacement_arcsec",
                   "measuredDisplacementPixels": "measured_displacement_pixels", "expectedDisplacementPixels": "expected_displacement_pixels",
                   "formalEndpointErrorArcsec": "formal_endpoint_error_arcsec", "timeSeparationDays": "time_separation_days",
                   "expectedEastNorthArcsec": "expected_east_north_arcsec", "measuredEastNorthArcsec": "measured_east_north_arcsec"}
        motion = {key: raw_motion.get(source) for key, source in mapping.items()}
        if motion["timeSeparationDays"] is None:
            motion["timeSeparationDays"] = float((Time(exported[-1]["observation"]["timestampUtc"], scale="utc") - Time(exported[0]["observation"]["timestampUtc"], scale="utc")).to_value(u.day))
        motion.update({"referenceRmsArcsec": references.get("rms_arcsec"), "referenceCount": references.get("matched_source_count"),
                       "formalErrorWarning": "Formal fit errors are incomplete and exclude instrumental, reference-frame, PSF and photocenter systematics.",
                       "referenceWarning": "Reference RMS is a diagnostic, not a statistical motion-significance denominator.",
                       "significantDetectionClaimed": False, "limitation": raw_motion.get("limitation")})
    warnings = list(field.warnings)
    if field.target_id == "m101":
        releases = sorted({frame["observation"]["release"].upper() for frame in exported})
        if len(releases) > 1:
            warnings += [f"The selected observations belong to different releases ({' and '.join(releases)})."]
        warnings += ["Spectral compatibility is exploratory; quantitative temporal change is not validated."]
    if field.target_id == "epsilon_indi_b":
        warnings += [details["interpretation"], "Formal fit errors differ from total uncertainty; reference RMS is diagnostic, not detection significance."]
    sequence = {"version": 1, "classification": field.classification, "frames": exported, "display": display,
                "warnings": list(dict.fromkeys(warnings)), "motion": motion, "interpretation": details["interpretation"],
                "predictionModel": details["predictionModel"], "astrometricReference": details["astrometricReference"],
                "fixedGrid": {"wcsHeader": dict(reference_wcs), "dimensions": target["dimensions"], "pixelScaleArcsec": field.pixel_scale_arcsec,
                              "pngConvention": "yImage = height - 1 - yFits; north up, east left; no recentering"},
                "sourceManifest": details["sourceManifest"].relative_to(project).as_posix()}
    # Retain the SPX-003A first-frame URLs while making their cuts identical to the sequence.
    for key in ("fits", "png"):
        shutil.copyfile(output / exported[0]["assets"][key], output / target["assets"][key])
    target["display"] = dict(display)
    target["observation"] = dict(exported[0]["observation"])
    target["warnings"] = sequence["warnings"]
    return sequence


def export_web_data(project: Path, output: Path | None = None) -> dict:
    """Reproducibly export real local artifacts; original science files are read-only."""
    project = Path(project).resolve()
    output = Path(output) if output is not None else project / "frontend/public/data"
    fields = prepared_fields(project)
    targets = []
    for field in fields:
        target = export_field(field, output, project)
        target["sequence"] = export_sequence(field, target, project, output)
        targets.append(target)
    catalog = {"version": 1, "coordinateFrame": "ICRS", "targets": targets,
               "notes": ["Global HiPS context and individual SPHEREx observations are distinct image layers.",
                         "Two already processed real epochs per field; fixed WCS, common display limits, no interpolated epochs."]}
    include_brightness_target(project,output,catalog)
    from .change_explorer import include_change_targets
    include_change_targets(project,output,catalog)
    include_challenge_targets(project,output,catalog)
    write_manifest(output / "catalog.json", catalog)
    return catalog


def include_challenge_targets(project,output,catalog):
    """Append only prepared new challenge targets; never acquire data here."""
    project,output=Path(project),Path(output)
    path=project/'outputs/spx006c/extension.json'
    if not path.exists():return catalog
    extension=load_json(path)
    for target in extension['targets']:
        if target['id'] not in {'wise0855','r_dra'}:raise ValueError('Unexpected challenge extension target.')
        for asset in {a for f in target['sequence']['frames'] for a in f['assets'].values()}:
            relative=portable_asset(asset);destination=output/relative;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(project/'outputs/spx006c/web_data'/relative,destination)
        catalog['targets']=[t for t in catalog['targets'] if t['id']!=target['id']]+[target]
    return catalog


def include_brightness_target(project,output,catalog):
    """Append only a prepared SPX-004A derivative; never copy raw scientific inputs."""
    project,output=Path(project),Path(output)
    manifest=project/'outputs/spx004a/web_target.json'
    if not manifest.exists():
        return catalog
    target=load_json(manifest)
    if target['id'] not in {'r_dra','rw_aur'} or not target.get('brightness'):
        raise ValueError('Unexpected prepared brightness field.')
    assets={path for frame in target['sequence']['frames'] for path in frame['assets'].values()}
    for asset in assets:
        relative=portable_asset(asset)
        source=project/'outputs/spx004a/web_data'/relative
        destination=output/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
    catalog['targets']=[t for t in catalog['targets'] if t['id']!=target['id']]+[target]
    write_manifest(output/'catalog.json',catalog)
    return catalog
