"""Prepare SPX-004B exclusively from local observations and append its web assets."""
from pathlib import Path
import json
from spherex_explorer.change_explorer import prepare,include_change_targets

if __name__ == '__main__':
    project=Path(__file__).resolve().parents[1]
    result=prepare(project)
    output=project/'frontend/public/data'
    catalog=json.loads((output/'catalog.json').read_text(encoding='utf-8'))
    include_change_targets(project,output,catalog)
    print(f"Original FITS: {result['inventory']['originalFitsCount']}; valid: {result['inventory']['validOriginalFitsCount']}")
    print(f"Epsilon D6 observations: {len(result['target']['sequence']['frames'])}; independent visits: {result['target']['sequence']['independentVisitCount']}")
    print('Prepared historical signed Difference B-A; no scientific acquisition occurred.')
