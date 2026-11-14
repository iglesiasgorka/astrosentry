"""Portable, relative assets and explicit scientific classification for a viewer."""

from pathlib import Path, PurePosixPath

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from .fits_utils import write_manifest
from .sequence_visualization import common_normalization

CLASSIFICATION_RULES = {
    "scientifically usable": "Requires validated astrometric uncertainties/systematics and response/PSF review; this pipeline does not automatically grant this classification.",
    "exploratory": "At least two accepted centroids at separated epochs in one detector/release, with every wavelength pair within half the narrower local bandwidth; systematics remain unvalidated.",
    "diagnostic": "Real data exist, but no accepted compatible centroid pair is available. Frames do not demonstrate a measured motion.",
    "unavailable": "No processed real frames are available.",
}


def relative_asset(value):
    """Reject host-specific or escaping paths in the public manifest."""
    value = str(value)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value or not value:
        raise ValueError(f"Asset paths must be relative portable paths: {value}")
    return path.as_posix()


def write_sequence_manifest(output, target, center, wcs, shape, scale, items, records,
                            classification, warnings):
    """Write exact-grid PNGs and JSON without local filesystem paths.

    PNG row zero is north/top; scientific FITS/WCS pixel coordinates have y=0 at
    the bottom. Both conventions are provided explicitly for position overlays.
    """
    if classification not in CLASSIFICATION_RULES:
        raise ValueError("Unknown sequence classification.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    norm = common_normalization([item.display_image for item in items])
    cmap = plt.get_cmap("gray").with_extremes(bad="#683a68")
    frames = []
    ordered = sorted(zip(items, records), key=lambda pair: pair[1]["midpoint_mjd"])
    for item, record in ordered:
        stem = f"{record['observation_id']}D{int(record['detector'])}"
        image_asset = relative_asset(f"frames/{stem}.png")
        aligned_asset = relative_asset(record["aligned_asset"])
        (output / "frames").mkdir(exist_ok=True)
        rgba = cmap(norm(np.ma.masked_invalid(item.display_image)), bytes=True)
        Image.fromarray(np.flipud(rgba)).save(output / image_asset)
        measured = record["target_centroid"]
        def position(x, y, ra, dec):
            return {"ra_deg": ra, "dec_deg": dec, "x_fits": x, "y_fits": y,
                    "x_image": x, "y_image": shape[0] - 1 - y}
        expected = position(measured["expected_x"], measured["expected_y"],
                            measured["expected_ra_deg"], measured["expected_dec_deg"])
        fit = measured["measurement"]
        observed = position(measured["measured_x"], measured["measured_y"], fit["ra_deg"], fit["dec_deg"]) if fit["accepted"] else None
        quality_warnings = []
        if not fit["accepted"]:
            quality_warnings.append(fit.get("reason") or "Centroid rejected.")
        if set(record.get("target_quality", {}).get("flag_pixel_counts", {})) - {"SOURCE", "FULLSAMPLE"}:
            quality_warnings.append("Local core FLAGS are recorded in observations.json; SOURCE is not automatically invalid.")
        frames.append({"observation_id": record["observation_id"], "timestamp_utc": record["midpoint_utc"],
                       "timestamp_kind": "FITS observation midpoint, UTC", "start_utc": record["start_utc"],
                       "effective_wavelength_um": record["wavelength_um"], "bandwidth_um": record["bandwidth_um"],
                       "detector": f"SPHEREx-D{int(record['detector'])}", "release": record["release"],
                       "processing_version": record["processing_version"],
                       "assets": {"image": image_asset, "aligned_fits": aligned_asset},
                       "quality_warnings": quality_warnings, "centroid_accepted": bool(fit["accepted"]),
                       "expected_position": expected, "measured_position": observed,
                       "formal_centroid_error_original_pixels": fit.get("formal_error_pixels")})
    manifest = {"schema_version": 1, "target_id": target["key"], "display_name": target["name"],
                "fixed_field_center": {"ra_deg": float(center.ra.deg), "dec_deg": float(center.dec.deg), "frame": "ICRS"},
                "angular_pixel_scale_arcsec": scale, "image_dimensions": {"width": shape[1], "height": shape[0]},
                "pixel_convention": "Zero-based WCS/FITS x,y has y increasing north; PNG x_image,y_image origin is top left.",
                "orientation": "North up, east left; fixed celestial grid, no target recentering.",
                "wcs_header": dict(wcs.to_header()), "units": "MJy/sr",
                "display_stretch": {"method": "Common 0.5/99.5 percentiles with asinh", "vmin": float(norm.vmin), "vmax": float(norm.vmax),
                                    "invalid_color": "#683a68", "source_array": "DISPLAY; not the conservative science mask"},
                "sequence_classification": classification, "classification_reason": CLASSIFICATION_RULES[classification],
                "classification_rules": CLASSIFICATION_RULES, "quality_warnings": list(warnings),
                "prediction_model": "Linear catalog proper motion; annual parallax, perspective and orbital effects omitted.",
                "assets": {"blink": "blink.gif", "overview": "aligned_overview.png", "positions": "motion_positions.png"} if frames else {},
                "frames": frames}
    write_manifest(output / "sequence_manifest.json", manifest)
    return manifest
