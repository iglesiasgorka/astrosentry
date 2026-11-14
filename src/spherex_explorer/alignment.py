"""Fixed-sky TAN reprojection with explicit support and conservative masks."""

from dataclasses import dataclass
import math
from pathlib import Path

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
from reproject import reproject_interp

from .data_access import SearchParameters
from .observation import Observation


@dataclass
class AlignedObservation:
    """Surface-brightness images and separately named interpolation diagnostics."""

    observation: Observation
    wcs: WCS
    image: np.ndarray
    display_image: np.ndarray
    footprint: np.ndarray
    support: np.ndarray
    coverage: np.ndarray
    display_coverage: np.ndarray
    variance_diagnostic: np.ndarray | None
    zodi: np.ndarray | None


def common_grid(ra: float, dec: float, size_deg: float = 0.1,
                pixel_scale_arcsec: float = 6.2) -> tuple[WCS, tuple[int, int]]:
    """Create centered ICRS TAN with north up, east left and no output SIP."""
    SearchParameters(ra, dec, size_deg)
    if not np.isfinite(pixel_scale_arcsec) or pixel_scale_arcsec <= 0:
        raise ValueError("Pixel scale must be a positive finite arcsecond value.")
    side = int(math.ceil(size_deg * 3600 / pixel_scale_arcsec))
    if side < 3 or side > 4096:
        raise ValueError("Requested grid must have 3 through 4096 pixels per side.")
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.radesys = "ICRS"
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.crpix = [(side + 1) / 2, (side + 1) / 2]
    wcs.wcs.cdelt = [-pixel_scale_arcsec / 3600, pixel_scale_arcsec / 3600]
    wcs.array_shape = (side, side)
    return wcs, (side, side)


def masked_reproject(array, invalid, original_wcs, output_wcs, shape,
                     minimum_support: float = 0.999):
    """Bilinear interpolation of valid numerator/support, with no bad-pixel leakage.

    Only outputs with almost full valid interpolation support are retained. The
    footprint is geometric support; support is the interpolated valid indicator.
    Renormalization preserves surface brightness, not integrated pixel flux.
    """
    if not 0 < minimum_support <= 1:
        raise ValueError("Minimum support must lie in (0, 1].")
    valid = ~np.asarray(invalid, dtype=bool) & np.isfinite(array)
    numerator, footprint = reproject_interp((np.where(valid, array, 0.0), original_wcs), output_wcs,
                                          shape_out=shape, order="bilinear", roundtrip_coords=True)
    support, _ = reproject_interp((valid.astype(float), original_wcs), output_wcs,
                                 shape_out=shape, order="bilinear", roundtrip_coords=True)
    covered = (footprint > 0) & np.isfinite(support) & (support >= minimum_support)
    output = np.full(shape, np.nan)
    np.divide(numerator, support, out=output, where=covered)
    return output, np.nan_to_num(footprint), np.nan_to_num(support), covered


def align_observation(observation: Observation, output_wcs: WCS, shape: tuple[int, int]) -> AlignedObservation:
    """Preserve the input spatial SIP; evaluate two explicitly separate masks."""
    if observation.header.get("BUNIT") is None or not u.Unit(observation.header["BUNIT"]).is_equivalent(u.MJy / u.sr):
        raise ValueError("Alignment requires IMAGE surface brightness compatible with MJy/sr.")
    factor = u.Unit(observation.header["BUNIT"]).to(u.MJy / u.sr)
    image, footprint, support, coverage = masked_reproject(
        observation.image * factor, observation.science_invalid, observation.wcs, output_wcs, shape)
    display, _, _, display_coverage = masked_reproject(
        observation.image * factor, observation.display_invalid, observation.wcs, output_wcs, shape)
    def auxiliary(array, variance=False):
        if array is None:
            return None
        invalid = observation.science_invalid | ~np.isfinite(array)
        scale = factor ** 2 if variance else factor
        return masked_reproject(array * scale, invalid, observation.wcs, output_wcs, shape)[0]
    return AlignedObservation(observation, output_wcs, image, display, footprint, support, coverage,
                              display_coverage, auxiliary(observation.variance, True), auxiliary(observation.zodi))


def validate_grid(wcs: WCS, shape: tuple[int, int], center: SkyCoord) -> dict:
    """Check center, axis orientation, angular scale, and roundtrip numerics."""
    x, y = (shape[1] - 1) / 2, (shape[0] - 1) / 2
    actual = wcs.pixel_to_world(x, y)
    right = wcs.pixel_to_world(x + 1, y)
    up = wcs.pixel_to_world(x, y + 1)
    east, north = actual.spherical_offsets_to(right)
    east_up, north_up = actual.spherical_offsets_to(up)
    samples = np.array([[x, y], [1, 1], [shape[1] - 2, shape[0] - 2], [x + 3, y - 3]])
    sky = wcs.pixel_to_world(samples[:, 0], samples[:, 1])
    xx, yy = wcs.world_to_pixel(sky)
    errors = np.hypot(xx - samples[:, 0], yy - samples[:, 1])
    return {"shape": list(shape), "center_error_arcsec": float(actual.separation(center).arcsec),
            "east_left": bool(east.arcsec < 0), "north_up": bool(north_up.arcsec > 0),
            "x_step_arcsec": float(actual.separation(right).arcsec),
            "y_step_arcsec": float(actual.separation(up).arcsec),
            "cross_axis_x_north_arcsec": float(north.arcsec), "cross_axis_y_east_arcsec": float(east_up.arcsec),
            "maximum_roundtrip_error_pixels": float(np.max(errors)), "header": dict(wcs.to_header())}


def save_aligned(aligned: AlignedObservation, path: Path):
    """Save arrays with common WCS and an unambiguous variance warning."""
    header = aligned.wcs.to_header()
    header["BUNIT"] = "MJy / sr"
    header["OBSID"] = aligned.observation.observation_id
    header["HISTORY"] = "Fixed-sky bilinear reprojection; input spatial SIP preserved."
    hdus = [fits.PrimaryHDU(), fits.ImageHDU(aligned.image, header=header, name="IMAGE"),
            fits.ImageHDU(aligned.display_image, header=header, name="DISPLAY"),
            fits.ImageHDU(aligned.footprint, header=aligned.wcs.to_header(), name="FOOTPRINT"),
            fits.ImageHDU(aligned.support, header=aligned.wcs.to_header(), name="SUPPORT"),
            fits.ImageHDU(aligned.coverage.astype(np.uint8), header=aligned.wcs.to_header(), name="COVERAGE")]
    if aligned.variance_diagnostic is not None:
        variance_header = aligned.wcs.to_header()
        variance_header["BUNIT"] = "MJy2 / sr2"
        variance_header["HISTORY"] = "Interpolated variance diagnostic only; NOT propagated uncertainty."
        hdus.append(fits.ImageHDU(aligned.variance_diagnostic, header=variance_header, name="VAR_DIAG"))
    if aligned.zodi is not None:
        hdus.append(fits.ImageHDU(aligned.zodi, header=header, name="ZODI"))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList(hdus).writeto(path, overwrite=True)
