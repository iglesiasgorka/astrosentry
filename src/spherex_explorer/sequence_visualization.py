"""Shared display scaling, fixed-sky blinking, and explicit motion annotations."""

from io import BytesIO
from pathlib import Path
import math

from astropy.visualization import ImageNormalize, AsinhStretch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


def common_normalization(arrays):
    """One robust intensity transform for an entire comparison, display only."""
    finite = [a[np.isfinite(a)] for a in arrays if np.isfinite(a).any()]
    if not finite:
        return ImageNormalize(vmin=0, vmax=1, stretch=AsinhStretch())
    low, high = np.percentile(np.concatenate(finite), [0.5, 99.5])
    if high <= low:
        high = low + 1
    return ImageNormalize(vmin=low, vmax=high, stretch=AsinhStretch())


def frame_label(item):
    observation = item.observation
    wave = observation.spectral_at(item.wcs.pixel_to_world((item.image.shape[1]-1)/2, (item.image.shape[0]-1)/2))
    value = wave["wavelength_um"]
    wavelength = f"{value:.5f} µm" if value is not None else "Wavelength unavailable"
    date = observation.midpoint.utc.isot if observation.midpoint is not None else "Time unavailable"
    return f"{date} UTC\nD{observation.header.get('DETECTOR')} | {wavelength} | {(observation.release or 'unknown').upper()}"


def plot_aligned_overview(items, destination, title):
    """Display real aligned arrays with one shared intensity normalization."""
    if not items:
        raise ValueError("No aligned observations to plot.")
    columns = min(4, len(items))
    rows = math.ceil(len(items)/columns)
    figure, axes = plt.subplots(rows, columns, figsize=(4.2*columns, 4.2*rows), squeeze=False)
    norm = common_normalization([item.display_image for item in items])
    cmap = plt.get_cmap("gray").with_extremes(bad="#683a68")
    for axis, item in zip(axes.flat, items):
        axis.imshow(np.ma.masked_invalid(item.display_image), origin="lower", norm=norm, cmap=cmap)
        axis.set_title(frame_label(item), fontsize=8)
        axis.set_xlabel("Fixed sky x [pixel]; east left")
        axis.set_ylabel("Fixed sky y [pixel]; north up")
    for axis in list(axes.flat)[len(items):]:
        axis.set_visible(False)
    figure.suptitle(title)
    figure.text(0.5, 0.012, "MJy/sr; common display stretch. Magenta: no display coverage. PSF, backgrounds and spectral response are not matched.", ha="center", fontsize=8)
    figure.tight_layout(rect=(0, 0.05, 1, 0.95), h_pad=3)
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def plot_before_after(first, second, destination):
    """Show original pixel orientations beside the unchanged fixed celestial grid."""
    figure, axes = plt.subplots(2, 2, figsize=(10, 10))
    originals = [np.where(item.observation.display_invalid, np.nan, item.observation.image) for item in (first, second)]
    norm = common_normalization(originals + [first.display_image, second.display_image])
    cmap = plt.get_cmap("gray").with_extremes(bad="#683a68")
    for row, (item, original) in enumerate(zip((first, second), originals)):
        axes[row, 0].imshow(np.ma.masked_invalid(original), origin="lower", norm=norm, cmap=cmap)
        axes[row, 0].set_title(f"Original detector orientation\n{item.observation.observation_id}")
        axes[row, 1].imshow(np.ma.masked_invalid(item.display_image), origin="lower", norm=norm, cmap=cmap)
        axes[row, 1].set_title(f"Fixed TAN: north up, east left\n{frame_label(item)}", fontsize=9)
        for axis in axes[row]:
            axis.set_xlabel("x [pixel]")
            axis.set_ylabel("y [pixel]")
    figure.suptitle("M101 — before and after WCS reprojection")
    figure.text(0.5, 0.015, "Shared display scaling in MJy/sr; no source-based shift, PSF matching or temporal photometric calibration.", ha="center", fontsize=9)
    figure.tight_layout(rect=(0, 0.04, 1, 0.95), h_pad=3)
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def write_blink(items, destination, title, measurements=None, duration_ms=900):
    """Chronological real frames, fixed limits/grid, identical intensity stretch."""
    if not items:
        raise ValueError("No real frames for blink.")
    norm = common_normalization([item.display_image for item in items])
    cmap = plt.get_cmap("gray").with_extremes(bad="#683a68")
    frames = []
    measurement_by_id = {m["observation_id"]: m for m in measurements or []}
    for item in items:
        figure, axis = plt.subplots(figsize=(6.6, 7))
        axis.imshow(np.ma.masked_invalid(item.display_image), origin="lower", norm=norm, cmap=cmap)
        axis.set_title(title + "\n" + frame_label(item), fontsize=10)
        axis.set_xlabel("Fixed sky x [pixel]; east left")
        axis.set_ylabel("Fixed sky y [pixel]; north up")
        measurement = measurement_by_id.get(item.observation.observation_id)
        if measurement:
            axis.scatter(measurement["expected_x"], measurement["expected_y"], marker="+", color="#39dcff", s=130, label="Expected: linear PM")
            if measurement["measurement"]["accepted"]:
                axis.scatter(measurement["measured_x"], measurement["measured_y"], marker="o", facecolors="none", edgecolors="#ffb84d", s=140, label="Measured: local fit")
            axis.legend(loc="upper left", fontsize=8)
        figure.text(0.5, 0.02, "Common MJy/sr display scale. No target recentering.\nPSF/background/spectral differences remain; not a motion significance map.", ha="center", fontsize=8)
        figure.tight_layout(rect=(0, 0.075, 1, 1))
        buffer = BytesIO()
        figure.savefig(buffer, format="png", dpi=110)
        buffer.seek(0)
        frames.append(Image.open(buffer).convert("RGB"))
        plt.close(figure)
    frames[0].save(destination, save_all=True, append_images=frames[1:], duration=duration_ms, loop=0, disposal=2)


def plot_motion(items, measurements, destination, display_name="Barnard's Star"):
    """Measured and predicted tracks, visibly separate, on one fixed sky grid."""
    figure, axes = plt.subplots(1, 2, figsize=(12, 5.7))
    norm = common_normalization([item.display_image for item in items])
    axes[0].imshow(np.ma.masked_invalid(items[0].display_image), origin="lower",
                   cmap=plt.get_cmap("gray").with_extremes(bad="#683a68"), norm=norm)
    for index, result in enumerate(measurements):
        axes[0].scatter(result["expected_x"], result["expected_y"], marker="+", s=100, color="#25c8f0")
        axes[1].scatter(result["expected_x"], result["expected_y"], marker="+", s=100, color="#0084a8", label="Expected: linear PM" if index == 0 else None)
        axes[1].annotate(result["midpoint_utc"][:10], (result["expected_x"], result["expected_y"]), xytext=(5, 5), textcoords="offset points", fontsize=7)
        if result["measurement"]["accepted"]:
            for axis in axes:
                axis.scatter(result["measured_x"], result["measured_y"], marker="o", facecolors="none", edgecolors="#e77e00", s=80,
                             label="Measured: local fit" if index == 0 and axis == axes[1] else None)
            axes[1].plot([result["expected_x"], result["measured_x"]], [result["expected_y"], result["measured_y"]], color="gray", linewidth=0.8)
    for axis in axes:
        axis.set_xlabel("Fixed sky x [pixel]")
        axis.set_ylabel("Fixed sky y [pixel]")
    axes[0].set_title("First real aligned frame and all positions")
    axes[1].set_title("Expected and accepted measured positions")
    if not any(result["measurement"]["accepted"] for result in measurements):
        axes[1].text(0.02, 0.02, "No accepted measured centroids\nTarget core fails quality criteria", transform=axes[1].transAxes, fontsize=9,
                     bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "gray"})
    axes[1].legend(fontsize=8)
    axes[1].set_aspect("equal", adjustable="datalim")
    figure.suptitle(f"{display_name} — known-motion validation")
    figure.text(0.5, 0.015, "Prediction excludes annual parallax and perspective. Missing/rejected centroids are not replaced by predictions.", ha="center", fontsize=8)
    figure.tight_layout(rect=(0, 0.055, 1, 0.94))
    figure.savefig(destination, dpi=150)
    plt.close(figure)
