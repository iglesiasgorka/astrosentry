import type { Camera, EngineSnapshot, LonLat, SkyEngine, SkyTarget, SurveyStatus } from '../../types/sky';
import { assetUrl } from '../../data/catalog';
import { SPHEREX_URL, TWO_MASS_URL, parseProperties, cubeFrame } from './surveys';

export const HOME_CAMERA: Camera = { center:[270,0], fov:360 };

/** The untyped library boundary is confined to this Aladin Lite 3.8.2 adapter. */
export async function createSkyEngine(host: HTMLDivElement, targets: SkyTarget[],
                                      surveyChanged: (status: SurveyStatus)=>void): Promise<SkyEngine> {
  const began=performance.now();
  const { default:A } = await import('aladin-lite');
  await A.init;
  const aladin=A.aladin(host,{
    survey:[], hipsList:[], target:'270 +0', fov:360, projection:'AIT', cooFrame:'ICRS',
    showZoomControl:false, showLayersControl:false, showFullscreenControl:false,
    showShareControl:false, showSimbadPointerControl:false, showCooGridControl:false,
    showSettingsControl:false, showProjectionControl:false, showFrame:false,
    showFov:false, showCooLocation:false, showReticle:false, showCooGrid:false, showStatusBar:false,inertia:false,
    backgroundColor:'rgb(5, 10, 17)', log:false,
  });
  let disposed=false, raf=0, cutoutToken=0, surveyToken=0;
  let activeImage:any=null, activeId:string|null=null, imageLoaded=false, nativeCenter:LonLat|null=null,frameIndex=0,frameId:string|null=null;
  type Layer={image:any;ready:boolean;promise:Promise<void>;center:LonLat|null;loadMs:number|null;layerName:string};
  const layers=new Map<string,Layer>();
  let releaseInitialBackground!:()=>void,backgroundSlotReserved=false;
  const initialBackground=new Promise<void>(resolve=>{releaseInitialBackground=resolve;});
  let activeSurvey:SurveyStatus|null=null;
  const listeners=new Set<()=>void>();
  const footprint=A.graphicOverlay({color:'#68d6e7',lineWidth:1.6});
  aladin.addOverlay(footprint);
  for(const target of targets)footprint.addFootprints([A.polygon(target.footprint)]);
  const snapshot=():EngineSnapshot=>({center:Array.from(aladin.getRaDec()) as LonLat,fov:aladin.getFov()[0],size:aladin.getSize()});
  let footprintVisible=false;footprint.hide();
  const emit=()=>{if(disposed||raf)return;raf=requestAnimationFrame(()=>{raf=0;if(disposed)return;const visible=snapshot().fov<6;if(visible!==footprintVisible){footprintVisible=visible;visible?footprint.show():footprint.hide();}listeners.forEach(listener=>listener());});};
  aladin.on('positionChanged',emit);aladin.on('zoomChanged',emit);
  const resize=new ResizeObserver(emit);resize.observe(host);
  const hideCutout=()=>{
    cutoutToken++;activeId=null;imageLoaded=false;nativeCenter=null;frameId=null;
    for(const layer of layers.values())if(layer.ready&&layer.image.getOpacity()!==0)layer.image.setOpacity(0);
    activeImage=null;
    emit();
  };
  const ensureFrame=(target:SkyTarget,index:number):Layer=>{
    const frame=target.sequence?.frames[index];
    if(index<0||(!frame&&index!==0))throw new Error('The requested real observation does not exist.');
    const key=`${target.id}:${frame?.id??target.observation.id}`;
    const existing=layers.get(key);if(existing)return existing;
    const entry:Layer={image:null,ready:false,promise:Promise.resolve(),center:null,loadMs:null,layerName:`local-${target.id}-${index}`};
    layers.set(key,entry);
    const start=performance.now(),display=target.sequence?.display??target.display;
    entry.promise=(async()=>{
      // In 3.8.2 setBaseImageLayer replaces overlayLayers[0]. Reserve the survey
      // slot before local layers: otherwise a late survey silently replaces frame 0.
      await initialBackground;
      const url=assetUrl(frame?.assets.fits??target.assets.fits);
      // A missing local asset must fail locally, before Aladin's remote FITS-proxy fallback.
      const available=await fetch(url,{method:'HEAD',signal:AbortSignal.timeout(10000)});
      if(!available.ok)throw new Error(`Local observation ${index+1} returned HTTP ${available.status}.`);
      if(disposed)throw new Error('Sky engine was disposed.');
      await new Promise<void>((resolve,reject)=>{
        let settled=false;
        const timeout=window.setTimeout(()=>done(new Error('Local FITS layer timed out.')),15000);
        const done=(error?:unknown)=>{if(settled)return;settled=true;clearTimeout(timeout);if(error)reject(error);else resolve();};
        entry.image=A.image(url,{name:`SPHEREx · ${target.name} · ${index+1}`,imgFormat:'fits',
          minCut:display.vmin,maxCut:display.vmax,stretch:'asinh',colormap:'grayscale',opacity:0,
          successCallback:(ra:number,dec:number)=>{
            if(disposed){done(new Error('Sky engine was disposed.'));return;}
            try{
              // 3.8.2 substitutes inferred cuts for falsy zero cuts on initial load.
              // Reapply explicit common cuts after native loading, then verify them.
              entry.image.setCuts(display.vmin,display.vmax,'fits');
              entry.image.setColormap('grayscale',{stretch:'asinh'});
              const cuts=entry.image.getCuts();
              if(cuts[0]!==display.vmin||cuts[1]!==display.vmax)throw new Error('Common intensity cuts were not applied.');
              entry.center=[ra,dec];entry.ready=true;entry.loadMs=performance.now()-start;done();
            }catch(error){done(error);}
          },errorCallback:(error:unknown)=>done(error||new Error('The local FITS could not load.'))});
        try{aladin.setOverlayImageLayer(entry.image,entry.layerName);}catch(error){done(error);}
      });
    })().catch(error=>{layers.delete(key);throw error;});
    return entry;
  };
  const showFrame=async(target:SkyTarget,index:number)=>{
    const token=++cutoutToken;activeId=target.id;imageLoaded=false;
    const entry=ensureFrame(target,index);await entry.promise;
    if(disposed||token!==cutoutToken)return;
    for(const layer of layers.values())if(layer.ready&&layer.image.getOpacity()!==(layer===entry?1:0))layer.image.setOpacity(layer===entry?1:0);
    activeImage=entry.image;nativeCenter=entry.center;frameIndex=index;
    frameId=target.sequence?.frames[index]?.id??target.observation.id;imageLoaded=true;emit();
  };
  const setSurvey=async(id:string)=>{
    const token=++surveyToken;
    const attempt=async(surveyId:string)=>{
      const cube=surveyId==='spherex';
      const url=cube?SPHEREX_URL:TWO_MASS_URL;
      surveyChanged({id:surveyId,name:cube?'SPHEREx DR1 all-sky':'2MASS K',state:'loading'});
      const response=await fetch(`${url}/properties`,{signal:AbortSignal.timeout(12000)});
      if(!response.ok)throw new Error(`HiPS metadata returned HTTP ${response.status}`);
      const properties=parseProperties(await response.text());
      if(disposed||token!==surveyToken)return;
      const selected=cube?cubeFrame(properties):null;
      // Let Aladin request its progressive tile pyramid immediately. An extra serial
      // tile preflight previously delayed first paint and duplicated the first tile.
      if(disposed||token!==surveyToken)return;
      let restore:SkyTarget|undefined,restoreIndex=frameIndex;
      if(!backgroundSlotReserved&&layers.size){
        // A later successful survey after an offline start must establish a base
        // slot without sacrificing the first previously visible local observation.
        const pending=[...layers.values()].filter(entry=>entry.image);
        if(pending.length){await Promise.allSettled(pending.map(entry=>entry.promise));restore=targets.find(target=>target.id===activeId);
          hideCutout();for(const entry of pending)aladin.removeImageLayer(entry.layerName);layers.clear();}
      }
      await new Promise<void>((resolve,reject)=>{
        let settled=false;
        const timeout=window.setTimeout(()=>{if(!settled){settled=true;reject(new Error('HiPS layer did not initialize.'));}},12000);
        const done=(error?:unknown)=>{if(settled)return;settled=true;clearTimeout(timeout);if(error)reject(error);else resolve();};
        const layer=A.imageHiPS(url,{imgFormat:cube?'png':'jpeg',name:cube?'SPHEREx DR1':'2MASS K',
          successCallback:(hips:any)=>{if(disposed||token!==surveyToken){done();return;}try{if(selected)hips.setFrequency({value:selected.frequencyHz,unit:'Hz'});done();}catch(e){done(e);}},
          errorCallback:(e:unknown)=>done(e||new Error('HiPS layer unavailable'))});
        aladin.setBaseImageLayer(layer);
        backgroundSlotReserved=true;
        releaseInitialBackground();
        // Aladin exposes the asynchronous properties/layer query in this pinned release.
        if(layer.query?.catch)layer.query.catch((e:unknown)=>done(e));
      });
      if(!disposed&&token===surveyToken){activeSurvey={id:surveyId,name:cube?'SPHEREx DR1 all-sky':'2MASS K',wavelengthUm:selected?.wavelengthUm??2.16,state:'ready'};surveyChanged(activeSurvey);}
      if(restore&&!disposed&&token===surveyToken)await showFrame(restore,restoreIndex);
    };
    try{await attempt(id);}catch(error){
      if(disposed||token!==surveyToken)return;
      if(id==='spherex'){
        try{await attempt('2mass');if(token===surveyToken)surveyChanged({id:'2mass',name:'2MASS K',wavelengthUm:2.16,state:'ready',message:'SPHEREx background unavailable. Showing 2MASS context; local cutouts remain SPHEREx.'});}
        catch{surveyChanged({id:'none',name:'Background unavailable',state:'error',message:'Remote sky tiles could not load. Local SPHEREx fields are still available.'});}
      }else if(activeSurvey)surveyChanged({...activeSurvey,message:'2MASS could not load. Keeping the previous sky background.'});
      else surveyChanged({id:'none',name:'Background unavailable',state:'error',message:'2MASS could not load. Local SPHEREx fields are still available.'});
    }finally{releaseInitialBackground();}
  };
  const engine:SkyEngine={
    getCamera:()=>({center:Array.from(aladin.getRaDec()) as LonLat,fov:aladin.getFov()[0]}),
    setCamera:camera=>{if(disposed)return;aladin.gotoRaDec(...camera.center);aladin.setFoV(camera.fov);emit();},
    snapshot,
    project:point=>{const p=aladin.world2pix(...point);return p&&p.every(Number.isFinite)?Array.from(p) as LonLat:null;},
    unproject:point=>{const p=aladin.pix2world(...point);return p&&p.every(Number.isFinite)?Array.from(p) as LonLat:null;},
    subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},
    setSurvey,
    showCutout:target=>showFrame(target,0),showFrame,
    prepareSequence:async target=>{for(let index=0;index<(target.sequence?.frames.length??1);index++)await ensureFrame(target,index).promise;},
    getDiagnostics:()=>({initializationMs:performance.now()-began,layers:[...layers].map(([key,entry])=>({key,ready:entry.ready,loadMs:entry.loadMs,cuts:entry.ready?entry.image.getCuts():null,stretch:entry.ready?entry.image.getColorCfg().stretch:null,opacity:entry.ready?entry.image.getOpacity():0}))}),
    testProjection:projection=>{aladin.setProjection(projection);emit();},
    hideCutout,
    setCutoutVisible:visible=>{activeImage?.setOpacity(visible?1:0);emit();},
    getCutoutStatus:()=>({id:activeId,loaded:imageLoaded,nativeCenter,frameId,frameIndex,cuts:activeImage?.getCuts()??null}),
    dispose:()=>{disposed=true;releaseInitialBackground();cutoutToken++;surveyToken++;cancelAnimationFrame(raf);resize.disconnect();listeners.clear();
      aladin.on('positionChanged',()=>{});aladin.on('zoomChanged',()=>{});
      if(typeof aladin.remove==='function')aladin.remove();else host.replaceChildren();},
  };
  const initializationMs=performance.now()-began;
  const diagnostics=engine.getDiagnostics;
  engine.getDiagnostics=()=>({...diagnostics(),initializationMs});
  // Three first-frame layers at most. Hidden native layers stay cached for reuse.
  const warm=window.setTimeout(()=>{void (async()=>{for(const target of targets){if(disposed)return;try{await ensureFrame(target,0).promise;}catch{/* Retried with an explicit error on selection. */}}})();},1000);
  const dispose=engine.dispose;engine.dispose=()=>{clearTimeout(warm);dispose();};
  emit();return engine;
}
