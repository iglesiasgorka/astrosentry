"""Offline coverage of query construction, version policy, and bounded download."""

from io import BytesIO

from astropy.io import fits
from astropy.table import Table
import numpy as np
import pytest
import requests

from spherex_explorer.data_access import (
    SearchParameters, build_query, download_cutout, parse_artifact_url,
    prepare_observations, query_observations, select_observations,
)


def artifact(release="dr1", version="l2b-v27-2026-196", obs="2025W18_1B_0074_2"):
    return (f"https://irsa.ipac.caltech.edu/ibe/data/spherex/{release}/level2/"
            f"2025W18_1B/{version}/2/level2_{obs}D2_spx_{version}.fits"
            "?center=210.80227,54.34895d&size=0.1")


def test_official_query():
    query = build_query(SearchParameters())
    assert "FROM spherex.artifact a" in query
    assert "JOIN spherex.plane p ON a.planeid = p.planeid" in query
    assert "POINT('ICRS', 210.80227, 54.34895)" in query
    assert "p.energy_bandpassname = 'SPHEREx-D2'" in query
    assert "?center=210.80227,54.34895d&size=0.1" in query
    assert "ORDER BY p.time_bounds_lower" in query


@pytest.mark.parametrize("arguments", [
    {"ra": -1}, {"ra": 360}, {"ra": float("nan")}, {"dec": 91},
    {"dec": float("inf")}, {"size": 0}, {"size": 1.1},
    {"bandpass": "SPHEREx-D7"}, {"bandpass": "D2' OR 1=1"},
])
def test_invalid_parameters(arguments):
    with pytest.raises(ValueError):
        SearchParameters(**arguments)


def test_boundaries_and_empty_results():
    SearchParameters(0, -90, 1, "SPHEREx-D1")
    SearchParameters(359.999, 90, 0.001, "SPHEREx-D6")
    assert prepare_observations(Table()) == []
    assert select_observations([], 8) == []


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_invalid_limit(limit):
    with pytest.raises(ValueError):
        select_observations([], limit)


def test_versions_are_not_independent_observations():
    urls = [artifact("qr2"), artifact("qr3"), artifact(), artifact(version="l2b-v28-2026-200")]
    table = Table({"uri": urls, "artifact_uri": urls,
                   "time_bounds_lower": [60790.] * 4, "energy_bandpassname": ["SPHEREx-D2"] * 4})
    records = prepare_observations(table)
    assert len(records) == 1
    assert records[0]["release"] == "dr1"
    assert records[0]["processing_version"] == "l2b-v28-2026-200"
    assert records[0]["observation_id"] == "2025W18_1B_0074_2"
    assert len(records[0]["alternative_versions"]) == 3


def test_missing_tap_timestamp_is_rejected():
    table = Table({"uri": [artifact()], "artifact_uri": [artifact()],
                   "time_bounds_lower": [float("nan")], "energy_bandpassname": ["SPHEREx-D2"]})
    with pytest.raises(ValueError, match="timestamp"):
        prepare_observations(table)


def test_unknown_artifact_format_is_rejected():
    with pytest.raises(ValueError, match="Unrecognized"):
        parse_artifact_url("https://irsa.ipac.caltech.edu/unknown.fits")


def test_time_sampling_includes_extremes_and_no_duplicates():
    records = [{"mjd": value} for value in [0, 1, 2, 50, 51, 99, 100]]
    assert [item["mjd"] for item in select_observations(records, 3)] == [0, 50, 100]
    assert select_observations(records, 20) == records


def test_query_uses_irsa_api(monkeypatch):
    class Result:
        def __len__(self):
            return 0
        def to_table(self):
            return Table()
    calls = []
    def fake_query(query, **kwargs):
        calls.append((query, kwargs))
        return Result()
    monkeypatch.setattr("spherex_explorer.data_access.Irsa.query_tap", fake_query)
    assert len(query_observations(SearchParameters())) == 0
    assert "spherex.plane" in calls[0][0]


class Response:
    def __init__(self, content):
        self.content = content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def raise_for_status(self):
        pass
    def iter_content(self, chunk_size):
        yield self.content


def fits_bytes():
    stream = BytesIO()
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((4, 4)), name="IMAGE")]).writeto(stream)
    return stream.getvalue()


def test_download_reuses_valid_file(monkeypatch, tmp_path):
    calls = []
    def get(*args, **kwargs):
        calls.append(args)
        return Response(fits_bytes())
    monkeypatch.setattr(requests, "get", get)
    path = download_cutout(artifact(), tmp_path)
    assert download_cutout(artifact(), tmp_path) == path
    assert len(calls) == 1
    assert not list(tmp_path.glob("*.part"))


def test_invalid_download_is_not_published(monkeypatch, tmp_path):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response(b"<html>not a FITS</html>"))
    with pytest.raises(RuntimeError, match="Cutout download failed"):
        download_cutout(artifact(), tmp_path)
    assert not list(tmp_path.iterdir())


def test_transient_retries_are_bounded(monkeypatch, tmp_path):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise requests.Timeout("Synthetic timeout")
    monkeypatch.setattr(requests, "get", fail)
    monkeypatch.setattr("spherex_explorer.data_access.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="3 attempt"):
        download_cutout(artifact(), tmp_path)
    assert len(calls) == 3


def test_full_image_url_and_oversized_response_are_rejected(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="cutout URLs"):
        download_cutout(artifact().split("?")[0], tmp_path)
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response(fits_bytes()))
    with pytest.raises(RuntimeError, match="safety limit"):
        download_cutout(artifact(), tmp_path, max_bytes=10)
    assert not list(tmp_path.iterdir())


def test_tap_timeout_is_forwarded_and_session_restored(monkeypatch):
    from astroquery.ipac.irsa import Irsa
    calls=[]
    def original(*args,**kwargs):
        calls.append(kwargs)
    monkeypatch.setattr(Irsa._session,'request',original)
    def failure(*args,**kwargs):
        Irsa._session.request('GET','https://example.invalid')
        raise RuntimeError('Synthetic TAP failure')
    monkeypatch.setattr(Irsa,'query_tap',failure)
    with pytest.raises(RuntimeError,match='Synthetic'):
        query_observations(SearchParameters(),timeout=42)
    assert calls[0]['timeout']==(15,42)
    assert Irsa._session.request is original
