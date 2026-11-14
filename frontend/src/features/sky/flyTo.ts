import type { Camera, LonLat } from '../../types/sky';

const radians = Math.PI / 180;
const vector = ([ra, dec]: LonLat) => [Math.cos(dec*radians)*Math.cos(ra*radians), Math.cos(dec*radians)*Math.sin(ra*radians), Math.sin(dec*radians)];
const normalized = (v: number[]) => { const n = Math.hypot(...v); return v.map(x => x / n); };
const coordinate = (v: number[]): LonLat => [((Math.atan2(v[1],v[0])/radians)%360+360)%360, Math.atan2(v[2],Math.hypot(v[0],v[1]))/radians];

export function sphericalInterpolate(start: LonLat, end: LonLat, t: number): LonLat {
  if (t <= 0) return [start[0]>=0&&start[0]<360?start[0]:((start[0]%360)+360)%360, start[1]];
  if (t >= 1) return [end[0]>=0&&end[0]<360?end[0]:((end[0]%360)+360)%360, end[1]];
  const a = vector(start), b = vector(end);
  const dot = Math.max(-1, Math.min(1,a.reduce((sum,v,i)=>sum+v*b[i],0)));
  if (dot > 0.9995) return coordinate(normalized(a.map((v,i)=>v*(1-t)+b[i]*t)));
  if (dot < -0.999999) {
    const axis = Math.abs(a[2]) < 0.8 ? [0,0,1] : [0,1,0];
    const perpendicular = normalized([a[1]*axis[2]-a[2]*axis[1],a[2]*axis[0]-a[0]*axis[2],a[0]*axis[1]-a[1]*axis[0]]);
    return coordinate(a.map((v,i)=>v*Math.cos(Math.PI*t)+perpendicular[i]*Math.sin(Math.PI*t)));
  }
  const angle = Math.acos(dot), denominator = Math.sin(angle);
  return coordinate(a.map((v,i)=>(v*Math.sin((1-t)*angle)+b[i]*Math.sin(t*angle))/denominator));
}

export function interpolateFov(from: number, to: number, t: number): number {
  if (!(from > 0 && to > 0 && Number.isFinite(from+to))) throw new Error('Field of view must be positive and finite.');
  return Math.exp(Math.log(from)*(1-t)+Math.log(to)*t);
}
export function fitFieldFov(width: number, height: number, viewport: [number,number]): number {
  return Math.max(width, height*viewport[0]/Math.max(1,viewport[1]))*2.8;
}
export interface AnimationClock { now(): number; request(callback: (time: number)=>void): number; cancel(id: number): void }
const clock: AnimationClock = { now: ()=>performance.now(), request: cb=>requestAnimationFrame(cb), cancel: id=>cancelAnimationFrame(id) };

export function flyTo(from: Camera, to: Camera, apply: (camera: Camera)=>void,
                      signal: AbortSignal, duration=2500, reducedMotion=false, timer: AnimationClock=clock): Promise<boolean> {
  return new Promise(resolve=>{
    if (signal.aborted) { resolve(false); return; }
    if (reducedMotion || duration <= 0) { apply(to); resolve(true); return; }
    const began=timer.now(); let handle=0; let finished=false;
    const finish=(completed: boolean)=>{ if(finished)return; finished=true; timer.cancel(handle); signal.removeEventListener('abort',abort); resolve(completed); };
    const abort=()=>finish(false);
    signal.addEventListener('abort',abort,{once:true});
    const frame=(now:number)=>{
      if(finished)return;
      const progress=Math.min(1,Math.max(0,(now-began)/duration));
      const eased=progress*progress*(3-2*progress);
      apply({center:sphericalInterpolate(from.center,to.center,eased),fov:interpolateFov(from.fov,to.fov,eased)});
      if(progress>=1){apply(to);finish(true);}else handle=timer.request(frame);
    };
    handle=timer.request(frame);
  });
}
