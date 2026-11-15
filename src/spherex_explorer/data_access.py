"""Official IRSA TAP queries, version selection, and bounded cutout downloads."""

from dataclasses import dataclass
import hashlib
import logging
import math
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlsplit

from astropy.time import Time
from astroquery.ipac.irsa import Irsa
import numpy as np
import requests

from .fits_utils import validate_fits

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchParameters:
    """ICRS position, angular cutout width, and documented SPHEREx bandpass."""

    ra: float = 210.80227
    dec: float = 54.34895
    size: float = 0.1
    bandpass: str = "SPHEREx-D2"

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.ra, self.dec, self.size)):
            raise ValueError("Coordinates and size must be finite numbers.")
        if not 0 <= self.ra < 360 or not -90 <= self.dec <= 90:
            raise ValueError("ICRS coordinates require 0 <= RA < 360 and -90 <= DEC <= 90.")
        if not 0 < self.size <= 1:
            raise ValueError("Cutout size must be in (0, 1] degrees (download safety limit).")
        if self.bandpass not in {f"SPHEREx-D{i}" for i in range(1, 7)}:
            raise ValueError("Bandpass must be SPHEREx-D1 through SPHEREx-D6.")


def build_query(parameters: SearchParameters) -> str:
    """Build the cutouts tutorial query using only its documented columns."""
    return f"""SELECT
    'https://irsa.ipac.caltech.edu/' || a.uri || '?center={parameters.ra},{parameters.dec}d&size={parameters.size}' AS uri,
    a.uri AS artifact_uri,
    p.time_bounds_lower,
    p.energy_bandpassname
FROM spherex.artifact a
JOIN spherex.plane p ON a.planeid = p.planeid
WHERE 1 = CONTAINS(POINT('ICRS', {parameters.ra}, {parameters.dec}), p.poly)
    AND p.energy_bandpassname = '{parameters.bandpass}'
ORDER BY p.time_bounds_lower"""


def query_observations(parameters: SearchParameters, timeout: float = 120):
    """Return a table; propagate TAP errors instead of fabricating results."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("TAP timeout must be positive and finite.")
    Irsa.TIMEOUT = timeout
    # Astroquery 0.4.11 delegates TAP to PyVO; TIMEOUT alone is not forwarded.
    # Bound the shared session request for this serial call, restoring it on errors.
    original_request = Irsa._session.request
    def timed_request(*args, **kwargs):
        kwargs.setdefault("timeout", (15, timeout))
        return original_request(*args, **kwargs)
    Irsa._session.request = timed_request
    try:
        result = Irsa.query_tap(build_query(parameters), maxrec=100000)
    finally:
        Irsa._session.request = original_request
    if len(result) >= 100000:
        raise RuntimeError("TAP row limit reached; query completeness cannot be guaranteed.")
    return result.to_table()


def parse_artifact_url(url: str) -> dict:
    """Read identity and processing version from the documented MEF filename."""
    path = urlsplit(url).path
    match = re.fullmatch(r"level2_(.+)D([1-6])_spx_(.+)\.fits", Path(path).name)
    release_match = re.search(r"/spherex/(dr1|qr3|qr2)/level2/", path)
    if not match or not release_match:
        raise ValueError(f"Unrecognized SPHEREx Level 2 artifact URL: {url}")
    return {
        "observation_id": match[1], "detector": int(match[2]),
        "processing_version": match[3], "release": release_match[1],
    }


def _version_rank(record):
    numbers = tuple(int(n) for n in re.findall(r"\d+", record["processing_version"]))
    return ({"dr1": 3, "qr3": 2, "qr2": 1}[record["release"]], numbers, record["url"])


def prepare_observations(table) -> list[dict]:
    """Deduplicate OBSID + detector, preferring DR1, QR3, then QR2 versions.

    time_bounds_lower is the TAP observation lower bound in MJD days. Invalid
    or missing timestamps are rejected because temporal sampling would be unsafe.
    """
    groups = {}
    for row in table:
        url = str(row["uri"])
        record = parse_artifact_url(url)
        raw_time = row["time_bounds_lower"]
        if np.ma.is_masked(raw_time):
            raise ValueError(f"Missing TAP observation timestamp for {url}")
        mjd = float(raw_time)
        if not math.isfinite(mjd):
            raise ValueError(f"Non-finite TAP observation timestamp for {url}")
        record.update(url=url, artifact_uri=str(row["artifact_uri"]),
                      bandpass=str(row["energy_bandpassname"]),
                      mjd=mjd, timestamp=Time(mjd, format="mjd", scale="utc").isot,
                      timestamp_source="spherex.plane.time_bounds_lower (MJD, UTC)")
        key = (record["observation_id"], record["detector"])
        groups.setdefault(key, []).append(record)
    observations = []
    for versions in groups.values():
        chosen = max(versions, key=_version_rank).copy()
        chosen["alternative_versions"] = [
            {key: item[key] for key in ("url", "release", "processing_version")}
            for item in versions if item["url"] != chosen["url"]
        ]
        observations.append(chosen)
    return sorted(observations, key=lambda item: (item["mjd"], item["observation_id"]))


def select_observations(observations: list[dict], limit: int = 8) -> list[dict]:
    """Select nearest observations to evenly spaced time targets, without repeats."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Download limit must be a positive integer.")
    ordered = sorted(observations, key=lambda item: item["mjd"])
    count = min(limit, len(ordered))
    if not count:
        return []
    targets = np.linspace(ordered[0]["mjd"], ordered[-1]["mjd"], count)
    available = set(range(len(ordered)))
    selected = []
    for target in targets:
        index = min(available, key=lambda i: (abs(ordered[i]["mjd"] - target), i))
        available.remove(index)
        selected.append(ordered[index])
    return sorted(selected, key=lambda item: item["mjd"])


def download_cutout(url: str, directory: Path, timeout: float = 120,
                    attempts: int = 3, max_bytes: int = 64 * 1024 * 1024) -> Path:
    """Stream one cutout atomically, with bounded retries and validated reuse."""
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    if (parsed.scheme != "https" or parsed.netloc != "irsa.ipac.caltech.edu"
            or "center" not in query or "size" not in query):
        raise ValueError("Only HTTPS IRSA cutout URLs with center and size are allowed.")
    if attempts < 1 or timeout <= 0:
        raise ValueError("Attempts and timeout must be positive.")
    parse_artifact_url(url)
    if len(query['center']) != 1 or len(query['size']) != 1:
        raise ValueError('Cutout parameters must be unique.')
    coordinates = query['center'][0].removesuffix('d').split(',')
    if len(coordinates) != 2:
        raise ValueError('Cutout center requires RA and Dec.')
    SearchParameters(float(coordinates[0]), float(coordinates[1]), float(query['size'][0]))
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    destination = directory / f"{Path(parsed.path).stem}_{digest}.fits"
    partial = destination.with_suffix(".fits.part")
    if destination.exists():
        validate_fits(destination)
        LOGGER.info("Reusing validated FITS: %s", destination)
        return destination
    for attempt in range(attempts):
        try:
            with requests.get(url, timeout=(15, timeout), stream=True, allow_redirects=False) as response:
                if 300 <= getattr(response, 'status_code', 200) < 400:
                    raise ValueError('Cutout redirects are refused; only the verified official URL is permitted.')
                response.raise_for_status()
                headers = getattr(response, 'headers', {})
                media = headers.get('Content-Type', '').split(';')[0].lower()
                if media and media not in {'image/fits', 'application/fits', 'application/octet-stream', 'binary/octet-stream'}:
                    raise ValueError(f'Unexpected cutout content type: {media}')
                if int(headers.get('Content-Length', 0)) > max_bytes:
                    raise ValueError(f'Cutout exceeds {max_bytes} byte safety limit.')
                total = 0
                began = time.monotonic()
                with partial.open("wb") as stream:
                    for chunk in response.iter_content(chunk_size=65536):
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError(f"Cutout exceeds {max_bytes} byte safety limit.")
                        if time.monotonic()-began > timeout:
                            raise ValueError('Cutout exceeded total streaming time limit.')
                        stream.write(chunk)
            validate_fits(partial)
            partial.replace(destination)
            return destination
        except (requests.RequestException, OSError, ValueError) as error:
            partial.unlink(missing_ok=True)
            transient = isinstance(error, (requests.ConnectionError, requests.Timeout))
            if isinstance(error, requests.HTTPError):
                transient = error.response.status_code in {408, 429, 500, 502, 503, 504}
            if not transient or attempt == attempts - 1:
                raise RuntimeError(f"Cutout download failed ({attempt + 1} attempt(s)): {url}: {error}") from error
            LOGGER.warning("Transient download failure: %s; retrying", error)
            time.sleep(2 ** attempt)
    raise RuntimeError("Download attempts exhausted.")
