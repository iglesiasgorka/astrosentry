"""Inspect actual SPHEREx HDUs and preserve missing metadata explicitly."""

import json
import math
from pathlib import Path

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np

EXPECTED_HDUS = ("PRIMARY", "IMAGE", "FLAGS", "VARIANCE", "ZODI", "EPSF", "WCS-WAVE")
DISPLAY_BAD_FLAGS = {"NONFUNC", "MISSING_DATA", "OVERFLOW", "SUR_ERROR", "NONLINEAR", "HOT", "COLD"}


def validate_fits(path: Path) -> None:
    """Read every HDU and reject invalid FITS or complete detector IMAGE arrays."""
    with fits.open(path, memmap=False) as hdus:
        hdus.verify("exception")
        for hdu in hdus:
            _ = hdu.data
        if "IMAGE" not in hdus or hdus["IMAGE"].data is None:
            raise ValueError(f"FITS has no IMAGE data: {path}")
        shape = hdus["IMAGE"].data.shape
        if len(shape) != 2 or any(side >= 2040 for side in shape):
            raise ValueError(f"Expected a 2D cutout smaller than the detector, got {shape}: {path}")


def flag_information(hdu) -> dict:
    """Decode bit names and descriptions from MSKN/MSKD cards, without guessing."""
    data = hdu.data
    definitions = []
    for key in hdu.header:
        if key.startswith("MSKN") and key[4:].isdigit():
            bit = int(key[4:])
            definitions.append({
                "bit": bit, "name": hdu.header[key],
                "description": hdu.header.get("MSKD" + key[4:]),
                "pixel_count": int(np.count_nonzero(data & (1 << bit))) if data is not None else None,
            })
    return {
        "definitions": definitions,
        "nonzero_fraction": float(np.count_nonzero(data) / data.size) if data is not None and data.size else None,
        "note": "Nonzero flags include SOURCE and do not all mean invalid pixels.",
    }


def display_mask(hdus) -> np.ndarray:
    """Mask nonfinite IMAGE pixels and explicitly named severe quality bits."""
    image = hdus["IMAGE"].data
    mask = ~np.isfinite(image)
    if "FLAGS" in hdus and hdus["FLAGS"].data is not None and hdus["FLAGS"].data.shape == image.shape:
        for definition in flag_information(hdus["FLAGS"])["definitions"]:
            if definition["name"] in DISPLAY_BAD_FLAGS:
                mask |= (hdus["FLAGS"].data & (1 << definition["bit"])) != 0
    return mask


def inspect_fits(path: Path, ra: float, dec: float) -> dict:
    """Inspect HDUs and evaluate spatial then alternate spectral WCS at ICRS RA/DEC."""
    validate_fits(path)
    result = {"errors": [], "extensions": [], "observation_id": None,
              "processing_version": None, "detector": None, "image_units": None,
              "effective_wavelength_um": None, "spectral_bandwidth_um": None,
              "spatial_wcs": None, "target_pixel": None, "quality_flags": None}
    with fits.open(path, memmap=False) as hdus:
        names = [hdu.name for hdu in hdus]
        result["missing_extensions"] = [name for name in EXPECTED_HDUS if name not in names]
        for hdu in hdus:
            entry = {"name": hdu.name, "type": type(hdu).__name__,
                     "shape": list(hdu.data.shape) if hdu.data is not None else None,
                     "dtype": str(hdu.data.dtype) if hdu.data is not None else None,
                     "units": hdu.header.get("BUNIT")}
            if isinstance(hdu, fits.BinTableHDU):
                entry["columns"] = [{"name": c.name, "format": c.format,
                                      "unit": c.unit, "dim": c.dim} for c in hdu.columns]
            result["extensions"].append(entry)
        header = hdus["IMAGE"].header
        image = hdus["IMAGE"].data
        result.update(observation_id=header.get("OBSID"),
                      processing_version=hdus[0].header.get("VERSION"),
                      detector=header.get("DETECTOR"), image_units=header.get("BUNIT"),
                      image_shape=list(image.shape),
                      finite_pixel_fraction=float(np.isfinite(image).mean()),
                      display_valid_pixel_fraction=float((~display_mask(hdus)).mean()))
        # DATE is a processing/file date in some products, never an observation fallback.
        result["header_time_metadata"] = {
            key: {"value": header[key], "comment": header.comments[key]}
            for key in header if key.startswith(("DATE", "MJD")) or key in {"TIMESYS", "TIMEUNIT", "TREFPOS"}
        }
        result["observation_timestamp"] = header.get("DATE-OBS")
        result["observation_mjd"] = header.get("MJD-OBS")
        for name in ("FLAGS", "VARIANCE", "ZODI"):
            if name in hdus and hdus[name].data is not None and hdus[name].data.shape != image.shape:
                result["errors"].append(f"{name} shape differs from IMAGE.")
        if "FLAGS" in hdus:
            result["quality_flags"] = flag_information(hdus["FLAGS"])
        for key in ("observation_id", "processing_version", "detector", "image_units"):
            if result[key] is None:
                result["errors"].append(f"Missing FITS metadata: {key}.")
        try:
            spatial = WCS(header)
            if not spatial.has_celestial:
                raise ValueError("IMAGE has no celestial WCS.")
            result["spatial_wcs"] = dict(spatial.to_header(relax=True))
            coordinate = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
            x, y = (float(value) for value in spatial.world_to_pixel(coordinate))
            result["target_pixel"] = [x, y]
            if not (math.isfinite(x) and math.isfinite(y) and
                    -0.5 <= x < image.shape[1] - 0.5 and -0.5 <= y < image.shape[0] - 0.5):
                raise ValueError("Selected sky coordinate lies outside the IMAGE cutout.")
            spectral = WCS(header, fobj=hdus, key="W")
            spectral.sip = None
            wavelength, bandwidth = spectral.pixel_to_world(x, y)
            wavelength = float(wavelength.to_value(u.um))
            bandwidth = float(bandwidth.to_value(u.um))
            if not all(math.isfinite(v) and v > 0 for v in (wavelength, bandwidth)):
                raise ValueError("Spectral WCS returned nonpositive or nonfinite values.")
            result.update(effective_wavelength_um=wavelength, spectral_bandwidth_um=bandwidth)
        except (ValueError, KeyError, TypeError, IndexError, RuntimeError) as error:
            result["errors"].append(f"WCS evaluation failed: {type(error).__name__}: {error}")
    return json_safe(result)


def json_safe(value):
    """Convert nested scientific scalars and nonfinite values to strict JSON."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_manifest(path: Path, manifest: dict) -> None:
    """Write a strict JSON manifest atomically, preserving explicit nulls."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.part")
    temporary.write_text(json.dumps(json_safe(manifest), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def assess_spectral_pairs(observations: list[dict]) -> dict:
    """Screen pairs by half the narrower local bandwidth; this is only a heuristic."""
    pairs = []
    for index, first in enumerate(observations):
        for second in observations[index + 1:]:
            a, b = first.get("inspection", {}), second.get("inspection", {})
            values = [a.get("effective_wavelength_um"), b.get("effective_wavelength_um"),
                      a.get("spectral_bandwidth_um"), b.get("spectral_bandwidth_um")]
            if any(v is None or not math.isfinite(v) or v <= 0 for v in values):
                continue
            dt = abs(first["mjd"] - second["mjd"])
            if dt <= 0 or first["timestamp"][:10] == second["timestamp"][:10]:
                continue
            delta = abs(values[0] - values[1])
            threshold = 0.5 * min(values[2:])
            pairs.append({"observation_ids": [first["observation_id"], second["observation_id"]],
                          "time_separation_days": dt, "wavelength_separation_um": delta,
                          "threshold_um": threshold, "separation_in_narrower_bandwidths": delta / min(values[2:]),
                          "passes_heuristic": delta <= threshold})
    similar = [pair for pair in pairs if pair["passes_heuristic"]]
    return {"criterion": "Different UTC calendar dates; delta wavelength <= 0.5 * min(local bandwidths).",
            "scientifically_comparable": None,
            "caution": "Candidate screening only; registration, PSF, calibration, backgrounds and quality require review.",
            "evaluated_pair_count": len(pairs), "similar_pair_count": len(similar),
            "widest_temporal_candidate": max(similar, key=lambda p: p["time_separation_days"]) if similar else None,
            "closest_spectral_pair": min(pairs, key=lambda p: p["separation_in_narrower_bandwidths"]) if pairs else None}
