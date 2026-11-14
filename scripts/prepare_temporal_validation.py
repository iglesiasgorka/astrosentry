"""Prepare independent real FITS/WCS samples for SPX-003B browser evidence."""
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
        samples[target["id"]] = []
        for frame in target["sequence"]["frames"]:
            points = []
            with fits.open(assets / frame["assets"]["fits"]) as hdus:
                image, wcs = hdus[0].data, WCS(hdus[0].header).celestial
                height, width = image.shape
                for y in range(8, height - 8, 4):
                    for x in range(8, width - 8, 4):
                        if not np.isfinite(image[y, x]):
                            continue
                        sky = wcs.pixel_to_world(x, y).icrs
                        points.append({"pixel": [x, y], "sky": [float(sky.ra.deg), float(sky.dec.deg)], "value": float(image[y, x])})
            samples[target["id"]].append(points)
    directory = PROJECT / "outputs/spx003b"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "registration_samples.json").write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")
    print({key: [len(frame) for frame in frames] for key, frames in samples.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
