import { describe,it,expect } from 'vitest';
import { sphericalInterpolate,interpolateFov,fitFieldFov,flyTo,type AnimationClock } from './flyTo';
import type { Camera } from '../../types/sky';

describe('spherical camera interpolation',()=>{
  it('takes the short path across RA zero',()=>{const [ra,dec]=sphericalInterpolate([359,0],[1,0],0.5);expect(Math.min(ra,360-ra)).toBeLessThan(1e-8);expect(dec).toBeCloseTo(0);});
  it('goes over the pole rather than linearly through the sky',()=>{const [ra,dec]=sphericalInterpolate([0,80],[180,80],0.5);expect(Number.isFinite(ra)).toBe(true);expect(dec).toBeCloseTo(90,5);});
  it('handles antipodal and identical centers without NaN',()=>{for(const pair of [[[0,0],[180,0]],[[20,30],[20,30]]] as const){const p=sphericalInterpolate([...pair[0]],[...pair[1]],0.5);expect(p.every(Number.isFinite)).toBe(true);}});
  it('arrives at the exact fixed center',()=>{expect(sphericalInterpolate([0,0],[331.09633125951194,-56.80053487932291],1)).toEqual([331.09633125951194,-56.80053487932291]);});
  it('interpolates zoom logarithmically',()=>{expect(interpolateFov(100,1,0.5)).toBeCloseTo(10);expect(()=>interpolateFov(0,1,.5)).toThrow();});
  it('fits real angular dimensions to the viewport',()=>{expect(fitFieldFov(.15,.15,[1600,900])).toBeGreaterThan(.15*2.8);expect(fitFieldFov(.15,.15,[400,800])).toBeCloseTo(.42);});
});

function fakeClock(){let time=0,id=0;const callbacks=new Map<number,(time:number)=>void>();const timer:AnimationClock={now:()=>time,request:cb=>{callbacks.set(++id,cb);return id;},cancel:key=>{callbacks.delete(key);}};
  return {timer,callbacks,step:(value:number)=>{time=value;const work=[...callbacks.values()];callbacks.clear();work.forEach(cb=>cb(time));}};}
describe('FlyTo lifecycle',()=>{
  const from:Camera={center:[0,0],fov:360},to:Camera={center:[331,-56],fov:.5};
  it('cancels its scheduled frame and never applies a late camera',async()=>{const t=fakeClock(),controller=new AbortController(),applied:Camera[]=[];
    const result=flyTo(from,to,c=>applied.push(c),controller.signal,2500,false,t.timer);t.step(1000);controller.abort();expect(await result).toBe(false);const n=applied.length;t.step(3000);expect(applied).toHaveLength(n);expect(t.callbacks.size).toBe(0);});
  it('finishes exactly and releases scheduled work',async()=>{const t=fakeClock(),applied:Camera[]=[];const result=flyTo(from,to,c=>applied.push(c),new AbortController().signal,2500,false,t.timer);t.step(1250);t.step(2500);expect(await result).toBe(true);expect(applied.at(-1)).toEqual(to);expect(t.callbacks.size).toBe(0);});
  it('respects reduced motion without a timer',async()=>{const t=fakeClock(),applied:Camera[]=[];expect(await flyTo(from,to,c=>applied.push(c),new AbortController().signal,2500,true,t.timer)).toBe(true);expect(applied).toEqual([to]);expect(t.callbacks.size).toBe(0);});
  it('does nothing for an already aborted request',async()=>{const t=fakeClock(),c=new AbortController();c.abort();expect(await flyTo(from,to,()=>{throw new Error('Must not move');},c.signal,2500,false,t.timer)).toBe(false);});
});
