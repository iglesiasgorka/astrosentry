"""Rebuild SPX-004A photometry and the fourth web field offline from local inputs."""
from pathlib import Path
import json
from spherex_explorer.variability_pipeline import run
from spherex_explorer.web_export import include_brightness_target

if __name__=='__main__':
    project=Path(__file__).resolve().parents[1]
    print(run(project))
    output=project/'frontend/public/data'
    catalog=json.loads((output/'catalog.json').read_text())
    include_brightness_target(project,output,catalog)
