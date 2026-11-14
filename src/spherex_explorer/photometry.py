"""Original-pixel aperture measurements with explicit, incomplete error accounting.

No PSF fitting, missing-pixel reconstruction, aperture correction or visual-image
photometry is performed. Returned uncertainties are not total uncertainties.
"""
from dataclasses import dataclass
from astropy import units as u
from astropy.stats import sigma_clip
import numpy as np
from scipy.ndimage import maximum_filter


@dataclass(frozen=True)
class ApertureConfig:
    radius: float = 2.0
    inner: float = 4.0
    outer: float = 7.0
    subpixels: int = 8
    minimum_background: int = 30

    def __post_init__(self):
        if not 0 < self.radius < self.inner < self.outer or self.subpixels < 2 or self.minimum_background < 3:
            raise ValueError('Require 0 < aperture < inner annulus < outer annulus and valid sampling.')


def pixel_solid_angles(wcs, shape):
    """Spherical quadrilateral areas in sr, using full spatial WCS including SIP."""
    yy, xx = np.indices((shape[0]+1, shape[1]+1), dtype=float)
    sky = wcs.pixel_to_world(xx-.5, yy-.5).icrs
    lon, lat = sky.ra.rad, sky.dec.rad
    vectors = np.stack([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)], axis=-1)
    def triangle(a,b,c):
        numerator=np.abs(np.sum(a*np.cross(b,c),axis=-1))
        denominator=1+np.sum(a*b,axis=-1)+np.sum(b*c,axis=-1)+np.sum(c*a,axis=-1)
        return 2*np.arctan2(numerator,denominator)
    a,b,c,d=vectors[:-1,:-1],vectors[:-1,1:],vectors[1:,1:],vectors[1:,:-1]
    area=triangle(a,b,c)+triangle(a,c,d)
    if not np.all(np.isfinite(area)&(area>0)):
        raise ValueError('Invalid WCS solid angle.')
    return area


def aperture_weights(shape,x,y,radius,subpixels=8):
    yy,xx=np.indices(shape,dtype=float)
    weights=np.zeros(shape)
    for sy in (np.arange(subpixels)+.5)/subpixels-.5:
        for sx in (np.arange(subpixels)+.5)/subpixels-.5:
            weights+=((xx+sx-x)**2+(yy+sy-y)**2<=radius**2)
    return weights/subpixels**2


def aperture_measurement(image,variance,invalid,wcs,position,background_invalid=None,config=ApertureConfig(),units='MJy/sr'):
    """Measure in-aperture flux density in microJy; never repair invalid source pixels.

    Formal variance = sum((fraction*solid_angle)^2 * VARIANCE) plus uncertainty
    of the clipped annulus mean. A separate empirical background noise floor is
    reported. Pixel covariance, calibration, aperture losses and PSF mismatch are
    not included in the formal uncertainty.
    """
    if not u.Unit(units).is_equivalent(u.MJy/u.sr):
        raise ValueError('IMAGE must contain calibrated surface brightness.')
    image=np.asarray(image,dtype=float);invalid=np.asarray(invalid,dtype=bool)
    if variance is None:
        return {'accepted':False,'reason':'Missing original VARIANCE.','fluxMicroJy':None,'formalErrorMicroJy':None}
    variance=np.asarray(variance,dtype=float)
    if image.shape!=variance.shape or image.shape!=invalid.shape:
        raise ValueError('Image, variance and mask shapes disagree.')
    x,y=(float(v) for v in wcs.world_to_pixel(position))
    result={'accepted':False,'reason':None,'fluxMicroJy':None,'formalErrorMicroJy':None,'snr':None,'xNative':x,'yNative':y,
            'apertureRadiusNativePixels':config.radius,'backgroundAnnulusNativePixels':[config.inner,config.outer],
            'uncertaintyKind':'Formal independent-pixel variance only; not total uncertainty.','apertureCorrectionApplied':False}
    if not np.isfinite(x+y) or min(x,y)<config.outer+.5 or x+config.outer+.5>=image.shape[1] or y+config.outer+.5>=image.shape[0]:
        return result|{'reason':'Aperture/background reaches the original cutout edge.'}
    weights=aperture_weights(image.shape,x,y,config.radius,config.subpixels)
    bad=invalid|~np.isfinite(image)|~np.isfinite(variance)|(variance<=0)
    aperture=weights>.01
    fraction=float((aperture&~bad).sum()/max(1,aperture.sum()))
    result['apertureValidFraction']=fraction
    if np.any(bad&aperture):
        return result|{'reason':'Invalid/flagged or nonpositive-variance source aperture; lost flux is not reconstructed.'}
    yy,xx=np.indices(image.shape)
    radius=np.hypot(xx-x,yy-y)
    background=(radius>=config.inner)&(radius<=config.outer)&~bad
    if background_invalid is not None:
        background &= ~np.asarray(background_invalid,dtype=bool)
    indices=np.flatnonzero(background)
    clipped=sigma_clip(image.ravel()[indices],sigma=3,maxiters=5)
    indices=indices[~np.ma.getmaskarray(clipped)]
    result['backgroundPixels']=len(indices)
    if len(indices)<config.minimum_background:
        return result|{'reason':'Insufficient clean local background pixels.'}
    values=image.ravel()[indices]
    bkg=float(np.mean(values));scatter=float(np.std(values,ddof=1))
    background_variance=float(variance.ravel()[indices].sum()/len(indices)**2)
    areas=pixel_solid_angles(wcs,image.shape)
    conversion=(1*u.Unit(units)).to_value(u.uJy/u.sr)
    factors=weights[aperture]*areas[aperture]*conversion
    flux=float(np.sum((image[aperture]-bkg)*factors))
    pixel_variance=float(np.sum(variance[aperture]*factors**2))
    bkg_term=float(factors.sum()**2*background_variance)
    error=float(np.sqrt(pixel_variance+bkg_term))
    result.update(fluxMicroJy=flux,formalErrorMicroJy=error,snr=flux/error,backgroundMJySr=bkg,
                  backgroundScatterMJySr=scatter,formalPixelVarianceMicroJy2=pixel_variance,
                  formalBackgroundVarianceMicroJy2=bkg_term,
                  empiricalBackgroundFloorMicroJy=float(factors.sum()*scatter/np.sqrt(len(indices))),
                  apertureSolidAngleSr=float(np.sum(weights*areas)),
                  subpixelPhase=[x%1,y%1],units='microJy (in-aperture flux density)')
    local=(radius<=3)&~bad
    peak_index=np.argmax(np.where(local,image,-np.inf))
    py,px=np.unravel_index(peak_index,image.shape)
    result['peakOffsetNativePixels']=float(np.hypot(px-x,py-y))
    if result['peakOffsetNativePixels']>1.5:
        return result|{'reason':'Brightest local peak is displaced from the catalog WCS position; identity/contamination is ambiguous.','fluxMicroJy':None,'formalErrorMicroJy':None,'snr':None}
    if flux<=0 or flux/error<5:
        return result|{'reason':'Nonpositive flux or formal aperture SNR below five.'}
    return result|{'accepted':True,'reason':'Accepted original-pixel aperture measurement; systematic uncertainty remains unvalidated.'}


def measure_observation(observation,position,config=ApertureConfig()):
    """Apply the existing conservative original-FLAGS policy; SOURCE is allowed."""
    from astropy.io import fits
    try:
        variance_unit=fits.getheader(observation.path,'VARIANCE').get('BUNIT')
        compatible=variance_unit is not None and u.Unit(variance_unit)==u.Unit(observation.header.get('BUNIT',''))**2
    except (KeyError,ValueError):
        compatible=False
    if not compatible:
        return {'accepted':False,'reason':'Original VARIANCE units are missing or incompatible.','fluxMicroJy':None,'formalErrorMicroJy':None,'coreQuality':observation.quality_at(position)}
    background_invalid=np.zeros(observation.image.shape,dtype=bool)
    for definition in observation.quality_metadata['definitions']:
        if definition['name']=='SOURCE':
            background_invalid |= (observation.flags & (1<<definition['bit']))!=0
    result=aperture_measurement(observation.image,observation.variance,observation.science_invalid,
        observation.wcs,position,background_invalid,config,observation.header.get('BUNIT',''))
    result['coreQuality']=observation.quality_at(position)
    x,y=observation.wcs.world_to_pixel(position)
    aperture=aperture_weights(observation.image.shape,float(x),float(y),config.radius,config.subpixels)>.01
    result['apertureFlagCounts']={definition['name']:int(np.count_nonzero(aperture & ((observation.flags & (1<<definition['bit']))!=0)))
        for definition in observation.quality_metadata['definitions'] if np.any(aperture & ((observation.flags & (1<<definition['bit']))!=0))}
    return result


def relative_fluxes(fluxes,errors):
    """Ratios to epoch zero and full formal covariance from the shared denominator.

    The reference ratio is exactly one by definition with a zero covariance row;
    this does not imply that the reference flux has zero measurement error.
    """
    f,e=np.asarray(fluxes,dtype=float),np.asarray(errors,dtype=float)
    if f.ndim!=1 or f.shape!=e.shape or not len(f) or not np.all(np.isfinite(f)&np.isfinite(e)&(f>0)&(e>=0)):
        raise ValueError('Relative flux requires positive finite fluxes and nonnegative errors.')
    covariance=np.outer(f,f)*e[0]**2/f[0]**4+np.diag(e**2/f[0]**2)
    covariance[0,:]=0;covariance[:,0]=0
    return {'ratios':(f/f[0]).tolist(),'formalErrors':np.sqrt(np.diag(covariance)).tolist(),
            'formalCovariance':covariance.tolist(),'referenceIndex':0,'sharedReferenceCovarianceIncluded':True}


def spectral_subset(records,fraction=.15):
    """Select by independent visits, baseline and wavelength span, never by flux."""
    if not 0<fraction<=.5:
        raise ValueError('Spectral fraction must be in (0, 0.5].')
    eligible=[r for r in records if r.get('qualityAccepted') and r.get('wavelengthUm') and r.get('bandwidthUm')]
    candidates=[]
    for start in eligible:
        group=sorted([r for r in eligible if r['detector']==start['detector'] and r['release']==start['release'] and r['wavelengthUm']>=start['wavelengthUm']],key=lambda r:r['wavelengthUm'])
        for end in range(1,len(group)+1):
            subset=group[:end]
            spread=subset[-1]['wavelengthUm']-subset[0]['wavelengthUm']
            if spread>fraction*min(r['bandwidthUm'] for r in subset):
                break
            chronological=sorted(subset,key=lambda r:r['mjd'])
            visits=[]
            for record in chronological:
                if not visits or record['mjd']-visits[-1]['mjd']>=1:
                    visits.append(record)
            candidates.append((len(visits),visits[-1]['mjd']-visits[0]['mjd'],-spread,visits))
    return max(candidates,key=lambda item:item[:3])[3] if candidates else []


def reference_positions(observation,target_position,limit=5):
    """Independent compact field peaks selected from one epoch, not by stability."""
    image=observation.image
    x,y=observation.wcs.world_to_pixel(target_position)
    yy,xx=np.indices(image.shape)
    valid=~observation.science_invalid&np.isfinite(image)
    values=np.where(valid,image,-np.inf)
    median=np.median(image[valid]);mad=np.median(np.abs(image[valid]-median))
    peaks=(values==maximum_filter(values,size=7))&valid&(image>median+5*max(1.4826*mad,1e-8))&(np.hypot(xx-x,yy-y)>10)
    peaks &= (xx>9)&(yy>9)&(xx<image.shape[1]-10)&(yy<image.shape[0]-10)
    ordered=sorted(zip(*np.nonzero(peaks)),key=lambda p:values[p],reverse=True)
    selected=[]
    for py,px in ordered:
        if any(np.hypot(px-qx,py-qy)<9 for qy,qx in selected):
            continue
        coordinate=observation.wcs.pixel_to_world(px,py)
        measurement=measure_observation(observation,coordinate)
        if measurement['accepted'] and measurement['snr']>=8:
            selected.append((py,px))
        if len(selected)>=limit:
            break
    return [observation.wcs.pixel_to_world(px,py).icrs for py,px in selected]


def classify_variability(records):
    if not records:
        return 'unavailable'
    return 'exploratory' if len(spectral_subset(records))>=2 else 'diagnostic'


def epsf_diagnostic(observation,position):
    """Read the real nearest detector-zone ePSF; do not mistake it for a native PSF."""
    from astropy.io import fits
    with fits.open(observation.path) as hdus:
        if 'EPSF' not in hdus:
            return {'available':False,'reason':'No EPSF extension.'}
        hdu=hdus['EPSF'];names=hdu.columns.names
        if not {'XCENTER','YCENTER','EPSF'}.issubset(names):
            return {'available':False,'reason':'Unsupported real EPSF schema.'}
        x,y=observation.wcs.world_to_pixel(position)
        x=1+float(x)-observation.header['CRPIX1A'];y=1+float(y)-observation.header['CRPIX2A']
        index=int(np.argmin((hdu.data['XCENTER']-x)**2+(hdu.data['YCENTER']-y)**2))
        row=hdu.data[index]
        return {'available':True,'row':index,'parentPixel':[x,y],
                'oversampling':[hdu.header.get('OVSMPX'),hdu.header.get('OVSMPY')],
                'shape':list(row['EPSF'].shape),
                'effectiveArea':float(row['NEFF_MEAN']) if 'NEFF_MEAN' in names else None,
                'zoneWavelengthUm':float(row['CWAVE']) if 'CWAVE' in names else None,
                'starsInModel':int(row['NSTAR']) if 'NSTAR' in names else None,
                'usedForFluxCorrection':False,
                'limitation':'Oversampled pixel-convolved model requires phase-aware native evaluation and normalization; no validated deblending/aperture correction is applied.'}
