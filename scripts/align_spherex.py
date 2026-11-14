"""SPX-002: fixed-sky alignment, target availability, and known-motion validation."""

import argparse
import hashlib
import json
import logging
import math
from pathlib import Path

from spherex_explorer.scientific_pipeline import run_m101, run_barnard, run_target, finalize_barnard_local
from spherex_explorer.targets import resolve_catalog, query_target_availability
from spherex_explorer.fits_utils import write_manifest

PROJECT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["target", "m101", "availability", "barnard", "barnard-d6", "barnard-local", "all"], default="all", nargs="?")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--target", help="Configured target key for the generic target stage")
    parser.add_argument("--total-budget", type=int, default=16, help="Global stored FITS budget per generic target, across detectors")
    parser.add_argument("--local-only", action="store_true", help="Reuse existing target data without new downloads")
    parser.add_argument("--catalog", type=Path, default=PROJECT / "config/targets.json")
    parser.add_argument("--max-downloads", type=int, default=None)
    parser.add_argument("--pixel-scale", type=float, default=6.2, help="Angular pixel size in arcseconds")
    parser.add_argument("--size", "--barnard-size", dest="field_size", type=float, default=0.15,
                        help="Fixed field width in degrees; must match cached cutouts for the target stage")
    parser.add_argument("--detector", default="SPHEREx-D2", choices=[f"SPHEREx-D{i}" for i in range(1,7)])
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--refresh-availability", action="store_true")
    parser.add_argument("--refresh-catalog", action="store_true")
    args = parser.parse_args(argv)
    args.max_downloads = args.max_downloads if args.max_downloads is not None else 8 if args.stage == "target" else 12
    if not 1 <= args.max_downloads <= 100 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("Download limit must be 1 through 100 and timeout must be positive and finite.")
    exit_code = 0
    allowed = PROJECT / "outputs" / ("spx002b" if args.stage == "target" else "spx002")
    output = (args.output_dir or allowed).resolve()
    if allowed not in [output, *output.parents]:
        parser.error(f"Outputs must be below {allowed} to preserve earlier phases.")
    if args.stage == "target":
        configured = json.loads(args.catalog.read_text(encoding="utf-8"))
        if args.target not in {row["key"] for row in configured}:
            parser.error("--target must identify an object in the configured target catalog.")
        output = output / args.target
    output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(output / f"{args.stage}.log", encoding="utf-8")])
    # Suppress only verbose informational chatter; retain scientific warnings/errors.
    logging.getLogger("astropy").setLevel(logging.WARNING)
    if args.stage == "target":
        # SPX-002B deliberately reuses provenance and all 30 cached availability
        # queries; it does not resolve or re-query other targets.
        targets = json.loads((PROJECT / "config/target_astrometry.json").read_text(encoding="utf-8"))["targets"]
        target = next(row for row in targets if row["key"] == args.target)
        availability = json.loads((PROJECT / "outputs/spx002/target_availability.json").read_text(encoding="utf-8"))
        result = run_target(PROJECT, output, availability, target, args.max_downloads,
                            args.pixel_scale, args.field_size, args.timeout, args.detector,
                            args.total_budget, target_key=args.target, local_only=args.local_only)
        if result.get("run_failures", result["failures"]) or result["status"] == "no_usable_observations":
            exit_code = 1
    if args.stage in {"m101", "all"}:
        run_m101(PROJECT, output / "m101", args.pixel_scale)
    if args.stage in {"availability", "barnard", "barnard-d6", "all"}:
        targets = resolve_catalog(args.catalog, PROJECT / "config/target_astrometry.json", args.refresh_catalog)
        availability = query_target_availability(targets, output / "target_availability.json", args.field_size,
                                                   args.timeout, args.refresh_availability)
        if args.stage in {"barnard", "all"}:
            target = next(row for row in targets if row["key"] == "barnard")
            result = run_barnard(PROJECT, output / "barnard", availability, target, args.max_downloads,
                                 args.pixel_scale, args.field_size, args.timeout, args.detector)
            if result["failures"] or result["status"] == "no_usable_observations":
                exit_code = 1
        if args.stage == "barnard-d6":
            if not (output / "barnard/observations.json").exists():
                parser.error("Run the initial Barnard stage before the controlled D6 check.")
            remaining = args.max_downloads - len(list((PROJECT / "data/raw/spx002/barnard").glob("*.fits")))
            if remaining > 0:
                target = next(row for row in targets if row["key"] == "barnard")
                result = run_barnard(PROJECT, output / "barnard/d6_check", availability, target,
                                     min(2, remaining), args.pixel_scale, args.field_size, args.timeout,
                                     "SPHEREx-D6", total_download_budget=args.max_downloads)
                if result["failures"] or result["status"] == "no_usable_observations":
                    exit_code = 1
            else:
                logging.info("No remaining global cutout budget; retaining existing detector checks.")
    if args.stage == "barnard-local":
        finalize_barnard_local(PROJECT, output / "barnard", args.pixel_scale, args.max_downloads)
    snapshot_path = PROJECT / ("outputs/spx002b/prior_artifacts_sha256.json" if args.stage == "target" else "outputs/spx002/spx001_integrity.json")
    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text())
        unchanged = {path: hashlib.sha256((PROJECT/path).read_bytes()).hexdigest() == digest for path,digest in snapshot.items()}
        write_manifest(output / "prior_results_preservation_check.json" if args.stage == "target" else output / "spx001_preservation_check.json",
                       {"all_unchanged": all(unchanged.values()), "files": unchanged})
        if not all(unchanged.values()):
            raise RuntimeError("SPX-001 integrity check failed.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
