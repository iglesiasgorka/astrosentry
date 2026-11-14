"""Offline SPX-004A evaluation and display-only export of the bounded experiment."""
import csv
import hashlib
import json
from pathlib import Path
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from astropy.io import fits
from astropy.wcs import WCS
from astropy.visualization import ImageNormalize,AsinhStretch
import numpy as np
from PIL import Image
from .observation import Observation
from .targets import predict_position
from .fits_utils import write_manifest
from .photometry import (ApertureConfig,measure_observation,reference_positions,relative_fluxes,
    spectral_subset,classify_variability,epsf_diagnostic)
from .web_export import sky_geometry,display_limits

WARNINGS=[
    'No reliable SPHEREx variability is established by this bounded experiment.',
    'Known variability of the source does not validate these individual measurements.',
    'Reject invalid or OVERFLOW-flagged aperture pixels; missing flux is never reconstructed.',
    'In-aperture flux is not aperture-corrected total flux. PSF, subpixel, calibration and blending systematics remain unvalidated.',
    'RW Aur is an unresolved multiple system; component fluxes are not deblended.',
    'WCS-WAVE wavelengths are preliminary screening metadata, not full science response calibration; CWAVE/CBAND calibration and bandpass matching are not validated.',
    'Formal independent-pixel errors omit covariance and calibration systematics; they are not total uncertainty.',
]


def evaluate_candidate(project,key):
    directory=project/'outputs/spx004a'/key
    manifest=json.loads((directory/'preparation/observations.json').read_text())
    records=[];objects={}
    for record in manifest['observations']:
        obs=Observation.read(project/record['local_path'],record['release'])
        position=predict_position(manifest['target'],obs.midpoint)
        measured=measure_observation(obs,position)
        item={'id':obs.observation_id,'detector':int(record['detector']),'release':record['release'],
              'timestampUtc':obs.midpoint.utc.isot,'mjd':float(obs.midpoint.utc.mjd),
              'wavelengthUm':record['wavelength_um'],'bandwidthUm':record['bandwidth_um'],
              'qualityAccepted':measured['accepted'],'comparisonAccepted':False,'measurement':measured,
              'fluxMicroJy':measured.get('fluxMicroJy'),'formalErrorMicroJy':measured.get('formalErrorMicroJy'),
              'reason':measured['reason'],'sourceRecord':record,'epsf':epsf_diagnostic(obs,position)}
        variants=[]
        for config in [ApertureConfig(1.75,4,7),ApertureConfig(2.25,4,7),ApertureConfig(2,5,8)]:
            variants.append(measure_observation(obs,position,config))
        for dx,dy in [(.15,0),(-.15,0),(0,.15),(0,-.15)]:
            x,y=obs.wcs.world_to_pixel(position)
            variants.append(measure_observation(obs,obs.wcs.pixel_to_world(x+dx,y+dy)))
        item['sensitivityVariants']=variants
        records.append(item);objects[(item['id'],item['detector'])]=obs
    records.sort(key=lambda r:r['mjd'])
    comparable=spectral_subset(records)
    if len(comparable)>=2:
        normalized=relative_fluxes([r['fluxMicroJy'] for r in comparable],[r['formalErrorMicroJy'] for r in comparable])
        for index,record in enumerate(comparable):
            record.update(comparisonAccepted=True,relativeFlux=normalized['ratios'][index],relativeFormalError=normalized['formalErrors'][index],relativeChangePercent=100*(normalized['ratios'][index]-1))
    else:
        normalized=None
    classification=classify_variability(records)
    # Choose the shorter-wave follow-up for the diagnostic display, never by flux change.
    display=[r for r in records if r['detector']==1] or records
    refs=[]
    if display:
        first=objects[(display[0]['id'],display[0]['detector'])]
        candidates=reference_positions(first,predict_position(manifest['target'],first.midpoint))
        for index,position in enumerate(candidates):
            measurements=[]
            for record in display:
                obs=objects[(record['id'],record['detector'])]
                measurement=measure_observation(obs,position)
                measurements.append({'id':record['id'],'measurement':measurement,'spectrum':obs.spectral_at(position)})
            good=[r for r in measurements if r['measurement']['accepted']]
            spectrally_matched=len(good)>=2 and max(r['spectrum']['wavelength_um'] for r in good)-min(r['spectrum']['wavelength_um'] for r in good)<=.15*min(r['spectrum']['bandwidth_um'] for r in good)
            ratios=relative_fluxes([r['measurement']['fluxMicroJy'] for r in good],[r['measurement']['formalErrorMicroJy'] for r in good]) if spectrally_matched else None
            refs.append({'id':f'R{index+1}','raDeg':position.ra.deg,'decDeg':position.dec.deg,'measurements':measurements,
                         'acceptedEpochs':len(good),'spectrallyMatched':spectrally_matched,
                         'relativeScatter':float(np.std(ratios['ratios'],ddof=1)) if ratios else None,
                         'warning':'Compact field candidate, not certified constant; independent of the target.'})
    interpretation=(f'{classification.capitalize()} brightness comparison: {sum(r["comparisonAccepted"] for r in records)} spectrally comparable accepted epochs; '
                    'no validated variability claim. Rejected aperture fluxes remain null.')
    result={'target':manifest['target'],'classification':classification,'interpretation':interpretation,
            'records':records,'references':refs,'normalization':normalized,'warnings':WARNINGS,
            'failedDownloads':manifest['failures'],'spectralFraction':.15,'comparableEpochIds':[r['id'] for r in comparable] if len(comparable)>=2 else [],
            'method':'Original IMAGE aperture r=2 native pixels; sigma-clipped SOURCE-masked annulus 4–7 pixels; full SIP WCS spherical pixel solid angles; original VARIANCE.',
            'psfDecision':'Real nearest-zone oversampled EPSF inspected. A phase-normalized, deblended native fit is not validated; flagged source cores cannot be repaired by fitting. Use controlled aperture rejection, not inferred missing flux.'}
    write_manifest(directory/'photometry.json',result)
    columns=['id','timestampUtc','detector','release','wavelengthUm','bandwidthUm','qualityAccepted','comparisonAccepted','fluxMicroJy','formalErrorMicroJy','reason']
    with (directory/'photometry.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        writer.writerows({k:r[k] for k in columns} for r in records)
    write_manifest(directory/'quality_diagnostics.json',{'records':[{'id':r['id'],'detector':r['detector'],'measurement':r['measurement'],'variants':r['sensitivityVariants'],'epsf':r['epsf']} for r in records]})
    write_manifest(directory/'references.json',refs)
    from astropy.time import Time
    fig,ax=plt.subplots(figsize=(9,4))
    accepted=[r for r in display if r['comparisonAccepted']]
    if accepted:
        ax.errorbar([Time(r['timestampUtc']).to_datetime() for r in accepted],[r['fluxMicroJy'] for r in accepted],yerr=[r['formalErrorMicroJy'] for r in accepted],fmt='o',linestyle='none',label='Formal errors only')
        ax.legend()
    else:
        ax.text(.5,.5,'No accepted spectrally comparable measurements\nNo variability curve can be inferred',ha='center',va='center',transform=ax.transAxes)
        ax.set_yticks([])
    if display:
        dates=[Time(r['timestampUtc']).to_datetime() for r in display]
        ax.set_xlim(min(dates),max(dates));ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.set(xlabel='Observation midpoint (UTC)',ylabel='In-aperture flux density (microJy)',title=f'{manifest["target"]["name"]} — {classification}')
    fig.autofmt_xdate();fig.tight_layout();fig.savefig(directory/'flux_vs_time.png',dpi=160);plt.close(fig)
    return result,display


def export_brightness(project,result,records):
    """Export only local display derivatives; scientific photometry is precomputed."""
    key=result['target']['key'];root=project/'outputs/spx004a/web_data';folder=root/key
    folder.mkdir(parents=True,exist_ok=True)
    arrays=[]
    for record in records:
        source=project/'outputs/spx004a'/key/'preparation'/record['sourceRecord']['aligned_asset']
        with fits.open(source) as hdus:
            arrays.append((np.array(hdus['DISPLAY'].data,dtype=float),hdus['DISPLAY'].header.copy(),np.array(hdus['COVERAGE'].data,dtype=bool)))
    first=arrays[0];wcs=WCS(first[1]);shape=first[0].shape
    geometry=sky_geometry(wcs,shape,float(wcs.wcs.crval[0]),float(wcs.wcs.crval[1]),6.2)
    low,high=display_limits(np.concatenate([a[np.isfinite(a)] for a,_,_ in arrays]))
    display={'vmin':low,'vmax':high,'stretch':'asinh','common':True,'pngAsinhParameter':.1,'units':first[1].get('BUNIT')}
    normalization=ImageNormalize(vmin=low,vmax=high,stretch=AsinhStretch())
    cmap=plt.get_cmap('gray').with_extremes(bad='#683a68');frames=[];points=[]
    for record,(values,header,science) in zip(records,arrays):
        if values.shape!=shape or dict(WCS(header).to_header())!=dict(wcs.to_header()):
            raise ValueError('Brightness display frames must share one fixed WCS.')
        identifier=record['id'];prefix=f'{key}/frames/{identifier}'
        assets={'fits':prefix+'.fits','png':prefix+'.png','masks':prefix+'.masks.json'}
        (root/assets['fits']).parent.mkdir(parents=True,exist_ok=True)
        h=wcs.to_header();h['BUNIT']=header.get('BUNIT');h['OBSID']=identifier;h['DATE-AVG']=record['timestampUtc'];h['DATAMIN']=low;h['DATAMAX']=high
        h['HISTORY']='SPX-004A display only; photometry measured on original IMAGE, not this aligned array.'
        fits.PrimaryHDU(values.astype(np.float32),h).writeto(root/assets['fits'],overwrite=True)
        Image.fromarray(np.flipud(cmap(normalization(np.ma.masked_invalid(values)),bytes=True))).save(root/assets['png'])
        pack=lambda mask:base64.b64encode(np.packbits(mask.ravel(),bitorder='little').tobytes()).decode()
        write_manifest(root/assets['masks'],{'encoding':'packed-bits-base64','bitOrder':'little','shape':list(shape),'origin':'FITS bottom-left','displayValid':pack(np.isfinite(values)),'scienceValid':pack(science)})
        source=record['sourceRecord']
        observation={'id':identifier,'timestampUtc':record['timestampUtc'],'detector':f'SPHEREx-D{record["detector"]}','release':record['release'],'processingVersion':source['processing_version'],'wavelengthUm':record['wavelengthUm'],'bandwidthUm':record['bandwidthUm']}
        frames.append({'id':identifier,'observation':observation,'assets':assets,'display':display,'warnings':WARNINGS,
                       'expectedPosition':None,'measuredPosition':None,'formalCentroidErrorArcsec':None,'formalCentroidErrorOriginalPixels':None,
                       'masks':{'displayValidFraction':float(np.isfinite(values).mean()),'scienceValidFraction':float(science.mean())},
                       'provenance':{'sourceUrl':source['url'],'sourceSha256':hashlib.sha256((project/source['local_path']).read_bytes()).hexdigest()}})
        points.append({k:record.get(k) for k in ['id','timestampUtc','mjd','wavelengthUm','qualityAccepted','comparisonAccepted','fluxMicroJy','formalErrorMicroJy','relativeFlux','relativeFormalError','relativeChangePercent','reason']}|{'coreFlags':record['measurement']['coreQuality'].get('flag_pixel_counts',{}),'apertureValidFraction':record['measurement'].get('apertureValidFraction')})
    target={'id':key,'name':result['target']['name'],'objectType':result['target']['object_type'],**geometry,
            'classification':result['classification'],'observation':frames[0]['observation'],'assets':frames[0]['assets'],
            'display':display,'warnings':WARNINGS,
            'sequence':{'frames':frames,'display':display,'motion':None,'warnings':WARNINGS,'classification':result['classification'],
                        'interpretation':result['interpretation'],'predictionModel':None,'astrometricReference':None},
            'brightness':{'classification':result['classification'],'interpretation':result['interpretation'],'method':result['method'],
                          'units':'microJy (in-aperture flux density)','points':points,'warnings':WARNINGS,
                          'references':[{'id':r['id'],'acceptedEpochs':r['acceptedEpochs'],'relativeScatter':r['relativeScatter'],'spectrallyMatched':r['spectrallyMatched']} for r in result['references']],
                          'normalization':result['normalization']}}
    write_manifest(project/'outputs/spx004a/web_target.json',target)
    write_manifest(root/'sequence_manifest.json',target)
    portable=json.loads(json.dumps(target))
    for assets in [portable['assets']]+[frame['assets'] for frame in portable['sequence']['frames']]:
        for name,path in assets.items():
            assets[name]='web_data/'+path
    write_manifest(project/'outputs/spx004a/sequence_manifest.json',portable)
    write_manifest(project/'outputs/spx004a'/key/'sequence_manifest.json',{'canonicalManifest':'../sequence_manifest.json','classification':result['classification']})
    return target


def run(project):
    project=Path(project)
    summaries=[];all_records=[]
    for key in ['r_dra','rw_aur']:
        result,display=evaluate_candidate(project,key)
        all_records.extend(dict(record,target=key) for record in result['records'])
        summaries.append({'target':key,'classification':result['classification'],'downloaded':len(result['records']),
                          'accepted':sum(r['qualityAccepted'] for r in result['records']),'comparable':sum(r['comparisonAccepted'] for r in result['records'])})
        if key=='rw_aur' and len(display)>=2:
            export_brightness(project,result,display)
    write_manifest(project/'outputs/spx004a/summary.json',summaries)
    write_manifest(project/'outputs/spx004a/photometry.json',{'records':all_records,'summary':summaries,'validatedVariability':False})
    base=project/'outputs/spx004a'
    ledger=json.loads((base/'requests.json').read_text())
    write_manifest(base/'observations.json',{'requests':ledger['requests'],'budget':ledger['budget'],'requestsUsed':len(ledger['requests']),'downloaded':sum(r['status']=='downloaded' for r in ledger['requests']),'selectionPolicy':json.loads((base/'selection_policy.json').read_text())})
    columns=['target','id','timestampUtc','detector','release','wavelengthUm','qualityAccepted','comparisonAccepted','fluxMicroJy','formalErrorMicroJy','reason']
    with (base/'photometry.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows({k:r[k] for k in columns} for r in all_records)
    return summaries
