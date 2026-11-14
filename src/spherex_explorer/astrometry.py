"""Diagnostic stellar centroid fitting, background references, and known motion."""

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
import numpy as np
from scipy.ndimage import maximum_filter, gaussian_filter
from scipy.optimize import least_squares

from .targets import predict_position


def fit_centroid(observation, coordinate: SkyCoord, radius=4, search_radius=2.0) -> dict:
    """Fit a local circular Gaussian plus plane in original, unresampled pixels.

    Uses input VARIANCE and conservative science flags; formal fit covariance is
    not a calibrated total astrometric error (PSF/systematic terms remain).
    """
    result = {"accepted": False, "reason": None, "ra_deg": None, "dec_deg": None,
              "x_original": None, "y_original": None, "formal_error_pixels": None, "formal_error_arcsec": None}
    x0, y0 = (float(v) for v in observation.wcs.world_to_pixel(coordinate))
    if not np.isfinite(x0 + y0):
        result["reason"] = "Nonfinite search coordinate."
        return result
    cx, cy = int(round(x0)), int(round(y0))
    if cx - radius < 0 or cy - radius < 0 or cx + radius >= observation.image.shape[1] or cy + radius >= observation.image.shape[0]:
        result["reason"] = "Search region reaches a cutout edge."
        return result
    section = np.s_[cy-radius:cy+radius+1, cx-radius:cx+radius+1]
    data = observation.image[section]
    bad = observation.science_invalid[section]
    yy, xx = np.indices(data.shape, dtype=float)
    xx += cx - radius
    yy += cy - radius
    valid = ~bad & np.isfinite(data)
    core = observation.science_invalid[cy-1:cy+2, cx-1:cx+2]
    result["valid_fraction"] = float(valid.mean())
    result["core_valid_fraction"] = float((~core).mean())
    if observation.variance is None or valid.sum() < 30 or result["core_valid_fraction"] < 0.75:
        result["reason"] = "Insufficient unflagged pixels or contaminated 3x3 target core."
        return result
    variance = observation.variance[section]
    valid &= np.isfinite(variance) & (variance > 0)
    background = float(np.median(data[valid]))
    peak = float(np.max(data[valid]) - background)
    if peak <= 0:
        result["reason"] = "No positive local source contrast."
        return result
    x, y, z, noise = xx[valid], yy[valid], data[valid], np.sqrt(variance[valid])
    def residual(p):
        amplitude, xc, yc, sigma, offset, sx, sy = p
        model = offset + sx * (x - x0) + sy * (y - y0) + amplitude * np.exp(-((x-xc)**2+(y-yc)**2)/(2*sigma**2))
        return (model - z) / noise
    initial = [peak, x0, y0, 0.8, background, 0, 0]
    fit = least_squares(residual, initial,
                        bounds=([0, x0-search_radius, y0-search_radius, 0.35, -np.inf, -np.inf, -np.inf],
                                [np.inf, x0+search_radius, y0+search_radius, 2.0, np.inf, np.inf, np.inf]),
                        max_nfev=300)
    amplitude, xfit, yfit, sigma, offset, sx, sy = fit.x
    dof = len(z) - len(fit.x)
    reduced = float(np.sum(fit.fun**2) / max(dof, 1))
    snr = float(amplitude / np.median(noise))
    rms = float(np.sqrt(np.mean((fit.fun * noise)**2)))
    mismatch = rms / amplitude if amplitude else np.inf
    result.update(sigma_pixels=float(sigma), peak_snr=snr, reduced_chi2=reduced,
                  residual_rms_over_peak=float(mismatch))
    boundary = abs(xfit-x0) > 0.95*search_radius or abs(yfit-y0) > 0.95*search_radius
    if not fit.success or boundary or sigma < 0.36 or sigma > 1.95 or snr < 8 or mismatch > 0.25:
        result["reason"] = "Local fit fails convergence, shape, search-boundary, SNR or residual criteria."
        return result
    try:
        covariance = np.linalg.inv(fit.jac.T @ fit.jac) * max(reduced, 1.0)
        formal = float(np.sqrt(max(covariance[1, 1], covariance[2, 2])))
    except np.linalg.LinAlgError:
        result["reason"] = "Singular local centroid covariance."
        return result
    if not np.isfinite(formal) or formal > 0.5:
        result["reason"] = "Formal centroid uncertainty is too large."
        return result
    sky = observation.wcs.pixel_to_world(xfit, yfit).icrs
    angular_error = max(sky.separation(observation.wcs.pixel_to_world(xfit+formal, yfit)).arcsec,
                        sky.separation(observation.wcs.pixel_to_world(xfit, yfit+formal)).arcsec)
    result.update(accepted=True, x_original=float(xfit), y_original=float(yfit),
                  ra_deg=float(sky.ra.deg), dec_deg=float(sky.dec.deg), formal_error_pixels=formal,
                  formal_error_arcsec=float(angular_error),
                  uncertainty_note="Formal Gaussian/plane fit only; does not include PSF mismatch, catalog epoch propagation or WCS systematics.")
    return result


def reference_candidates(aligned, exclude=None, maximum=30):
    """Find isolated local peaks solely for registration diagnostics, not motion discovery."""
    array = aligned.display_image
    finite = np.isfinite(array)
    if finite.sum() < 30:
        return []
    baseline = np.median(array[finite])
    smooth = gaussian_filter(np.where(finite, array, baseline), 0.6)
    residual = smooth - gaussian_filter(smooth, 3)
    scatter = 1.4826 * np.median(np.abs(residual[finite] - np.median(residual[finite])))
    maxima = (residual == maximum_filter(residual, size=7)) & finite & (residual > max(5*scatter, 1e-8))
    yy, xx = np.where(maxima)
    indices = sorted(range(len(xx)), key=lambda i: residual[yy[i], xx[i]], reverse=True)
    coordinates = []
    for index in indices:
        x, y = int(xx[index]), int(yy[index])
        if min(x, y, array.shape[1]-1-x, array.shape[0]-1-y) < 6:
            continue
        sky = aligned.wcs.pixel_to_world(x, y)
        if exclude is not None and sky.separation(exclude).arcsec < 35:
            continue
        coordinates.append(sky)
        if len(coordinates) >= maximum:
            break
    return coordinates


def alignment_residuals(first, second, pixel_scale_arcsec, exclude=None) -> dict:
    """Independently fit matched reference sources; report, never remove, residual shifts."""
    coordinates = reference_candidates(first, exclude)
    matches, rejected = [], []
    for sky in coordinates:
        a = fit_centroid(first.observation, sky)
        b = fit_centroid(second.observation, sky)
        if not a["accepted"] or not b["accepted"]:
            rejected.append({"ra_deg": float(sky.ra.deg), "dec_deg": float(sky.dec.deg),
                             "first": a, "second": b})
            continue
        sa = SkyCoord(a["ra_deg"]*u.deg, a["dec_deg"]*u.deg)
        sb = SkyCoord(b["ra_deg"]*u.deg, b["dec_deg"]*u.deg)
        xa, ya = first.wcs.world_to_pixel(sa)
        xb, yb = first.wcs.world_to_pixel(sb)
        separation = float(sa.separation(sb).arcsec)
        if separation > 2 * pixel_scale_arcsec:
            rejected.append({"reason": "Centroids separated by more than two output pixels.", "first": a, "second": b})
            continue
        matches.append({"first": a, "second": b, "dx_pixels": float(xb-xa), "dy_pixels": float(yb-ya),
                        "separation_arcsec": separation, "separation_pixels": float(np.hypot(xb-xa, yb-ya))})
    reliable = len(matches) >= 3
    result = {"candidate_count": len(coordinates), "matched_source_count": len(matches),
              "minimum_sources_for_summary": 3, "reliable_multi_source_residual": reliable,
              "matches": matches, "rejected": rejected,
              "rms_pixels": None, "rms_arcsec": None, "median_dx_pixels": None, "median_dy_pixels": None,
              "limitation": "Relative image diagnostic; no external absolute astrometric certification or extra source-derived shift was applied."}
    if reliable:
        result.update(rms_pixels=float(np.sqrt(np.mean([r["separation_pixels"]**2 for r in matches]))),
                      rms_arcsec=float(np.sqrt(np.mean([r["separation_arcsec"]**2 for r in matches]))),
                      median_dx_pixels=float(np.median([r["dx_pixels"] for r in matches])),
                      median_dy_pixels=float(np.median([r["dy_pixels"] for r in matches])))
    else:
        result["limitation"] += " Fewer than three accepted background sources; no reliable residual estimate."
    return result


def measure_known_target(aligned, target):
    """Report predicted and measured positions separately on the unchanged sky grid."""
    observation = aligned.observation
    if observation.midpoint is None:
        return {"observation_id": observation.observation_id, "error": "Missing observation midpoint."}
    expected = predict_position(target, observation.midpoint)
    measured = fit_centroid(observation, expected)
    x, y = aligned.wcs.world_to_pixel(expected)
    result = {"observation_id": observation.observation_id, "midpoint_utc": observation.midpoint.utc.isot,
              "expected_ra_deg": float(expected.ra.deg), "expected_dec_deg": float(expected.dec.deg),
              "expected_x": float(x), "expected_y": float(y), "measurement": measured,
              "measured_x": None, "measured_y": None, "expected_measured_separation_arcsec": None}
    if measured["accepted"]:
        position = SkyCoord(measured["ra_deg"]*u.deg, measured["dec_deg"]*u.deg)
        mx, my = aligned.wcs.world_to_pixel(position)
        result.update(measured_x=float(mx), measured_y=float(my),
                      expected_measured_separation_arcsec=float(expected.separation(position).arcsec))
    return result


def motion_summary(measurements, pixel_scale_arcsec):
    """Separate expected full-baseline displacement from measured accepted endpoints."""
    if len(measurements) < 2:
        return {"expected_displacement_arcsec": None, "measured_displacement_arcsec": None,
                "limitation": "Fewer than two epochs."}
    first, last = measurements[0], measurements[-1]
    expected_a = SkyCoord(first["expected_ra_deg"]*u.deg, first["expected_dec_deg"]*u.deg)
    expected_b = SkyCoord(last["expected_ra_deg"]*u.deg, last["expected_dec_deg"]*u.deg)
    result = {"endpoint_observation_ids": [first["observation_id"], last["observation_id"]],
              "time_separation_days": float((Time(last["midpoint_utc"]) - Time(first["midpoint_utc"])).to_value("day")),
              "expected_displacement_arcsec": float(expected_a.separation(expected_b).arcsec),
              "expected_displacement_pixels": float(np.hypot(last["expected_x"]-first["expected_x"], last["expected_y"]-first["expected_y"])),
              "accepted_centroid_count": sum(r["measurement"]["accepted"] for r in measurements),
              "measured_displacement_arcsec": None, "measured_displacement_pixels": None,
              "formal_endpoint_error_arcsec": None, "qualitative_direction_cosine": None,
              "limitation": "Linear proper motion only: annual parallax, perspective acceleration, orbital effects and observer location are omitted. Formal centroid errors exclude systematics."}
    if first["measurement"]["accepted"] and last["measurement"]["accepted"]:
        ma, mb = first["measurement"], last["measurement"]
        a = SkyCoord(ma["ra_deg"]*u.deg, ma["dec_deg"]*u.deg)
        b = SkyCoord(mb["ra_deg"]*u.deg, mb["dec_deg"]*u.deg)
        expected_vector = np.array([last["expected_x"]-first["expected_x"], last["expected_y"]-first["expected_y"]])
        measured_vector = np.array([last["measured_x"]-first["measured_x"], last["measured_y"]-first["measured_y"]])
        result.update(measured_displacement_arcsec=float(a.separation(b).arcsec),
                      measured_displacement_pixels=float(np.linalg.norm(measured_vector)),
                      formal_endpoint_error_arcsec=float(np.hypot(ma.get("formal_error_arcsec", ma["formal_error_pixels"]*pixel_scale_arcsec),
                                                                 mb.get("formal_error_arcsec", mb["formal_error_pixels"]*pixel_scale_arcsec))),
                      qualitative_direction_cosine=float(np.dot(expected_vector, measured_vector)/max(np.linalg.norm(expected_vector)*np.linalg.norm(measured_vector), 1e-15)))
        expected_east, expected_north = expected_a.spherical_offsets_to(expected_b)
        measured_east, measured_north = a.spherical_offsets_to(b)
        result["expected_east_north_arcsec"] = [float(expected_east.arcsec), float(expected_north.arcsec)]
        result["measured_east_north_arcsec"] = [float(measured_east.arcsec), float(measured_north.arcsec)]
        result["observed_minus_expected_east_north_arcsec"] = [float((measured_east-expected_east).arcsec), float((measured_north-expected_north).arcsec)]
    return result
