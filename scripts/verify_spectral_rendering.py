"""Check saved official metadata, real HiPS responses and drawn canvas differences.

This verifies channel addressing and changes in rendered imagery. It is not
spectral calibration, source photometry or an individual-pixel HiPS WCS test.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]


def main():
    directory = PROJECT/'outputs/spx005'
    table = json.loads((directory/'channels.json').read_text())
    raw = (directory/'hips_properties.txt').read_bytes()
    properties = dict(line.split('=', 1) for line in raw.decode().splitlines()
                      if '=' in line and not line.lstrip().startswith('#'))
    properties = {k.strip(): v.strip() for k, v in properties.items()}
    values = list(map(float, properties['data_cube_crval3_arr'].split()))
    assert len(values) == 102 and table['excludedFrames'] == [50, 51]
    assert hashlib.sha256(raw).hexdigest() == table['propertiesSha256']
    assert len(table['channels']) == 100
    for channel in table['channels']:
        index = channel['frameIndex']
        assert index == 17*(channel['band']-1)+channel['channel']-1
        assert index not in [50, 51] and channel['wavelengthUm'] == values[index]
    assert values[29] == 1.481
    network = json.loads((directory/'spectral_network.json').read_text())
    frames = {}
    for index in network['verifiedFrames']:
        tiles = [tile for tile in network['tiles'] if tile['frame'] == index and tile['status'] == 200]
        assert tiles
        coarse = {tile['pixel'] for tile in tiles if tile['order'] == 0}
        if index != 101:
            assert len(coarse) == 12
        frames[str(index)] = {'successfulResponses': len(tiles), 'uniqueCoarsePixels': len(coarse)}
    canvas_checks = []
    signatures = network['canvasSignatures']
    for previous, current in zip(signatures, signatures[1:]):
        a = np.asarray(previous['pixels'], dtype=float).reshape(-1, 4)[:, :3]
        b = np.asarray(current['pixels'], dtype=float).reshape(-1, 4)[:, :3]
        delta = np.abs(a-b)
        changed = int((delta > 2).sum())
        assert changed > 50
        canvas_checks.append({'fromFrame': previous['frame'], 'toFrame': current['frame'],
                              'changedColorComponents': changed,
                              'meanAbsolute8BitDifference': float(delta.mean()), 'passed': True})
    report = {'officialValidChannels': 100, 'initialFrame': 29, 'initialWavelengthUm': 1.481,
              'liveFrames': frames, 'drawnCanvasComparisons': canvas_checks,
              'pageErrors': network['pageErrors'], 'passed': not network['pageErrors']}
    (directory/'spectral_rendering_check.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
