import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import type {SkyEngine,SkyTarget} from '../../types/sky';
import catalog from '../../../public/data/catalog.json';
import metadata from './spherex-cube.json';
const fake=vi.hoisted(()=>({base:null as any,failNextBase:false,order:[] as string[],images:[] as any[],frequencies:[] as number[],camera:vi.fn(),resolveProperties:null as null|(()=>void)}));
vi.mock('aladin-lite',()=>({default:{init:Promise.resolve(),
  aladin:()=>({addOverlay:vi.fn(),addColormap:vi.fn(),getRaDec:()=>[331,-56],getFov:()=>[1,1],getSize:()=>[1400,1000],on:vi.fn(),gotoRaDec:fake.camera,setFoV:vi.fn(),
    setBaseImageLayer:(layer:any)=>{fake.base=layer;fake.order.push('background');if(fake.failNextBase){fake.failNextBase=false;return Promise.reject(new Error('Controlled native base failure'));}queueMicrotask(()=>layer.options.successCallback(layer));return Promise.resolve();},getBaseImageLayer:()=>fake.base,
    setOverlayImageLayer:(image:any)=>{fake.order.push('fits');queueMicrotask(()=>image.options.successCallback(331,-56));},removeImageLayer:vi.fn()}),
  graphicOverlay:()=>({addFootprints:vi.fn(),hide:vi.fn(),show:vi.fn()}),polygon:()=>({}),
  imageHiPS:(_url:string,options:any)=>({id:_url,options,query:Promise.resolve(),setFrequency:vi.fn(({value}:{value:number})=>fake.frequencies.push(value))}),
  image:(_url:string,options:any)=>{let cuts=[options.minCut||-999,options.maxCut||999],opacity=options.opacity||1,stretch=options.stretch;
    const image={options,getCuts:()=>cuts,setCuts:(a:number,b:number)=>{cuts=[a,b]},setColormap:vi.fn((_name:string,options:any)=>{stretch=options.stretch}),getColorCfg:()=>({stretch}),getOpacity:()=>opacity,setOpacity:(value:number)=>{opacity=value}};
    fake.images.push(image);return image;},
}}));
import {createSkyEngine} from './SkyEngine';
const properties='hips_cube_depth=102\ndata_cube_bunit3=um\nem_min='+metadata.emMinMeters+'\nem_max='+metadata.emMaxMeters+'\ndata_cube_crval3_arr='+Array.from({length:102},(_,i)=>metadata.channels.find(c=>c.frameIndex===i)?.wavelengthUm??0).join(' ');
let engine:SkyEngine;
beforeEach(()=>{fake.base=null;fake.failNextBase=false;fake.order.length=0;fake.images.length=0;fake.frequencies.length=0;fake.camera.mockReset();
  vi.stubGlobal('window',{location:{href:'http://localhost/'},setTimeout});
  vi.stubGlobal('requestAnimationFrame',()=>1);vi.stubGlobal('cancelAnimationFrame',vi.fn());
  vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,text:async()=>properties})));
});
afterEach(()=>{engine?.dispose();vi.unstubAllGlobals();});
const target=()=>{const field=structuredClone(catalog.targets[0]) as unknown as SkyTarget;
  const pair=field.sequence!.historicalPair;if(pair){field.sequence!.frames=field.sequence!.frames.filter(f=>f.id===pair.aId||f.id===pair.bId);delete field.sequence!.groups;delete field.sequence!.defaultGroupId;delete field.sequence!.historicalPair;delete field.sequence!.differences;}
  return field;};
describe('native layer lifecycle regression checks',()=>{
  it('reserves a slow background slot before preparing any FITS layer',async()=>{
    let release!:()=>void;const slow=new Promise<void>(resolve=>{release=resolve});
    vi.stubGlobal('fetch',vi.fn(async(url:string)=>{if(url.endsWith('/properties'))await slow;return {ok:true,text:async()=>properties}}));
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[target()],vi.fn());
    const background=engine.setSurvey('spherex'),local=engine.showFrame(target(),0);
    await Promise.resolve();expect(fake.images).toHaveLength(0);release();await background;await local;
    expect(fake.order).toEqual(['background','fits']);expect(engine.getCutoutStatus().loaded).toBe(true);
  });
  it('reuses two prepared layers on every visit without moving the camera',async()=>{
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[target()],vi.fn());await engine.setSurvey('spherex');
    await engine.prepareSequence(target());await engine.showFrame(target(),0);engine.hideCutout();await engine.showFrame(target(),1);await engine.showFrame(target(),0);
    expect(fake.images).toHaveLength(2);expect(fake.camera).not.toHaveBeenCalled();expect(fake.images.map(i=>i.getOpacity())).toEqual([1,0]);
  });
  it('reapplies a real zero cut after the native falsy-value default',async()=>{
    const field=target();field.sequence!.display.vmin=0;
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[field],vi.fn());await engine.setSurvey('spherex');await engine.showFrame(field,0,field.sequence!.display);
    expect(engine.getCutoutStatus().cuts![0]).toBe(0);
  });
  it('reports a missing epoch without loading a remote FITS proxy',async()=>{
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[target()],vi.fn());await engine.setSurvey('spherex');
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:404})));
    await expect(engine.showFrame(target(),1)).rejects.toThrow('HTTP 404');expect(fake.images).toHaveLength(0);
  });
  it('shows a prepared signed residual with linear cuts and restores an epoch without moving the camera',async()=>{
    const field=structuredClone(catalog.targets[0]) as unknown as SkyTarget,difference=field.sequence!.differences![0];
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[field],vi.fn());await engine.setSurvey('spherex');
    await engine.showDifference(field,difference);expect(engine.getCutoutStatus().kind).toBe('difference');expect(engine.getCutoutStatus().frameId).toBeNull();
    expect(engine.getCutoutStatus().cuts).toEqual([difference.display.vmin,difference.display.vmax]);expect(engine.getDiagnostics().layers[0].stretch).toBe('linear');
    await engine.showFrame(field,0);expect(engine.getCutoutStatus().kind).toBe('epoch');expect(fake.camera).not.toHaveBeenCalled();
  });
  it('bounds native layers when visiting more than twelve local display assets',async()=>{
    const field=target(),first=field.sequence!.frames[0];field.sequence!.frames=Array.from({length:15},(_,i)=>({...first,id:`synthetic-${i}`,assets:{...first.assets,fits:`epsilon_indi_b/test-${i}.fits`}}));
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[field],vi.fn());await engine.setSurvey('spherex');
    await engine.prepareSequence(field);expect(engine.getDiagnostics().layers).toHaveLength(12);
  });
  it('newly prepared observations cannot cover the already selected native image',async()=>{
    const field=structuredClone(catalog.targets[0]) as unknown as SkyTarget;
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[field],vi.fn());await engine.setSurvey('spherex');
    await engine.prepareSequence(field);await engine.showFrame(field,0);
    await engine.prepareSequence(field,[0,1,2,3,4,5]);
    const visible=engine.getDiagnostics().layers.filter(layer=>layer.opacity!==0);
    expect(visible).toHaveLength(1);expect(visible[0].key).toContain(field.sequence!.frames[0].id);
  });
  it('changes only the existing HiPS frequency while preserving local cuts, layer identity and camera',async()=>{
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[target()],vi.fn());await engine.setSurvey('spherex');await engine.showFrame(target(),0);
    const before=engine.getCutoutStatus(),images=fake.images.length;
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,arrayBuffer:async()=>new Uint8Array([137,80,78,71,13,10,26,10]).buffer})));
    await engine.setSpectralFrame(76);expect(engine.getSpectralStatus().appliedFrame).toBe(76);
    expect(fake.frequencies).toHaveLength(2);expect(fake.order.filter(item=>item==='background')).toHaveLength(1);
    expect(fake.images).toHaveLength(images);expect(engine.getCutoutStatus()).toEqual(before);expect(fake.camera).not.toHaveBeenCalled();
    engine.hideCutout();await engine.showFrame(target(),0);expect(engine.getSpectralStatus().appliedFrame).toBe(76);
  });
  it('rejects a non-PNG channel preflight and keeps the previous map frequency',async()=>{
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[target()],vi.fn());await engine.setSurvey('spherex');
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,arrayBuffer:async()=>new TextEncoder().encode('HTML error').buffer})));
    await engine.setSpectralFrame(8);expect(engine.getSpectralStatus()).toMatchObject({phase:'error',appliedFrame:29});expect(fake.frequencies).toHaveLength(1);
  });
  it('restores spectral controls when a failed 2MASS switch retains the SPHEREx background',async()=>{
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[target()],vi.fn());await engine.setSurvey('spherex');
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:503})));await engine.setSurvey('2mass');
    expect(engine.getSpectralStatus()).toMatchObject({available:true,appliedFrame:29});
  });
  it('keeps the committed background and usable spectral controls while another survey is pending',async()=>{
    const changed=vi.fn();engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[target()],changed);await engine.setSurvey('spherex');
    let release!:(value:unknown)=>void;vi.stubGlobal('fetch',vi.fn(()=>new Promise(resolve=>{release=resolve})));
    const pending=engine.setSurvey('2mass');expect(changed.mock.lastCall![0]).toMatchObject({id:'spherex',state:'loading'});
    expect(engine.getSpectralStatus().available).toBe(true);release({ok:false,status:503});await pending;
    expect(engine.getDiagnostics().activeSurveyId).toBe('spherex');
  });
  it('restores the actual committed base when native application of a replacement rejects',async()=>{
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[target()],vi.fn());await engine.setSurvey('spherex');const previous=fake.base;
    vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.endsWith('/properties')?{ok:true,text:async()=>'hips_tile_format=jpeg\nhips_order_min=0'}:{ok:true,arrayBuffer:async()=>new Uint8Array([255,216,255]).buffer}));
    fake.failNextBase=true;await engine.setSurvey('2mass');expect(fake.base).toBe(previous);expect(engine.getDiagnostics().activeSurveyId).toBe('spherex');expect(engine.getSpectralStatus().available).toBe(true);
  });

});
