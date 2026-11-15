"""Export WISE/R Dra from local real data without rewriting earlier science/assets."""
from pathlib import Path
from types import SimpleNamespace
import json
import shutil

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np

from spherex_explorer.dynamic import export_aligned_sequence
from spherex_explorer.observation import Observation
from spherex_explorer.fits_utils import write_manifest

PROJECT=Path(__file__).resolve().parents[1]


def load_items(directory,manifest):
    items=[]
    for record in manifest['observations']:
        path=Path(record['local_path']);path=path if path.is_absolute() else PROJECT/path
        obs=Observation.read(path,record['release'])
        with fits.open(directory/record['aligned_asset']) as hdus:
            items.append(SimpleNamespace(observation=obs,wcs=WCS(hdus['IMAGE'].header),image=np.array(hdus['IMAGE'].data),
                display_image=np.array(hdus['DISPLAY'].data),coverage=np.array(hdus['COVERAGE'].data,dtype=bool),
                display_coverage=np.isfinite(hdus['DISPLAY'].data)))
    return items


def export_one(key,directory,name):
    manifest=json.loads((directory/'observations.json').read_text());items=load_items(directory,manifest)
    if len(items)<2:return None
    positions={};warnings=[]
    if key=='wise0855':
        warnings=['Diagnostic WISE 0855 field: no accepted centroid pair at compatible wavelengths; no measured displacement.',
            'The historical challenge coordinate is not its position at every epoch; cyan marks use the documented linear catalog prediction.',
            'Annual parallax (~0.439 arcsec), observer position and other systematics are omitted. Predictions are not measurements.',
            'Isolated fits at incompatible wavelengths are retained privately as diagnostics and not promoted to a validated WISE measurement.']
        for record in manifest['observations']:
            c=record['target_centroid'];x,y=c['expected_x'],c['expected_y'];height=items[0].image.shape[0]
            positions[record['observation_id']]={'expectedPosition':{'raDeg':c['expected_ra_deg'],'decDeg':c['expected_dec_deg'],
                'xFits':x,'yFits':y,'xImage':x,'yImage':height-1-y},'measuredPosition':None}
    else:
        warnings=['R Draconis is a known Mira variable; that catalog knowledge does not validate these SPHEREx aperture measurements.',
            'Source apertures have invalid/OVERFLOW/SUR_ERROR/BLOOM pixels. Rejected fluxes remain null; no quantitative variability curve.',
            'The available D2 wavelengths differ; these five frames are inspection-only, not a homogeneous temporal measurement.']
    root=PROJECT/'outputs/spx006c/web_data'
    target=export_aligned_sequence(items,manifest['observations'],root,key,key,name,warnings,positions)
    target['objectType']='Cold brown dwarf · diagnostic predictions' if key=='wise0855' else 'Known Mira variable · rejected photometry'
    if key=='wise0855':
        target['sequence']['predictionModel']=manifest['predicted_motion_model']
        target['sequence']['astrometricReference']=manifest['target']
        report=json.loads((directory/'alignment_report.json').read_text());motion=report['motion'];references=report.get('background_reference_residuals',{})
        if len(manifest['sequence_ids'])==2:
            pair=[next(f['id'] for f in target['sequence']['frames'] if f['observation']['id']==identifier) for identifier in manifest['sequence_ids']]
            target['sequence']['historicalPair']={'aId':pair[0],'bId':pair[1]}
            target['sequence']['motion']={'measuredDisplacementArcsec':None,'measuredDisplacementPixels':None,
                'formalEndpointErrorArcsec':None,'expectedDisplacementArcsec':motion['expected_displacement_arcsec'],
                'expectedDisplacementPixels':motion['expected_displacement_pixels'],'timeSeparationDays':motion['time_separation_days'],
                'referenceRmsArcsec':references.get('rms_arcsec'),'referenceCount':references.get('matched_source_count')}
            target['sequence']['interpretation']='WISE 0855 diagnostic: the compatible 2025/2026 pair has predicted linear displacement only; both endpoint centroid fits are rejected. No SPHEREx motion is measured.'
    else:
        old=json.loads((PROJECT/'outputs/spx004a/r_dra/photometry.json').read_text());by_id={r['id']:r for r in old['records']};points=[]
        for frame in target['sequence']['frames']:
            r=by_id[frame['observation']['id']]
            points.append({k:r.get(k) for k in ['id','timestampUtc','mjd','wavelengthUm','qualityAccepted','comparisonAccepted','fluxMicroJy','formalErrorMicroJy','relativeFlux','relativeFormalError','relativeChangePercent','reason']}|{'id':frame['id'],'coreFlags':r['measurement']['coreQuality'].get('flag_pixel_counts',{}),'apertureValidFraction':r['measurement'].get('apertureValidFraction')})
        target['brightness']={'classification':old['classification'],'interpretation':old['interpretation'],'method':old['method'],
            'units':'microJy (in-aperture flux density)','points':points,'warnings':warnings,
            'references':[{'id':r['id'],'acceptedEpochs':r['acceptedEpochs'],'relativeScatter':r['relativeScatter'],'spectrallyMatched':r['spectrallyMatched']} for r in old['references']],
            'normalization':old['normalization']}
    write_manifest(root/key/'target.json',target)
    assets={asset for frame in target['sequence']['frames'] for asset in frame['assets'].values()}
    for asset in assets:
        destination=PROJECT/'frontend/public/data'/asset;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/asset,destination)
    write_manifest(PROJECT/'outputs/spx006c'/key/'web_target.json',target)
    return target


if __name__=='__main__':
    path=PROJECT/'frontend/public/data/catalog.json';catalog=json.loads(path.read_text());new=[]
    for key,directory,name in [('r_dra',PROJECT/'outputs/spx004a/r_dra/preparation','R Draconis'),('wise0855',PROJECT/'outputs/spx006c/wise0855','WISE 0855')]:
        if (directory/'observations.json').exists():
            target=export_one(key,directory,name)
            if target:new.append(target)
    old_ids={t['id'] for t in new};catalog['targets']=[t for t in catalog['targets'] if t['id'] not in old_ids]+new
    write_manifest(PROJECT/'outputs/spx006c/extension.json',{'targets':new})
    write_manifest(path,catalog)
    write_manifest(PROJECT/'outputs/spx006c/export_summary.json',{'added':[{t['id']:len(t['sequence']['frames'])} for t in new],
        'webFrames':sum(len(t['sequence']['frames']) for t in catalog['targets']),'originalFits':len(list((PROJECT/'data/raw').rglob('*.fits'))),
        'oldTargetEntriesChanged':False})
    print(json.dumps({'targets':len(catalog['targets']),'epochs':sum(len(t['sequence']['frames']) for t in catalog['targets'])}))
