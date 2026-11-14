"""Provenanced SIMBAD astrometry, fixed fields, and archive availability."""

import json
from pathlib import Path

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time
from astroquery.simbad import Simbad
import numpy as np

from .data_access import SearchParameters, prepare_observations, query_observations
from .fits_utils import json_safe, write_manifest

SIMBAD_EPOCH_SOURCE = "https://simbad.u-strasbg.fr/Pages/guide/sim-fsam.htx"


def resolve_catalog(config_path: Path, output_path: Path, refresh=False) -> list[dict]:
    """Resolve configured identities with an explicitly documented ICRS J2000 epoch."""
    if Path(output_path).exists() and not refresh:
        return json.loads(Path(output_path).read_text(encoding="utf-8"))["targets"]
    configurations = json.loads(Path(config_path).read_text(encoding="utf-8"))
    simbad = Simbad()
    simbad.server = "simbad.harvard.edu"
    simbad.TIMEOUT = 90
    simbad.add_votable_fields("pmra", "pmdec", "plx_value", "pm_bibcode", "plx_bibcode",
                             "ids", "otype", "pm_err_maj", "pm_err_min")
    table = simbad.query_objects([item["query_name"] for item in configurations])
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    table.write(Path(output_path).with_suffix(".ecsv"), format="ascii.ecsv", overwrite=True)
    return catalog_from_table(configurations, table, output_path)


def catalog_from_table(configurations, table: Table, output_path: Path) -> list[dict]:
    """Keep raw reference values and bibliography; no unknown epochs are inferred."""
    targets = []
    for item in configurations:
        rows = [row for row in table if str(row["user_specified_id"]).strip() == item["query_name"]]
        if len(rows) != 1:
            raise ValueError(f"Expected one unambiguous SIMBAD identity for {item['query_name']}")
        row = rows[0]
        def value(key):
            raw = row[key]
            return None if np.ma.is_masked(raw) else json_safe(raw)
        target = {**item, "main_id": value("main_id"), "identifiers": str(row["ids"]).split("|"),
                  "ra_deg": value("ra"), "dec_deg": value("dec"), "reference_epoch_jyear": 2000.0,
                  "frame": "ICRS", "reference_epoch_source": SIMBAD_EPOCH_SOURCE,
                  "coordinate_bibcode": value("coo_bibcode"), "pm_ra_cosdec_mas_yr": value("pmra"),
                  "pm_dec_mas_yr": value("pmdec"), "proper_motion_bibcode": value("pm_bibcode"),
                  "pm_error_major_mas_yr": value("pm_err_maj"), "pm_error_minor_mas_yr": value("pm_err_min"),
                  "parallax_mas": value("plx_value"), "parallax_bibcode": value("plx_bibcode"),
                  "simbad_type": value("otype"), "source": "SIMBAD Harvard mirror via astroquery",
                  "resolved_at_utc": Time.now().utc.isot,
                  "epoch_note": "SIMBAD basic positions are propagated to ICRS epoch J2000, distinct from the source catalog epoch (Gaia EDR3 J2016)."}
        if target["ra_deg"] is None or target["dec_deg"] is None:
            raise ValueError(f"SIMBAD returned no coordinates for {item['name']}")
        targets.append(target)
    write_manifest(output_path, {"targets": targets})
    return targets


def predict_position(target: dict, time: Time) -> SkyCoord:
    """Linear tangent-plane proper motion; no annual parallax or perspective terms.

    pm_ra_cosdec follows the catalog convention. Values are never replaced by a
    measured centroid. A missing motion returns the fixed catalog position.
    """
    position = SkyCoord(target["ra_deg"] * u.deg, target["dec_deg"] * u.deg, frame="icrs")
    if target.get("pm_ra_cosdec_mas_yr") is None or target.get("pm_dec_mas_yr") is None:
        return position
    dt = time.tcb.jyear - float(target["reference_epoch_jyear"])
    east = target["pm_ra_cosdec_mas_yr"] * dt * u.mas
    north = target["pm_dec_mas_yr"] * dt * u.mas
    # A great-circle offset implements the first-order tangent prediction without
    # dividing by cos(dec) near the celestial poles.
    return position.directional_offset_by(np.arctan2(east.to_value(u.mas), north.to_value(u.mas)) * u.rad,
                                         np.hypot(east.to_value(u.mas), north.to_value(u.mas)) * u.mas)


def epoch_groups(records: list[dict], gap_days=1.0) -> list[list[dict]]:
    """Group consecutive visits separated by less than the documented time gap."""
    if gap_days <= 0:
        raise ValueError("Epoch gap must be positive.")
    groups = []
    for record in sorted(records, key=lambda r: r["mjd"]):
        if not groups or record["mjd"] - groups[-1][-1]["mjd"] >= gap_days:
            groups.append([])
        groups[-1].append(record)
    return groups


def summarize_availability(records):
    """Summarize unique detector observations and one-day-separated visit groups."""
    return {"unique_observation_count": len(records),
            "epoch_count_gap_1_day": len(epoch_groups(records)),
            "distinct_utc_dates": len({r["timestamp"][:10] for r in records}),
            "releases": sorted({r["release"] for r in records}),
            "start_utc": min((r["timestamp"] for r in records), default=None),
            "end_utc": max((r["timestamp"] for r in records), default=None),
            "observations": records}


def query_target_availability(targets, destination: Path, size_deg=0.15, timeout=120, refresh=False):
    """Query six verified SPHEREx bandpasses for each target, without FITS downloads."""
    destination = Path(destination)
    result = json.loads(destination.read_text()) if destination.exists() and not refresh else {
        "epoch_definition": "Consecutive records with gaps >= 1 day start a new epoch group.",
        "field_reference_time": "2025-11-01T00:00:00 UTC", "targets": []}
    existing = {entry["key"]: entry for entry in result["targets"]}
    for target in targets:
        center = predict_position(target, Time("2025-11-01", scale="utc"))
        cached = existing.get(target["key"])
        if cached and (cached["size_deg"] != size_deg or
                       abs(cached["field_center_ra_deg"] - float(center.ra.deg)) > 1e-10 or
                       abs(cached["field_center_dec_deg"] - float(center.dec.deg)) > 1e-10):
            cached = None
        entry = cached or {"key": target["key"], "name": target["name"],
                    "field_center_ra_deg": float(center.ra.deg), "field_center_dec_deg": float(center.dec.deg),
                    "size_deg": size_deg, "astrometry": target, "detectors": {}}
        for detector in range(1, 7):
            bandpass = f"SPHEREx-D{detector}"
            if bandpass in entry["detectors"] and entry["detectors"][bandpass].get("error") is None:
                continue
            try:
                table = query_observations(SearchParameters(float(center.ra.deg), float(center.dec.deg), size_deg, bandpass), timeout)
                records = prepare_observations(table)
                entry["detectors"][bandpass] = {**summarize_availability(records), "tap_row_count": len(table), "error": None}
            except Exception as error:
                entry["detectors"][bandpass] = {"unique_observation_count": None, "error": f"{type(error).__name__}: {error}"}
            existing[target["key"]] = entry
            result["targets"] = list(existing.values())
            write_manifest(destination, result)
            print(f"{target['name']} {bandpass}: {entry['detectors'][bandpass].get('unique_observation_count')} observations; {entry['detectors'][bandpass].get('error')}", flush=True)
    return result


def select_spectral_sequence(records: list[dict], limit=12, tolerance_bandwidths=0.5, minimum_gap_days=1.0,
                             require_accepted_centroids=False):
    """Select a same-release spectral cluster spanning the most separated epochs.

    Inputs require measured local wavelength/bandwidth and target quality; spectral
    estimates alone never imply valid astrometry. At most one record per epoch.
    """
    if limit < 1 or tolerance_bandwidths <= 0:
        raise ValueError("Limit and spectral tolerance must be positive.")
    usable = [r for r in records if r.get("wavelength_um") is not None and r.get("bandwidth_um") is not None
              and np.isfinite(r["wavelength_um"]) and np.isfinite(r["bandwidth_um"])
              and r["wavelength_um"] > 0 and r["bandwidth_um"] > 0 and r.get("target_quality_ok", False)]
    if require_accepted_centroids:
        usable = [r for r in usable if r.get("target_centroid", {}).get("measurement", {}).get("accepted", False)]
    candidates = []
    for anchor in usable:
        cluster = [r for r in usable if r["release"] == anchor["release"] and
                   r.get("detector") == anchor.get("detector") and
                   abs(r["wavelength_um"] - anchor["wavelength_um"]) <= tolerance_bandwidths * min(r["bandwidth_um"], anchor["bandwidth_um"])]
        pairwise = []
        for record in sorted(cluster, key=lambda r: abs(r["wavelength_um"] - anchor["wavelength_um"])):
            if all(abs(record["wavelength_um"] - other["wavelength_um"]) <= tolerance_bandwidths *
                   min(record["bandwidth_um"], other["bandwidth_um"]) for other in pairwise):
                pairwise.append(record)
        chosen = []
        for group in epoch_groups(pairwise, minimum_gap_days):
            chosen.append(min(group, key=lambda r: (abs(r["wavelength_um"] - anchor["wavelength_um"]), r["mjd"])))
        if len(chosen) > limit:
            indices = np.linspace(0, len(chosen) - 1, limit).round().astype(int)
            chosen = [chosen[i] for i in indices]
        span = chosen[-1]["mjd"] - chosen[0]["mjd"] if chosen else 0
        candidates.append(((len(chosen), span, anchor["release"] == "dr1"), chosen))
    return max(candidates, key=lambda item: item[0])[1] if candidates else []
