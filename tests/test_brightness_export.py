"""Portable brightness export tests use temporary synthetic asset bytes only."""
import json
from pathlib import Path
import pytest
from spherex_explorer.web_export import include_brightness_target


def test_absent_optional_brightness_manifest_preserves_earlier_targets(tmp_path):
    catalog={'targets':[{'id':'earlier'}]}
    assert include_brightness_target(tmp_path,tmp_path/'public',catalog)==catalog
    assert catalog['targets']==[{'id':'earlier'}]


def test_brightness_append_is_portable_and_idempotent(tmp_path):
    root=tmp_path/'outputs/spx004a';(root/'web_data/rw_aur/frames').mkdir(parents=True)
    frames=[]
    for i in range(3):
        assets={key:f'rw_aur/frames/test{i}.{key}' for key in ['fits','png','masks']}
        for path in assets.values():(root/'web_data'/path).write_bytes(b'synthetic test asset, never real science')
        frames.append({'assets':assets})
    target={'id':'rw_aur','brightness':{'classification':'diagnostic'},'sequence':{'frames':frames}}
    (root/'web_target.json').write_text(json.dumps(target))
    catalog={'targets':[{'id':'earlier'}]};output=tmp_path/'public'
    include_brightness_target(tmp_path,output,catalog);include_brightness_target(tmp_path,output,catalog)
    assert len(catalog['targets'])==2
    assert len(list((output/'rw_aur').rglob('*.fits')))==3
    assert not list(output.rglob('aligned.fits'))
    assert str(tmp_path) not in (output/'catalog.json').read_text()


def test_brightness_export_rejects_path_traversal(tmp_path):
    root=tmp_path/'outputs/spx004a';root.mkdir(parents=True)
    (root/'web_target.json').write_text(json.dumps({'id':'rw_aur','brightness':{'classification':'diagnostic'},'sequence':{'frames':[{'assets':{'fits':'../outside.fits'}}]}}))
    with pytest.raises(ValueError,match='portable'):
        include_brightness_target(tmp_path,tmp_path/'public',{'targets':[]})
