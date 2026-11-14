"""SPX-002 orchestration using original FITS and isolated output directories."""

import hashlib
import json
import logging
from pathlib import Path
import shutil
import re

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
import numpy as np

from .alignment import common_grid, align_observation, validate_grid, save_aligned
from .astrometry import alignment_residuals, measure_known_target, motion_summary
from .data_access import download_cutout, select_observations
from .fits_utils import write_manifest
from .observation import Observation
from .sequence_visualization import plot_aligned_overview, plot_before_after, write_blink, plot_motion
from .targets import epoch_groups, predict_position, select_spectral_sequence

LOGGER = logging.getLogger(__name__)
METHOD = {
    "reprojection": "reproject_interp bilinear with full original spatial WCS/SIP; fixed ICRS TAN output.",
    "mask_handling": "Interpolate zero-filled valid numerator and valid indicator separately; divide only at support >= 0.999.",
    "units": "MJy/sr surface brightness; no pixel area flux scaling.",
    "variance": "VAR_DIAG is interpolated variance, not propagated uncertainty; interpolation squared weights and covariances are NOT modeled.",
    "display": "Separate severe-flags mask; common percentile/asinh normalization for all comparison frames.",
    "not_applied": "No target recentering, source-derived registration correction, PSF matching, ZODI subtraction, background or gain matching.",
}


def build_alignment_report(items, center, shape, scale):
    if not items:
        raise ValueError("No observations to report.")
    all_geometry = np.logical_and.reduce([item.footprint > 0 for item in items])
    all_science = np.logical_and.reduce([item.coverage for item in items])
    all_display = np.logical_and.reduce([item.display_coverage for item in items])
    original_checks = []
    for item in items:
        obs = item.observation
        yy, xx = np.indices(obs.image.shape)
        xs, ys = xx[::10, ::10].ravel(), yy[::10, ::10].ravel()
        sky = obs.wcs.pixel_to_world(xs, ys)
        xr, yr = obs.wcs.world_to_pixel(sky)
        original_checks.append({"observation_id": obs.observation_id,
                                "has_sip": obs.wcs.sip is not None,
                                "max_original_wcs_roundtrip_pixels": float(np.nanmax(np.hypot(xr-xs, yr-ys))),
                                "geometric_coverage_fraction": float((item.footprint > 0).mean()),
                                "science_coverage_fraction": float(item.coverage.mean()),
                                "display_coverage_fraction": float(item.display_coverage.mean())})
    return {"method": METHOD, "grid": validate_grid(items[0].wcs, shape, center),
            "pixel_scale_arcsec": scale, "observation_count": len(items),
            "common_geometric_coverage_fraction": float(all_geometry.mean()),
            "common_science_coverage_fraction": float(all_science.mean()),
            "common_display_coverage_fraction": float(all_display.mean()),
            "original_wcs_checks": original_checks,
            "observations": [item.observation.metadata() for item in items]}


def run_m101(project: Path, output: Path, pixel_scale_arcsec=6.2):
    """Align all eight SPX-001 files without modifying their inputs or outputs."""
    source = json.loads((project / "outputs/observations.json").read_text(encoding="utf-8"))
    center = SkyCoord(source["parameters"]["ra"]*u.deg, source["parameters"]["dec"]*u.deg)
    grid, shape = common_grid(center.ra.deg, center.dec.deg, source["parameters"]["size"], pixel_scale_arcsec)
    output.mkdir(parents=True, exist_ok=True)
    items = []
    for record in source["observations"]:
        observation = Observation.read(Path(record["local_path"]), record["release"])
        aligned = align_observation(observation, grid, shape)
        save_aligned(aligned, output / "aligned" / f"{observation.observation_id}.fits")
        items.append(aligned)
    pair_ids = ["2025W19_2B_0346_1", "2026W26_1A_0500_1"]
    by_id = {item.observation.observation_id: item for item in items}
    pair = [by_id[key] for key in pair_ids]
    report = build_alignment_report(items, center, shape, pixel_scale_arcsec)
    report["pair_ids"] = pair_ids
    report["pair_common_geometric_coverage_fraction"] = float(np.logical_and.reduce([r.footprint > 0 for r in pair]).mean())
    report["pair_common_science_coverage_fraction"] = float(np.logical_and.reduce([r.coverage for r in pair]).mean())
    report["pair_common_display_coverage_fraction"] = float(np.logical_and.reduce([r.display_coverage for r in pair]).mean())
    report["pair_reference_residuals"] = alignment_residuals(*pair, pixel_scale_arcsec, exclude=center)
    report["spectral_caution"] = "A/B pass the SPX-001 heuristic but have different local wavelengths and DR1/QR3 provenance; quantitative temporal comparability is not certified."
    report["input_integrity"] = {str(r.observation.path): hashlib.sha256(r.observation.path.read_bytes()).hexdigest() for r in items}
    write_manifest(output / "alignment_report.json", report)
    plot_aligned_overview(items, output / "aligned_overview.png", f"M101 — fixed TAN grid, {pixel_scale_arcsec:g} arcsec/pixel")
    plot_before_after(*pair, output / "before_after.png")
    write_blink(pair, output / "blink.gif", "M101 A/B — same sky grid and display scale")
    LOGGER.info("M101: %s", {k: report[k] for k in ("common_geometric_coverage_fraction", "pair_common_science_coverage_fraction")})
    LOGGER.info("M101 reference diagnostics: %s", {k:v for k,v in report["pair_reference_residuals"].items() if k not in {"matches", "rejected"}})
    return report


def initial_target_selection(records, limit):
    """Cover separated epoch groups before adding intra-epoch spectral alternatives."""
    if limit < 1:
        raise ValueError("Download limit must be positive.")
    records = sorted(records, key=lambda record: record["mjd"])
    preferred = [r for r in records if r["release"] == "dr1"]
    if len(epoch_groups(preferred)) >= 3 and preferred[-1]["mjd"] - preferred[0]["mjd"] >= 60:
        records = preferred
    groups = epoch_groups(records, gap_days=1)
    if not groups:
        return []
    # Uniform temporal group anchors, then round-robin within each selected visit.
    representatives = [group[len(group)//2] for group in groups]
    anchors = select_observations(representatives, min(len(groups), max(2, limit//2)))
    chosen_groups = [next(group for group in groups if anchor in group) for anchor in anchors]
    queues = []
    for group in chosen_groups:
        chronological = select_observations(group, min(len(group), limit))
        queue = chronological[:1] + chronological[-1:] if len(chronological) > 1 else chronological[:]
        queue += [r for r in chronological if r not in queue]
        queues.append(queue)
    selected = []
    for index in range(max(map(len, queues))):
        for queue in queues:
            if index < len(queue) and len(selected) < limit:
                selected.append(queue[index])
    # A field containing only single-frame visits must still use its configured
    # budget rather than silently stopping after half as many temporal anchors.
    if len(selected) < min(limit, len(records)):
        remaining = [record for record in records if record not in selected]
        selected += select_observations(remaining, min(limit-len(selected), len(remaining)))
    return sorted(selected, key=lambda record: record["mjd"])


def initial_barnard_selection(records, limit):
    """Backward-compatible name for the target-independent temporal selector."""
    return initial_target_selection(records, limit)


def _inspect_target_record(record, observation, center, grid, shape, target):
    """Reevaluate original pixels on the current grid, including cached observations."""
    if observation.midpoint is None:
        raise ValueError("Missing midpoint time for proper-motion prediction.")
    prediction = predict_position(target, observation.midpoint)
    spectral_center = observation.spectral_at(center)
    spectral_target = observation.spectral_at(prediction)
    aligned = align_observation(observation, grid, shape)
    measured = measure_known_target(aligned, target)
    quality = measured["measurement"].get("core_valid_fraction", 0)
    item = {**record, **observation.metadata(), "spectral_field_center": spectral_center,
            "spectral_expected_target": spectral_target,
            "wavelength_um": spectral_target["wavelength_um"], "bandwidth_um": spectral_target["bandwidth_um"],
            "target_quality_ok": bool(quality >= 0.75), "target_centroid": measured,
            "target_quality": observation.quality_at(prediction),
            "predicted_ra_deg": float(prediction.ra.deg), "predicted_dec_deg": float(prediction.dec.deg)}
    if measured["measurement"]["accepted"]:
        fit = measured["measurement"]
        item["spectral_measured_target"] = observation.spectral_at(SkyCoord(fit["ra_deg"]*u.deg, fit["dec_deg"]*u.deg))
    return item, aligned


def run_target(project: Path, output: Path, availability: dict, target: dict,
               max_downloads=8, pixel_scale_arcsec=6.2, size_deg=0.15, timeout=120, detector="SPHEREx-D2",
               total_download_budget=16, target_key=None, legacy=False, local_only=False,
               selected_records=None, raw_directory=None, download_function=None):
    """Budgeted real cutouts, post-download local spectral screening, and honest astrometry."""
    if max_downloads < 1 or max_downloads > 100:
        raise ValueError("Download budget must be between 1 and 100 cutouts.")
    target_key = target_key or target.get("key")
    if not target_key or not re.fullmatch(r"[a-z][a-z0-9_-]*", target_key):
        raise ValueError("A safe configured target key is required.")
    if target.get("key", target_key) != target_key:
        raise ValueError("Target model and target_key disagree.")
    if not 1 <= total_download_budget <= 100 or max_downloads > total_download_budget:
        raise ValueError("Per-call selection must fit within a positive global target budget.")
    matches = [row for row in availability["targets"] if row["key"] == target_key]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one cached availability entry for {target_key}.")
    entry = matches[0]
    if entry.get("astrometry", {}).get("main_id") not in {None, target.get("main_id")}:
        raise ValueError("Cached availability and astrometric identity disagree.")
    if entry.get("size_deg", size_deg) != size_deg:
        raise ValueError("Requested field size differs from cached cutout URLs; no query or download was performed.")
    project, output = Path(project).resolve(), Path(output).resolve()
    if not legacy:
        allowed = [project / "outputs/spx002b", project / "outputs/spx004a"]
        if not any(root in output.parents for root in allowed):
            raise ValueError("Generic target outputs must be below outputs/spx002b/ or outputs/spx004a/.")
    output.mkdir(parents=True, exist_ok=True)
    center = SkyCoord(entry["field_center_ra_deg"]*u.deg, entry["field_center_dec_deg"]*u.deg)
    grid, shape = common_grid(center.ra.deg, center.dec.deg, size_deg, pixel_scale_arcsec)
    detector_result = entry["detectors"].get(detector, {})
    records = detector_result.get("observations", [])
    selected = initial_target_selection(records, max_downloads) if selected_records is None else list(selected_records)
    if len(selected)>max_downloads or any(record not in records for record in selected):
        raise ValueError("Explicit selection must fit the budget and cached detector availability.")
    manifest = {"target": target, "detector": detector, "download_budget": max_downloads,
                "field_center_ra_deg": center.ra.deg, "field_center_dec_deg": center.dec.deg,
                "size_deg": size_deg, "field_center_epoch": "2025-11-01",
                "selection_method": "Prefer DR1 when >=3 visit groups span >=60 days. Sample separated temporal visit groups, then round-robin intra-visit alternatives (endpoints first); local spectral/quality screening after bounded downloads. All downloaded records retained.",
                "observations": [], "failures": [], "run_failures": [], "downloaded_count": 0,
                "predicted_motion_model": "Linear tangent proper motion from documented SIMBAD ICRS J2000. No annual parallax or perspective acceleration.",
                "target_key": target_key,
                "detector_choice": f"Controlled {detector} experiment; quality, local spectra and accepted centroids determine selection.",
                "global_download_budget": total_download_budget,
                "attempted_candidates": [{"observation_id": r["observation_id"], "url": r["url"], "detector": detector} for r in selected]}
    aligned_by_id = {}
    raw_directory = Path(raw_directory) if raw_directory is not None else project / "data/raw" / ("spx002" if legacy else "spx002b") / target_key
    if project / "data/raw" not in raw_directory.resolve().parents:
        raise ValueError("Raw cutouts must stay below data/raw/.")
    def record_key(record):
        return (record["observation_id"], int(record.get("detector", detector[-1])))
    if not legacy and (output / "observations.json").exists():
        previous = json.loads((output / "observations.json").read_text(encoding="utf-8"))
        if previous.get("target_key") != target_key:
            raise ValueError("Existing results belong to a different target.")
        manifest["failures"] = previous.get("failures", [])
        plans = previous.get("attempted_candidates", []) + manifest["attempted_candidates"]
        manifest["attempted_candidates"] = list({item["url"]: item for item in plans}.values())
        for record in previous["observations"]:
            local = Path(record["local_path"])
            obs = Observation.read(local if local.is_absolute() else project / local, record["release"])
            item, aligned = _inspect_target_record(record, obs, center, grid, shape, target)
            item["local_path"] = obs.path.relative_to(project).as_posix()
            aligned_by_id[record_key(item)] = aligned
            manifest["observations"].append(item)
            save_aligned(aligned, output / item["aligned_asset"])
    existing_keys = {record_key(record) for record in manifest["observations"]}
    for record in selected:
        if record_key(record) in existing_keys:
            continue
        try:
            digest = hashlib.sha256(record["url"].encode()).hexdigest()[:16]
            cached = list(raw_directory.glob(f"*_{digest}.fits"))
            if local_only and not cached:
                continue
            if not cached and len(list(raw_directory.glob("*.fits"))) >= total_download_budget:
                raise ValueError("Global target FITS budget is exhausted; reuse existing cutouts or explicitly raise the total budget.")
            path = (download_function or download_cutout)(record["url"], raw_directory, timeout=timeout)
            observation = Observation.read(path, record["release"])
            item, aligned = _inspect_target_record(record, observation, center, grid, shape, target)
            manifest["observations"].append(item)
            existing_keys.add(record_key(item))
            aligned_by_id[record_key(item)] = aligned
            asset_name = observation.observation_id if legacy else f"{observation.observation_id}D{int(item['detector'])}"
            item["aligned_asset"] = f"aligned/{asset_name}.fits"
            save_aligned(aligned, output / item["aligned_asset"])
            if not legacy:
                item["local_path"] = path.relative_to(project).as_posix()
            LOGGER.info("%s %s %s lambda=%s um quality=%s fit=%s", target_key, record["observation_id"], record["timestamp"], item["wavelength_um"],
                        item["target_quality"]["science_valid_fraction"], item["target_centroid"]["measurement"])
        except Exception as error:
            failure = {"url": record["url"], "error": f"{type(error).__name__}: {error}"}
            manifest["failures"].append(failure)
            manifest["run_failures"].append(failure)
            LOGGER.exception("%s cutout failed", target_key)
        manifest["downloaded_count"] = len(manifest["observations"])
        write_manifest(output / "observations.json", manifest)
    manifest["observations"].sort(key=lambda r: r["mjd"])
    manifest["downloaded_count"] = len(manifest["observations"])
    manifest["stored_fits_count"] = len(list(raw_directory.glob("*.fits")))
    sequence = select_spectral_sequence(manifest["observations"], total_download_budget,
                                        require_accepted_centroids=not legacy)
    measured_sequence = len(sequence) >= 2
    mode = "same-release pairwise half-bandwidth spectral cluster; one record per separated epoch"
    if len(sequence) < 2:
        sequence = select_spectral_sequence(manifest["observations"], total_download_budget)
        if len(sequence) < 2:
            sequence = select_spectral_sequence([{**r, "target_quality_ok": True} for r in manifest["observations"]], total_download_budget)
        if not sequence:
            sequence = [group[0] for group in epoch_groups(manifest["observations"])]
        mode = "Diagnostic only: no accepted, same-release, same-detector spectral centroid pair."
    sequence.sort(key=lambda record: record["mjd"])
    manifest["sequence_mode"] = mode
    manifest["sequence_ids"] = [r["observation_id"] for r in sequence]
    manifest["sequence_keys"] = [list(record_key(r)) for r in sequence]
    manifest["sequence_classification"] = "exploratory" if measured_sequence else "diagnostic" if sequence else "unavailable"
    manifest["spectral_tolerance"] = "Every pair must differ by <= 0.5 times the smaller local target bandwidth for matched mode."
    manifest["status"] = "complete" if sequence and not manifest["failures"] else "partial" if sequence else "no_usable_observations"
    write_manifest(output / "observations.json", manifest)
    if not sequence:
        write_manifest(output / "alignment_report.json", {"status": "no_usable_observations", "failures": manifest["failures"], "archive_error": detector_result.get("error")})
        if not legacy:
            from .sequence_manifest import write_sequence_manifest
            write_sequence_manifest(output, target, center, grid, shape, pixel_scale_arcsec, [], [], manifest["sequence_classification"], ["No observations available."])
        return manifest
    all_items = [aligned_by_id[record_key(r)] for r in manifest["observations"]]
    sequence_items = [aligned_by_id[record_key(r)] for r in sequence]
    measurements = [r["target_centroid"] for r in sequence]
    report = build_alignment_report(sequence_items, center, shape, pixel_scale_arcsec)
    report.update(sequence_ids=manifest["sequence_ids"], sequence_mode=mode, measurements=measurements,
                  sequence_classification=manifest["sequence_classification"],
                  motion=motion_summary(measurements, pixel_scale_arcsec),
                  target=target, downloaded_count=manifest["downloaded_count"])
    if not legacy:
        for metadata in report["observations"]:
            metadata["local_path"] = Path(metadata["local_path"]).relative_to(project).as_posix()
    if len(sequence_items) >= 2:
        target_center = predict_position(target, sequence_items[0].observation.midpoint)
        report["background_reference_residuals"] = alignment_residuals(sequence_items[0], sequence_items[-1], pixel_scale_arcsec, exclude=target_center)
    report["interpretation"] = {
        "significant_detection_claimed": False,
        "measurement_kind": "Apparent photocenter displacement; not a fitted catalog proper motion.",
        "uncertainty": "Formal endpoint fit errors exclude reference-frame, PSF, blending, parallax and binary photocenter systematics.",
        "comparison": "Reference-source RMS is an empirical diagnostic, not a calibrated target-motion uncertainty or significance denominator.",
    }
    write_manifest(output / "alignment_report.json", report)
    display_name = target.get("name", target_key)
    plot_aligned_overview(all_items, output / "aligned_overview.png", f"{display_name} — all candidates; detector and wavelength labeled")
    write_blink(sequence_items, output / "blink.gif", f"{display_name} — {manifest['sequence_classification']}; {len(sequence_items)} epochs", measurements)
    plot_motion(sequence_items, measurements, output / "motion_positions.png", display_name)
    if not legacy:
        from .sequence_manifest import write_sequence_manifest
        warnings = ["PSF, local response and backgrounds are not matched; no detection significance is established.",
                    "Prediction omits annual parallax, perspective and orbital motion."]
        if target.get("object_type") == "Unresolved brown dwarf binary":
            warnings.append("Unresolved binary: a measured centroid may be a combined, wavelength-dependent photocenter.")
        if not measured_sequence:
            warnings.append(mode)
        write_sequence_manifest(output, target, center, grid, shape, pixel_scale_arcsec,
                                sequence_items, sequence, manifest["sequence_classification"], warnings)
    return manifest


def run_barnard(project: Path, output: Path, availability: dict, target: dict,
                max_downloads=12, pixel_scale_arcsec=6.2, size_deg=0.15, timeout=120,
                detector="SPHEREx-D2", total_download_budget=None):
    """Compatibility wrapper retaining the original Barnard cache and call signature."""
    target = {"key": "barnard", "name": "Barnard's Star", **target}
    return run_target(project, output, availability, target, max_downloads, pixel_scale_arcsec,
                      size_deg, timeout, detector,
                      max_downloads if total_download_budget is None else total_download_budget,
                      target_key="barnard", legacy=True)


def finalize_barnard_local(project: Path, output: Path, pixel_scale_arcsec=6.2, total_download_budget=12):
    """Rebuild the final case from existing FITS only, keeping detector checks separate.

    An unusable target may still have a spectrally matched diagnostic pair; it is
    explicitly labeled and never upgraded to a valid measured-motion result.
    """
    diagnostic = output / "d2_diagnostic"
    diagnostic.mkdir(parents=True, exist_ok=True)
    original = diagnostic / "observations.json"
    if not original.exists():
        for name in ("observations.json", "alignment_report.json", "aligned_overview.png", "blink.gif", "motion_positions.png"):
            if (output / name).exists():
                shutil.copy2(output / name, diagnostic / name)
    manifest = json.loads(original.read_text(encoding="utf-8"))
    d6_path = output / "d6_check/observations.json"
    d6_manifest = json.loads(d6_path.read_text(encoding="utf-8")) if d6_path.exists() else None
    records = manifest["observations"] + (d6_manifest["observations"] if d6_manifest else [])
    if len(records) > total_download_budget:
        raise ValueError("Existing case exceeds the configured global download budget.")
    center = SkyCoord(manifest["field_center_ra_deg"]*u.deg, manifest["field_center_dec_deg"]*u.deg)
    grid, shape = common_grid(center.ra.deg, center.dec.deg, manifest["size_deg"], pixel_scale_arcsec)
    items, by_key = [], {}
    target = manifest["target"]
    for record in records:
        obs = Observation.read(Path(record["local_path"]), record["release"])
        item = align_observation(obs, grid, shape)
        measurement = measure_known_target(item, target)
        prediction = predict_position(target, obs.midpoint)
        record.update(target_centroid=measurement, target_quality=obs.quality_at(prediction),
                      target_quality_ok=bool(obs.quality_at(prediction).get("science_valid_fraction", 0) >= 0.75))
        key = (record["observation_id"], int(record["detector"]))
        by_key[key] = item
        items.append(item)
    sequence = select_spectral_sequence(records)
    diagnostic_only = len(sequence) < 2
    if diagnostic_only:
        # Find the best spectral pair without misrepresenting flagged cores as valid.
        sequence = select_spectral_sequence([{**r, "target_quality_ok": True} for r in records])
    if len(sequence) < 2:
        sequence = [group[0] for group in epoch_groups([r for r in records if int(r["detector"]) == 2])]
    sequence.sort(key=lambda r: r["mjd"])
    sequence_items = [by_key[(r["observation_id"], int(r["detector"]))] for r in sequence]
    measurements = [measure_known_target(item, target) for item in sequence_items]
    manifest.update(observations=records, downloaded_count=len(records), download_budget=total_download_budget,
                    sequence_ids=[r["observation_id"] for r in sequence],
                    sequence_mode="Spectral diagnostic only: target cores fail quality; no reliable centroids." if diagnostic_only else "Same-release, same-detector spectral sequence with acceptable target quality.",
                    detector_checks={"D2": "d2_diagnostic/observations.json", "D6": "d6_check/observations.json" if d6_manifest else None},
                    scientific_status="motion_not_measurable" if diagnostic_only else "requires_astrometric_review",
                    status="processed_with_scientific_limitations" if diagnostic_only else "complete")
    manifest["initial_detector"] = manifest.pop("detector", "SPHEREx-D2")
    manifest["detectors_examined"] = sorted({f"SPHEREx-D{int(r['detector'])}" for r in records})
    manifest["sequence_detector"] = f"SPHEREx-D{int(sequence[0]['detector'])}"
    if d6_manifest:
        manifest["failures"] += d6_manifest["failures"]
    write_manifest(output / "observations.json", manifest)
    report = build_alignment_report(sequence_items, center, shape, pixel_scale_arcsec)
    report.update(sequence_mode=manifest["sequence_mode"], scientific_status=manifest["scientific_status"],
                  downloaded_count=len(records), sequence_ids=manifest["sequence_ids"], measurements=measurements,
                  motion=motion_summary(measurements, pixel_scale_arcsec),
                  astrometric_reference=target,
                  omitted_effects={"annual_parallax": True, "parallax_mas_catalog": target["parallax_mas"],
                                   "perspective_acceleration": True, "observer_position": True},
                  target_quality_by_observation=[{"observation_id": r["observation_id"], "detector": r["detector"],
                                                  "quality": r["target_quality"]} for r in records])
    if len(sequence_items) >= 2:
        report["background_reference_residuals"] = alignment_residuals(sequence_items[0], sequence_items[-1], pixel_scale_arcsec,
                                                                     exclude=predict_position(target, sequence_items[0].observation.midpoint))
    report["conclusion"] = ("No reliable observed motion can be measured in these cutouts: the target cores are invalid. "
                            "The expected track is a prediction, not an observation. D6 did not supply a validated replacement pair." if diagnostic_only else
                            "Review accepted fits and background residuals before scientific interpretation.")
    write_manifest(output / "alignment_report.json", report)
    plot_aligned_overview(items, output / "aligned_overview.png", "Barnard's Star — D2 and D6 diagnostics; different wavelengths, flagged cores")
    write_blink(sequence_items, output / "blink.gif", "Barnard's Star — spectral diagnostic; target core invalid" if diagnostic_only else "Barnard's Star — fixed sky", measurements)
    plot_motion(sequence_items, measurements, output / "motion_positions.png")
    return manifest
