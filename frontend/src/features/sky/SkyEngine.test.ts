import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import type {SkyEngine,SkyTarget} from '../../types/sky';
import catalog from '../../../public/data/catalog.json';
const fake=vi.hoisted(()=>({order:[] as string[],images:[] as any[],camera:vi.fn(),resolveProperties:null as null|(()=>void)}));
vi.mock('aladin-lite',()=>({default:{init:Promise.resolve(),
  aladin:()=>({addOverlay:vi.fn(),getRaDec:()=>[331,-56],getFov:()=>[1,1],getSize:()=>[1400,1000],on:vi.fn(),gotoRaDec:fake.camera,setFoV:vi.fn(),
    setBaseImageLayer:(layer:any)=>{fake.order.push('background');queueMicrotask(()=>layer.options.successCallback(layer));},
    setOverlayImageLayer:(image:any)=>{fake.order.push('fits');queueMicrotask(()=>image.options.successCallback(331,-56));},removeImageLayer:vi.fn()}),
  graphicOverlay:()=>({addFootprints:vi.fn(),hide:vi.fn(),show:vi.fn()}),polygon:()=>({}),
  imageHiPS:(_url:string,options:any)=>({options,query:Promise.resolve(),setFrequency:vi.fn()}),
  image:(_url:string,options:any)=>{let cuts=[options.minCut||-999,options.maxCut||999],opacity=0;
    const image={options,getCuts:()=>cuts,setCuts:(a:number,b:number)=>{cuts=[a,b]},setColormap:vi.fn(),getColorCfg:()=>({stretch:'asinh'}),getOpacity:()=>opacity,setOpacity:(value:number)=>{opacity=value}};
    fake.images.push(image);return image;},
}}));
import {createSkyEngine} from './SkyEngine';
const properties='hips_cube_depth=102\nem_min=0.0000007\nem_max=0.000005\ndata_cube_crval3_arr='+Array.from({length:102},(_,i)=>1+i/100).join(' ');
let engine:SkyEngine;
beforeEach(()=>{fake.order.length=0;fake.images.length=0;fake.camera.mockReset();
  vi.stubGlobal('window',{location:{href:'http://localhost/'},setTimeout});
  vi.stubGlobal('requestAnimationFrame',()=>1);vi.stubGlobal('cancelAnimationFrame',vi.fn());
  vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,text:async()=>properties})));
});
afterEach(()=>{engine?.dispose();vi.unstubAllGlobals();});
const target=()=>structuredClone(catalog.targets[0]) as unknown as SkyTarget;
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
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[field],vi.fn());await engine.setSurvey('spherex');await engine.showFrame(field,0);
    expect(engine.getCutoutStatus().cuts![0]).toBe(0);
  });
  it('reports a missing epoch without loading a remote FITS proxy',async()=>{
    engine=await createSkyEngine({replaceChildren(){}} as unknown as HTMLDivElement,[target()],vi.fn());await engine.setSurvey('spherex');
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:404})));
    await expect(engine.showFrame(target(),1)).rejects.toThrow('HTTP 404');expect(fake.images).toHaveLength(0);
  });
});
