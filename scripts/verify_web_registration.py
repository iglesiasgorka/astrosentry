"""Compare actual browser pixels against independent FITS/WCS samples after browser QA.

This rank-pattern check tests sky anchoring and image orientation under a display
stretch. It is not photometry, a precision astrometric residual, or motion significance.
"""

import json
from pathlib import Path

from astropy.io import fits
import numpy as np
from PIL import Image
from scipy.stats import spearmanr

PROJECT = Path(__file__).resolve().parents[1]


def main():
    directory = PROJECT / "outputs/spx003a"
    report = {}
    for target in ("epsilon_indi_b", "m101", "barnard"):
        for suffix in ("", "_panned", "_resized"):
            name = target + suffix
            metadata = json.loads((directory / f"{name}_screen.json").read_text())
            image = np.array(Image.open(directory / f"{name}.png").convert("RGB"), dtype=float)
            with fits.open(PROJECT / "frontend/public/data" / metadata["target"]["assets"]["fits"]) as hdus:
                array = hdus[0].data.copy()
            expected, observed, inverted = [], [], []
            for sample in metadata["samples"]:
                point = sample["screen"]
                if point is None:
                    continue
                # Accept the first probe's typed-array JSON as well as portable arrays.
                x, y = (point["0"], point["1"]) if isinstance(point, dict) else point
                ix, iy = int(round(x)), int(round(y))
                if not (2 <= ix < image.shape[1]-2 and 2 <= iy < image.shape[0]-2):
                    continue
                px, py = sample["pixel"]
                flipped = array[array.shape[0]-1-py, px]
                if np.isfinite(flipped):
                    expected.append(sample["value"])
                    observed.append(float(np.mean(image[iy-1:iy+2, ix-1:ix+2])))
                    inverted.append(float(flipped))
            correct = float(spearmanr(expected, observed).statistic)
            wrong = float(spearmanr(inverted, observed).statistic)
            passed = len(expected) >= 100 and correct > 0.90 and correct-wrong > 0.10
            report[name] = {"samples": len(expected), "registered_intensity_rank_correlation": correct,
                            "vertical_flip_control_correlation": wrong, "passed": passed}
            print(f"{name}: n={len(expected)}, registered={correct:.6f}, inverted={wrong:.6f}, passed={passed}")
    (directory / "rendered_registration_check.json").write_text(json.dumps(report, indent=2)+"\n")
    return 0 if all(item["passed"] for item in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
