"""Run the SPX-001 M101 experiment with real IRSA cutouts."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import importlib.metadata
import logging
from pathlib import Path
import platform
import sys

from spherex_explorer.data_access import (
    SearchParameters, build_query, download_cutout, prepare_observations,
    query_observations, select_observations,
)
from spherex_explorer.fits_utils import assess_spectral_pairs, inspect_fits, write_manifest
from spherex_explorer.visualization import plot_overview

LOGGER = logging.getLogger("explore_spherex")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_arguments(argv=None):
    """Parse validated experiment configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ra", type=float, default=210.80227, help="ICRS right ascension [deg]")
    parser.add_argument("--dec", type=float, default=54.34895, help="ICRS declination [deg]")
    parser.add_argument("--size", type=float, default=0.1, help="Cutout width [deg], at most 1")
    parser.add_argument("--detector", default="SPHEREx-D2", choices=[f"SPHEREx-D{i}" for i in range(1, 7)])
    parser.add_argument("--max-downloads", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs")
    parser.add_argument("--raw-dir", type=Path, default=PROJECT_ROOT / "data" / "raw")
    parser.add_argument("--timeout", type=float, default=120, help="TAP and download read timeout [s]")
    args = parser.parse_args(argv)
    try:
        SearchParameters(args.ra, args.dec, args.size, args.detector)
        if args.max_downloads < 1 or not 0 < args.timeout < float("inf"):
            raise ValueError("Download limit and finite timeout must be positive.")
    except ValueError as error:
        parser.error(str(error))
    return args


def main(argv=None) -> int:
    """Write provenance even for empty queries or failed real integrations."""
    args = parse_arguments(argv)
    args.output_dir = args.output_dir.resolve()
    args.raw_dir = args.raw_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(args.output_dir / "exploration.log", mode="w", encoding="utf-8")])
    parameters = SearchParameters(args.ra, args.dec, args.size, args.detector)
    manifest = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "started", "parameters": asdict(parameters), "coordinate_frame": "ICRS",
        "download_limit": args.max_downloads, "raw_directory": str(args.raw_dir),
        "python": platform.python_version(),
        "dependencies": {name: importlib.metadata.version(name) for name in
                         ("astropy", "astroquery", "numpy", "matplotlib", "requests")},
        "query": build_query(parameters), "raw_result_count": None,
        "unique_observation_count": None, "selected_count": 0, "downloaded_count": 0,
        "time_range": None, "observations": [], "failures": [], "overview_path": None,
        "sources": ["https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts/",
                    "https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/"],
    }
    overview = args.output_dir / "observations_overview.png"
    # Avoid leaving an old successful overview next to a failed current manifest.
    overview.unlink(missing_ok=True)
    try:
        LOGGER.info("Querying IRSA for %s", parameters)
        table = query_observations(parameters, args.timeout)
        manifest["raw_result_count"] = len(table)
        manifest["tap_columns"] = [{"name": name, "unit": str(table[name].unit) if table[name].unit else None,
                                    "description": table[name].description} for name in table.colnames]
        observations = prepare_observations(table)
        manifest["unique_observation_count"] = len(observations)
        if observations:
            manifest["time_range"] = {
                "start_utc": observations[0]["timestamp"], "end_utc": observations[-1]["timestamp"],
                "start_mjd": observations[0]["mjd"], "end_mjd": observations[-1]["mjd"],
            }
        LOGGER.info("TAP rows: %d; unique observations: %d; interval: %s",
                    len(table), len(observations), manifest["time_range"])
        selected = select_observations(observations, args.max_downloads)
        manifest["selected_count"] = len(selected)
        manifest["selected_observations"] = selected
        for record in selected:
            try:
                local_path = download_cutout(record["url"], args.raw_dir, timeout=args.timeout)
                item = {**record, "local_path": str(local_path)}
                manifest["observations"].append(item)
                manifest["downloaded_count"] += 1
                item["inspection"] = inspect_fits(local_path, args.ra, args.dec)
                LOGGER.info("%s | %s | wavelength=%s um | bandwidth=%s um | %s | %s",
                            record["observation_id"], record["timestamp"],
                            item["inspection"]["effective_wavelength_um"],
                            item["inspection"]["spectral_bandwidth_um"],
                            item["inspection"]["processing_version"], record["release"])
                if item["inspection"]["errors"]:
                    LOGGER.warning("Inspection notes: %s", item["inspection"]["errors"])
            except Exception as error:
                # Preserve independent successes and report the exact remote/local failure.
                manifest["failures"].append({"url": record["url"], "error": f"{type(error).__name__}: {error}"})
                LOGGER.error("Observation failed: %s", error)
        inspected = [item for item in manifest["observations"] if "inspection" in item]
        manifest["spectral_pair_assessment"] = assess_spectral_pairs(inspected)
        LOGGER.info("Spectral pair screening: %s", manifest["spectral_pair_assessment"])
        if inspected:
            plot_overview(inspected, overview)
            manifest["overview_path"] = str(overview)
        inspection_errors = any(item["inspection"]["errors"] for item in inspected)
        manifest["status"] = ("partial" if manifest["failures"] or inspection_errors else
                              "complete" if inspected else "no_results")
    except Exception as error:
        manifest["status"] = "failed"
        manifest["failures"].append({"stage": "query_or_processing", "error": f"{type(error).__name__}: {error}"})
        LOGGER.exception("Real integration failed")
    finally:
        write_manifest(args.output_dir / "observations.json", manifest)
    LOGGER.info("Finished: status=%s, downloaded=%d", manifest["status"], manifest["downloaded_count"])
    return 0 if manifest["status"] in {"complete", "no_results"} else 1


if __name__ == "__main__":
    sys.exit(main())
