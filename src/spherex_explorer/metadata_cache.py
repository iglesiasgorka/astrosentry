"""Explicit provenance for successful metadata caches; failures never become empty data."""
from datetime import datetime,timezone
import json
import time


def utc_now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def cached_result(data,path,status,error=None):
    imported=data.get('cacheImport')
    retrieved=data.get('cachedAtUtc')
    stored=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat().replace('+00:00','Z')
    cache={'status':status,'archiveRetrievedAtUtc':retrieved,'storedAtUtc':stored,
           'timestampBasis':'Recorded successful query time' if retrieved else 'File modification time; original retrieval time was not recorded',
           'origin':'operator-imported-SPX007B' if imported else 'successful-IRSA-query',
           'importedAtUtc':imported.get('importedAtUtc') if imported else None,'upstreamError':error}
    note=f'{status.upper()} successful metadata cache; stored {stored}. '
    if imported:note+='Operator-imported real SPX-007B data, not a live acquisition. '
    if error:note+='IRSA unavailable; cached availability does not establish current archive completeness. '
    return {**data,'cache':cache,'source':data.get('source','IRSA metadata')+' '+note}


def age_seconds(path):return max(0,time.time()-path.stat().st_mtime)


def save_failure(path,error):
    message=getattr(error,'public_message','IRSA metadata request failed; this is not a no-data result.')
    value={'checkedAtUtc':utc_now(),'message':message}
    temporary=path.with_suffix('.part');temporary.write_text(json.dumps(value));temporary.replace(path)
    return value
