"""Original FITS observations, explicit quality policies, and local spectral metadata."""

from dataclasses import dataclass
from pathlib import Path

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
import numpy as np

from .fits_utils import display_mask, flag_information, validate_fits


@dataclass
class Observation:
    """In-memory cutout arrays with the complete original spatial WCS, including SIP."""

    path: Path
    observation_id: str
    release: str | None
    header: fits.Header
    primary_header: fits.Header
    image: np.ndarray
    flags: np.ndarray | None
    variance: np.ndarray | None
    zodi: np.ndarray | None
    wcs: WCS
    start: Time | None
    midpoint: Time | None
    display_invalid: np.ndarray
    science_invalid: np.ndarray
    quality_metadata: dict
    epsf_metadata: dict | None

    @classmethod
    def read(cls, path: Path, release: str | None = None):
        """Read scientific inputs from FITS; never use a diagnostic PNG."""
        path = Path(path)
        validate_fits(path)
        with fits.open(path, memmap=False) as hdus:
            header = hdus["IMAGE"].header.copy()
            image = np.array(hdus["IMAGE"].data, dtype=float)
            arrays = {name: np.array(hdus[name].data, copy=True) if name in hdus and hdus[name].data is not None else None
                      for name in ("FLAGS", "VARIANCE", "ZODI")}
            for name, array in arrays.items():
                if array is not None and array.shape != image.shape:
                    raise ValueError(f"{name} shape differs from IMAGE in {path}")
            flags, variance = arrays["FLAGS"], arrays["VARIANCE"]
            quality = flag_information(hdus["FLAGS"]) if flags is not None else {"definitions": []}
            # SOURCE is a known source, FULLSAMPLE indicates available read history.
            # Unknown/unclassified set bits are rejected by this conservative policy.
            allowed = 0
            for definition in quality["definitions"]:
                if definition["name"] in {"SOURCE", "FULLSAMPLE"}:
                    allowed |= 1 << definition["bit"]
            invalid = ~np.isfinite(image)
            if flags is None:
                invalid[:] = True
            else:
                invalid |= (flags.astype(np.uint32) & np.uint32(0xFFFFFFFF ^ allowed)) != 0
            if variance is None:
                invalid[:] = True
            else:
                invalid |= ~np.isfinite(variance) | (variance <= 0)
            quality.update(science_policy="Reject all set bits except SOURCE/FULLSAMPLE; require finite IMAGE and positive finite VARIANCE.",
                           science_valid_fraction=float((~invalid).mean()),
                           display_policy="SPX-001 severe flag display mask; not a quantitative science mask.")
            epsf = None
            if "EPSF" in hdus:
                hdu = hdus["EPSF"]
                epsf = {"rows": len(hdu.data) if hdu.data is not None else 0,
                        "columns": list(hdu.columns.names),
                        "metadata": {k: hdu.header[k] for k in ("OVSMPX", "OVSMPY", "DETECTOR") if k in hdu.header}}
            def read_time(mjd_key, date_key):
                if mjd_key in header:
                    return Time(header[mjd_key], format="mjd", scale=str(header.get("TIMESYS", "UTC")).lower())
                if date_key in header:
                    return Time(header[date_key], scale=str(header.get("TIMESYS", "UTC")).lower())
                return None
            start = read_time("MJD-OBS", "DATE-OBS")
            midpoint = read_time("MJD-AVG", "DATE-AVG")
            if midpoint is None:
                end = read_time("MJD-END", "DATE-END")
                if start is not None and end is not None:
                    midpoint = start + (end - start) / 2
            return cls(path, header.get("OBSID"), release, header, hdus[0].header.copy(), image,
                       flags, variance, arrays["ZODI"], WCS(header), start, midpoint,
                       display_mask(hdus), invalid, quality, epsf)

    def spectral_at(self, coordinate: SkyCoord) -> dict:
        """Evaluate wavelength and bandwidth at an ICRS position using official WCS W."""
        result = {"ra_deg": float(coordinate.icrs.ra.deg), "dec_deg": float(coordinate.icrs.dec.deg),
                  "wavelength_um": None, "bandwidth_um": None, "error": None}
        try:
            x, y = self.wcs.world_to_pixel(coordinate)
            if not (-0.5 <= x < self.image.shape[1] - 0.5 and -0.5 <= y < self.image.shape[0] - 0.5):
                raise ValueError("Coordinate is outside the cutout.")
            with fits.open(self.path, memmap=False) as hdus:
                spectral = WCS(self.header, key="W", fobj=hdus)
                spectral.sip = None
                wavelength, bandwidth = spectral.pixel_to_world(x, y)
                values = float(wavelength.to_value(u.um)), float(bandwidth.to_value(u.um))
                if not all(np.isfinite(v) and v > 0 for v in values):
                    raise ValueError("Spectral WCS returned invalid values.")
                result.update(wavelength_um=values[0], bandwidth_um=values[1])
        except (ValueError, KeyError, TypeError, RuntimeError) as error:
            result["error"] = f"{type(error).__name__}: {error}"
        return result

    def metadata(self) -> dict:
        """Small serializable metadata; arrays and EPSF pixels stay outside JSON."""
        return {"observation_id": self.observation_id, "release": self.release,
                "local_path": str(self.path.resolve()), "start_utc": self.start.utc.isot if self.start is not None else None,
                "midpoint_utc": self.midpoint.utc.isot if self.midpoint is not None else None,
                "midpoint_mjd": float(self.midpoint.utc.mjd) if self.midpoint is not None else None,
                "units": self.header.get("BUNIT"), "detector": self.header.get("DETECTOR"),
                "shape": list(self.image.shape), "has_spatial_sip": self.wcs.sip is not None,
                "primary_version": self.primary_header.get("VERSION"),
                "quality": self.quality_metadata, "epsf": self.epsf_metadata}

    def quality_at(self, coordinate: SkyCoord, radius=1) -> dict:
        """Report actual local flag counts and finite fractions, independent of a fit."""
        x, y = self.wcs.world_to_pixel(coordinate)
        if not np.isfinite(x + y):
            return {"error": "Nonfinite target pixel."}
        x, y = int(round(float(x))), int(round(float(y)))
        if x-radius < 0 or y-radius < 0 or x+radius >= self.image.shape[1] or y+radius >= self.image.shape[0]:
            return {"error": "Target quality aperture reaches a cutout edge."}
        section = np.s_[y-radius:y+radius+1, x-radius:x+radius+1]
        counts = {}
        for definition in self.quality_metadata["definitions"]:
            count = int(np.count_nonzero(self.flags[section] & (1 << definition["bit"])))
            if count:
                counts[definition["name"]] = count
        return {"pixel_center": [x, y], "radius_pixels": radius, "flag_pixel_counts": counts,
                "finite_fraction": float(np.isfinite(self.image[section]).mean()),
                "science_valid_fraction": float((~self.science_invalid[section]).mean()),
                "display_valid_fraction": float((~self.display_invalid[section]).mean()), "error": None}
