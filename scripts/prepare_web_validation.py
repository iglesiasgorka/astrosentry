"""Prepare independent FITS/WCS sample points for the optional browser QA run."""

import json
from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]


def main():
    assets = PROJECT / "frontend/public/data"
    catalog = json.loads((assets / "catalog.json").read_text(encoding="utf-8"))
    samples = {}
    for target in catalog["targets"]:
        with fits.open(assets / target["assets"]["fits"]) as hdus:
            image = hdus[0].data
            wcs = WCS(hdus[0].header).celestial
            height, width = image.shape
            points = []
            for y in range(8, height - 8, 4):
                for x in range(8, width - 8, 4):
                    value = float(image[y, x])
                    if not np.isfinite(value):
                        continue
                    sky = wcs.pixel_to_world(x, y).icrs
                    points.append({"pixel": [x, y], "sky": [float(sky.ra.deg), float(sky.dec.deg)],
                                   "value": value})
            samples[target["id"]] = points
    output = PROJECT / "outputs/spx003a/registration_samples.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared independent samples: { {key: len(value) for key, value in samples.items()} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
