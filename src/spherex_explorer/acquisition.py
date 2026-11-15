"""Task-wide persistent acquisition accounting; every HTTP attempt consumes budget."""
import hashlib
import json
from pathlib import Path
import threading
from datetime import datetime, timezone

from .data_access import download_cutout, parse_artifact_url
from .fits_utils import write_manifest, validate_fits

_LOCK = threading.RLock()


class AcquisitionBudget:
    def __init__(self, project, ledger_path=None, limit=24, reservation=8):
        self.project = Path(project).resolve()
        self.path = Path(ledger_path) if ledger_path else self.project/'outputs/spx006/acquisition_ledger.json'
        if ledger_path and not self.path.exists():
            write_manifest(self.path, {'version':1,'limit':limit,'wiseReservation':reservation,'attempts':[]})

    def snapshot(self):
        with _LOCK:
            return json.loads(self.path.read_text())

    def download(self, url, directory, purpose='dynamic', timeout=45):
        parse_artifact_url(url)
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        cached = list((self.project/'data/raw').rglob(f'*_{digest}.fits'))
        cached += list(Path(directory).glob(f'*_{digest}.fits'))
        if cached:
            validate_fits(cached[0])
            return cached[0]
        with _LOCK:
            ledger = self.snapshot()
            attempts = ledger['attempts']
            dynamic_used = sum(a['purpose'] != 'wise0855' for a in attempts)
            if len(attempts) >= ledger['limit'] or (purpose != 'wise0855' and dynamic_used >= ledger['limit']-ledger['wiseReservation']):
                raise ValueError('The task-wide acquisition budget is exhausted; WISE reservation is protected.')
            entry = {'number': len(attempts)+1, 'purpose': purpose, 'url': url,
                     'startedUtc': datetime.now(timezone.utc).isoformat(), 'status': 'running'}
            attempts.append(entry)
            write_manifest(self.path, ledger)
        result = {'status': 'interrupted', 'error': 'Acquisition did not complete.'}
        try:
            # Disable the helper's internal retries: each retry must be accounted separately.
            path = download_cutout(url, directory, timeout=timeout, attempts=1, max_bytes=32*1024*1024)
            result = {'status': 'downloaded', 'bytes': path.stat().st_size,
                      'localPath': path.relative_to(self.project).as_posix()}
            return path
        except Exception as error:
            result = {'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
            raise
        finally:
            with _LOCK:
                ledger = self.snapshot()
                ledger['attempts'][entry['number']-1].update(result)
                write_manifest(self.path, ledger)
