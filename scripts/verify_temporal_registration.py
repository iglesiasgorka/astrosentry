"""Validate actual rendered patterns against each epoch's independent FITS samples.

This is a registration/orientation check under a common monotonic display transform,
not photometry, an absolute astrometric error, or a motion significance calculation.
"""
import json
import argparse
from pathlib import Path
from astropy.io import fits
import numpy as np
from PIL import Image
from scipy.stats import spearmanr

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=PROJECT/'outputs/spx003b')
    parser.add_argument('--pattern',default='*_screen.json')
    parser.add_argument('--expected',type=int,default=12)
    parser.add_argument('--dynamic-root',type=Path,default=PROJECT/'outputs/spx006b/assets')
    args=parser.parse_args()
    directory = args.directory
    report = {}
    for path in sorted(directory.glob(args.pattern)):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        name = path.stem.removesuffix("_screen")
        image = np.array(Image.open(directory / f"{name}.png").convert("RGB"), dtype=float)
        asset=metadata['frame']['assets']['fits']
        root=args.dynamic_root if asset.startswith('dynamic/') else PROJECT/'frontend/public/data'
        with fits.open(root/asset) as hdus:
            array = hdus[0].data.copy()
        expected, observed, flipped, paired = [], [], [], []
        for sample in metadata["samples"]:
            point = sample["screen"]
            if point is None:
                continue
            x, y = (int(round(v)) for v in point)
            if not (2 <= x < image.shape[1]-2 and 2 <= y < image.shape[0]-2):
                continue
            value = float(np.mean(image[y-1:y+2, x-1:x+2]))
            expected.append(sample["value"])
            observed.append(value)
            px, py = sample["pixel"]
            wrong = array[array.shape[0]-1-py, px]
            if np.isfinite(wrong):
                flipped.append(float(wrong))
                paired.append(value)
        correct = float(spearmanr(expected, observed).statistic)
        inverted = float(spearmanr(flipped, paired).statistic)
        passed = len(expected) >= 50 and correct > .90 and correct-inverted > .08
        report[name] = {"samples": len(expected), "registeredRankCorrelation": correct, "invertedControlCorrelation": inverted, "passed": passed}
        print(name, report[name])
    complete = len(report) == args.expected
    (directory / "rendered_registration_check.json").write_text(json.dumps({"captures": report, "expectedCaptures": args.expected, "passed": complete and all(v["passed"] for v in report.values())}, indent=2) + "\n", encoding="utf-8")
    return 0 if complete and all(v["passed"] for v in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
