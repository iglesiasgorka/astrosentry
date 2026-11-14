"""Export three validated local two-epoch sequences without network access."""

import argparse
from pathlib import Path

from spherex_explorer.web_export import export_web_data

PROJECT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "frontend/public/data")
    args = parser.parse_args(argv)
    catalog = export_web_data(PROJECT, args.output_dir.resolve())
    for target in catalog["targets"]:
        print(f"{target['id']}: {len(target['sequence']['frames'])} real frames | {target['dimensions']['width']}x{target['dimensions']['height']} | {target['classification']}")
    print(f"Wrote {args.output_dir.resolve() / 'catalog.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
