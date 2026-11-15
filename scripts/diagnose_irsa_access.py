"""Two bounded metadata probes; never download an observation or retry silently."""
from io import BytesIO
import json
from pathlib import Path
import time

from astropy.io.votable import parse
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/spx007b'


def probe(name, endpoint, params, timeout):
    report = {'service': name, 'endpoint': endpoint, 'parameters': params,
              'timeoutSeconds': timeout, 'maxBytes': 8_000_000, 'retries': 0}
    began = time.monotonic()
    try:
        with requests.get(endpoint, params=params, timeout=(10, timeout), stream=True) as response:
            report.update(url=response.url, status=response.status_code,
                          contentType=response.headers.get('Content-Type'),
                          allowOrigin=response.headers.get('Access-Control-Allow-Origin'))
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > report['maxBytes']:
                    raise ValueError('Metadata exceeds bounded response size.')
            report['bytes'] = len(body)
            (OUT / f'{name}_response.xml').write_bytes(body)
            response.raise_for_status()
            votable = parse(BytesIO(body))
            report['queryStatus'] = [{'name': i.name, 'value': i.value, 'text': i.content}
                                     for r in votable.resources for i in r.infos]
            table = votable.get_first_table().to_table()
            report.update(count=len(table), schema=[{'name': n, 'dtype': str(table[n].dtype),
                          'unit': str(table[n].unit)} for n in table.colnames],
                          firstRows=[{n: str(row[n]) for n in table.colnames} for row in table[:2]])
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    report['elapsedSeconds'] = time.monotonic() - began
    (OUT / f'{name}_diagnosis.json').write_text(json.dumps(report, indent=2) + '\n')
    print(name, {k: report.get(k) for k in ['status', 'bytes', 'count', 'error', 'elapsedSeconds']}, flush=True)


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    for name in ['tap', 'sia2']:
        if (OUT / f'{name}_diagnosis.json').exists():
            raise SystemExit('Probe evidence exists. Review it before issuing any additional metadata requests.')
    probe('tap', 'https://irsa.ipac.caltech.edu/TAP/sync',
          {'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'votable', 'MAXREC': '1',
           'QUERY': 'SELECT TOP 1 time_bounds_lower FROM spherex.plane'}, 15)
    probe('sia2', 'https://irsa.ipac.caltech.edu/SIA',
          [('POS', 'CIRCLE 304.693508808 42.4436872991 0.0002777777777777778'),
           ('COLLECTION', 'spherex_dr1'), ('COLLECTION', 'spherex_qr3'), ('MAXREC', '1000')], 40)
