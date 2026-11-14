"""Diagnostic IMAGE panels, without temporal alignment or quantitative matching."""

from pathlib import Path
import math

from astropy.io import fits
from astropy.visualization import AsinhStretch, ImageNormalize, PercentileInterval
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .fits_utils import display_mask


def plot_overview(observations: list[dict], destination: Path) -> None:
    """Plot real IMAGE values with independent 99% percentile/asinh scaling."""
    if not observations:
        raise ValueError("No downloaded observations to visualize.")
    columns = min(4, len(observations))
    rows = math.ceil(len(observations) / columns)
    figure, axes = plt.subplots(rows, columns, figsize=(4.5 * columns, 4.4 * rows), squeeze=False)
    try:
        for axis, observation in zip(axes.flat, observations):
            with fits.open(observation["local_path"], memmap=False) as hdus:
                values = np.ma.array(hdus["IMAGE"].data, mask=display_mask(hdus))
                finite = values.compressed()
                if finite.size:
                    low, high = PercentileInterval(99).get_limits(finite)
                    if high <= low:
                        high = low + max(abs(float(low)) * 1e-6, 1e-6)
                    norm = ImageNormalize(vmin=low, vmax=high, stretch=AsinhStretch())
                    colormap = plt.get_cmap("gray").with_extremes(bad="#963a61")
                    artist = axis.imshow(values, origin="lower", cmap=colormap, norm=norm, interpolation="nearest")
                    figure.colorbar(artist, ax=axis, fraction=0.046, label=observation["inspection"].get("image_units") or "Units unavailable")
                else:
                    axis.text(0.5, 0.5, "No valid display pixels", ha="center", transform=axis.transAxes)
                wave = observation["inspection"].get("effective_wavelength_um")
                label = f"{wave:.5f} µm" if wave is not None else "Wavelength unavailable"
                axis.set_title(f"{observation['timestamp']} UTC\n{label} | {observation['release'].upper()} D{observation['detector']}", fontsize=9)
                axis.set_xlabel("Cutout x [pixel]")
                axis.set_ylabel("Cutout y [pixel]")
        for axis in list(axes.flat)[len(observations):]:
            axis.set_visible(False)
        figure.suptitle("SPHEREx real cutouts — diagnostic view", fontsize=15)
        figure.text(0.5, 0.015,
                    "Not aligned or calibrated for quantitative temporal comparison. Independent 99% / asinh scaling.\n"
                    "Magenta: nonfinite or selected severe FLAGS bits. SOURCE is retained. Wavelength evaluated at the requested ICRS coordinate.",
                    ha="center", fontsize=9)
        figure.tight_layout(rect=(0, 0.08, 1, 0.94), h_pad=4.0, w_pad=2.0)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(destination, dpi=160)
    finally:
        plt.close(figure)
